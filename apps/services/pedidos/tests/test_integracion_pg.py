"""
Pruebas contra un PostgreSQL REAL: migracion, SQL del repositorio, bloqueos
(SELECT ... FOR UPDATE), concurrencia real sobre el mismo ISBN y expiracion.
Solo corren si se define TEST_DATABASE_URL (si no, se omiten):

    TEST_DATABASE_URL=postgresql://usuario:clave@localhost:5432/base_de_pruebas pytest tests/test_integracion_pg.py

Usa una base DESECHABLE, nunca la de la aplicacion. Cada prueba trabaja en
un esquema propio (test_pedidos_<aleatorio>) y lo borra al terminar.
"""
import os
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

from conftest import ALEPH, ANA_ID, CIEN, INTERNA, RAYUELA, token
from db import repository
from db.repository import InventarioDuplicado, PedidosRepository
from services import expiracion

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="define TEST_DATABASE_URL (base desechable) para estas pruebas")

APPS = Path(__file__).resolve().parents[3]                      # apps/
SQL_MONOLITO = APPS / "WebMonolito" / "db" / "01_schema.sql"
SQL_PEDIDOS = APPS / "services" / "pedidos" / "sql" / "001_pedidos.sql"


class Base:
    def __init__(self, esquema):
        self.esquema = esquema

    def conectar(self, autocommit=False):
        import psycopg

        return psycopg.connect(URL, autocommit=autocommit, options=f"-c search_path={self.esquema}")

    def ejecutar_archivo(self, ruta):
        with self.conectar(autocommit=True) as conn:
            conn.execute(ruta.read_text(encoding="utf-8"))

    def sql(self, consulta, parametros=None):
        with self.conectar() as conn:
            cur = conn.execute(consulta, parametros)
            return cur.fetchall() if cur.description else None

    @contextmanager
    def unit_of_work(self):
        conn = self.conectar()
        try:
            yield PedidosRepository(conn)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def stock(self, isbn):
        return self.sql("SELECT stock_disponible, stock_reservado FROM inventario WHERE isbn = %s", (isbn,))[0]


def _esquema_nuevo():
    import psycopg

    esquema = f"test_pedidos_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {esquema}")
    return Base(esquema)


def _borrar(db):
    import psycopg

    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {db.esquema} CASCADE")


@pytest.fixture
def migrada():
    """Base del monolito con tres libros (stock 5, 2 y 10) y la migracion de pedidos aplicada."""
    db = _esquema_nuevo()
    try:
        db.ejecutar_archivo(SQL_MONOLITO)
        db.sql("INSERT INTO formatos (nombre) VALUES ('Tapa dura')")
        db.sql("INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, id_formato) VALUES "
               "(%s, 'Cien años de soledad', 1967, 300, 5, 1), (%s, 'El Aleph', 1949, 250.50, 2, 1), "
               "(%s, 'Rayuela', 1963, 199.99, 10, 1)", (CIEN, ALEPH, RAYUELA))
        db.ejecutar_archivo(SQL_PEDIDOS)
        yield db
    finally:
        _borrar(db)


@pytest.fixture
def api(migrada, monkeypatch, client):
    monkeypatch.setattr(repository, "unit_of_work", migrada.unit_of_work)
    return client


# ------------------------------------------------------------------ migracion
def test_migracion_tablas_e_inventario_inicial_desde_libros(migrada):
    assert migrada.sql("SELECT isbn, stock_disponible, stock_reservado FROM inventario ORDER BY isbn") == [
        (CIEN, 5, 0), (ALEPH, 2, 0), (RAYUELA, 10, 0)]
    tablas = {t for (t,) in migrada.sql(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")}
    assert {"inventario", "pedidos", "pedido_lineas", "pedido_historial"} <= tablas
    assert ("006_pedidos",) in migrada.sql("SELECT version FROM schema_migraciones")
    # sin llaves foraneas hacia las tablas de otros servicios
    foraneas = {t for (t,) in migrada.sql(
        "SELECT DISTINCT ccu.table_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu USING (constraint_schema, constraint_name) "
        "WHERE tc.table_schema = current_schema() AND tc.constraint_type = 'FOREIGN KEY' "
        "AND tc.table_name IN ('inventario', 'pedidos', 'pedido_lineas', 'pedido_historial')")}
    assert foraneas == {"pedidos"}


def test_migracion_idempotente_no_repone_el_inventario(migrada):
    migrada.sql("UPDATE inventario SET stock_disponible = 1 WHERE isbn = %s", (CIEN,))
    migrada.sql("DELETE FROM inventario WHERE isbn = %s", (RAYUELA,))
    migrada.ejecutar_archivo(SQL_PEDIDOS)
    migrada.ejecutar_archivo(SQL_PEDIDOS)
    assert migrada.sql("SELECT isbn, stock_disponible FROM inventario ORDER BY isbn") == [(CIEN, 1), (ALEPH, 2)]
    assert migrada.sql("SELECT stock FROM libros WHERE isbn = %s", (CIEN,)) == [(5,)]     # books intacto


def test_migracion_en_una_base_sin_la_tabla_libros():
    db = _esquema_nuevo()
    try:
        db.ejecutar_archivo(SQL_PEDIDOS)
        assert db.sql("SELECT COUNT(*) FROM inventario") == [(0,)]
    finally:
        _borrar(db)


def test_la_base_impide_stock_negativo(migrada):
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        with migrada.unit_of_work() as repo:
            repo.inventario_bloquear([ALEPH])
            repo.inventario_ajustar(ALEPH, disponible=-3, reservado=3)
    assert migrada.stock(ALEPH) == (2, 0)


def test_repositorio_inventario(migrada):
    with migrada.unit_of_work() as repo:
        assert repo.inventario_get(CIEN)["stock_disponible"] == 5 and repo.inventario_get("X") is None
        filas, total = repo.inventario_list(limit=2, offset=1)
        assert total == 3 and [f["isbn"] for f in filas] == [ALEPH, RAYUELA]
        assert list(repo.inventario_bloquear([RAYUELA, CIEN, "NO-ESTA"])) == [CIEN, RAYUELA]
        assert repo.inventario_insert("NUEVO-1", 4)["stock_reservado"] == 0
        assert repo.inventario_fijar_disponible("NUEVO-1", 9)["stock_disponible"] == 9
        assert repo.inventario_delete("NUEVO-1") is True and repo.inventario_delete("NUEVO-1") is False
    with pytest.raises(InventarioDuplicado):
        with migrada.unit_of_work() as repo:
            repo.inventario_insert(CIEN, 1)


# ------------------------------------------------------------------ API completa sobre PostgreSQL
def test_api_flujo_completo_sobre_postgresql(api, migrada, fake_redis, ana, admin, pedir):
    creado = pedir(ana, {CIEN: 2, ALEPH: 1})
    assert creado.status_code == 201
    pedido = creado.get_json()
    assert pedido["total"] == 850.5 and pedido["expira_en"] > pedido["created_at"] and pedido["articulos"] == 3
    assert migrada.stock(CIEN) == (3, 2) and migrada.stock(ALEPH) == (1, 1)
    assert migrada.sql("SELECT estado, total, expira_en - created_at FROM pedidos")[0][:2] == ("PENDIENTE_PAGO", 850.5)

    assert pedir(ana, {ALEPH: 2}).status_code == 409 and migrada.stock(ALEPH) == (1, 1)

    editado = api.patch(f"/pedidos/{pedido['id']}/lineas", headers=ana, json={"lineas": [
        {"isbn": CIEN, "cantidad": 1}, {"isbn": ALEPH, "cantidad": 0}, {"isbn": RAYUELA, "cantidad": 3}]})
    assert editado.status_code == 200 and editado.get_json()["total"] == 899.97
    assert migrada.stock(CIEN) == (4, 1) and migrada.stock(ALEPH) == (2, 0) and migrada.stock(RAYUELA) == (7, 3)
    assert api.put(f"/pedidos/{pedido['id']}", headers=ana, json={"lineas": [{"isbn": CIEN, "cantidad": 6}]}).status_code == 409

    lista = api.get("/pedidos", headers=ana).get_json()
    assert lista["total"] == 1 and lista["items"][0]["articulos"] == 4
    assert api.get("/pedidos?estado=PAGADO", headers=admin).get_json()["total"] == 0
    assert api.get(f"/pedidos?user_id={ANA_ID}", headers=admin).get_json()["total"] == 1

    assert api.patch(f"/pedidos/internal/{pedido['id']}/estado", headers=INTERNA, json={"estado": "PAGADO"}).status_code == 200
    assert migrada.stock(CIEN) == (4, 0) and migrada.stock(RAYUELA) == (7, 0)          # venta confirmada
    assert api.patch(f"/pedidos/{pedido['id']}/estado", headers=admin, json={"estado": "ENTREGADO"}).status_code == 409
    assert api.patch(f"/pedidos/{pedido['id']}/estado", headers=admin, json={"estado": "ENVIADO"}).status_code == 200
    final = api.get(f"/pedidos/{pedido['id']}", headers=ana).get_json()
    assert [h["estado_nuevo"] for h in final["historial"]] == ["PENDIENTE_PAGO", "PAGADO", "ENVIADO"]

    otro = pedir(ana, {CIEN: 4}).get_json()["id"]
    assert migrada.stock(CIEN) == (0, 4)
    assert api.patch(f"/pedidos/{otro}/cancelar", headers=ana).status_code == 200
    assert migrada.stock(CIEN) == (4, 0)                                              # el stock regresa
    assert api.delete(f"/pedidos/{otro}", headers=admin).status_code == 200
    assert api.get(f"/pedidos/{otro}", headers=admin).status_code == 404
    assert migrada.sql("SELECT eliminado_en IS NOT NULL FROM pedidos WHERE id = %s", (otro,)) == [(True,)]


def test_expiracion_sobre_postgresql(api, migrada, fake_redis, ana, pedir):
    vencido = pedir(ana, {CIEN: 2}).get_json()["id"]
    vigente = pedir(ana, {CIEN: 1}).get_json()["id"]
    migrada.sql("UPDATE pedidos SET expira_en = NOW() - INTERVAL '1 second' WHERE id = %s", (vencido,))

    assert expiracion.ejecutar_una_vez() == [vencido]
    assert migrada.sql("SELECT id, estado FROM pedidos ORDER BY id") == [(vencido, "EXPIRADO"), (vigente, "PENDIENTE_PAGO")]
    assert migrada.stock(CIEN) == (4, 1)
    assert migrada.sql("SELECT estado_anterior, estado_nuevo, actor FROM pedido_historial WHERE pedido_id = %s "
                       "ORDER BY id DESC LIMIT 1", (vencido,)) == [("PENDIENTE_PAGO", "EXPIRADO", "sistema:expiracion")]
    assert api.patch(f"/pedidos/{vencido}/lineas", headers=ana, json={"lineas": [{"isbn": CIEN, "cantidad": 1}]}).status_code == 409


def test_la_expiracion_no_espera_a_un_pedido_bloqueado_por_otra_peticion(api, migrada, fake_redis, ana, pedir):
    """SKIP LOCKED: si un pago tiene bloqueado el pedido, la tarea no se queda colgada ni lo expira."""
    pedido = pedir(ana, {CIEN: 1}).get_json()["id"]
    migrada.sql("UPDATE pedidos SET expira_en = NOW() - INTERVAL '1 second' WHERE id = %s", (pedido,))
    with migrada.unit_of_work() as pago:
        pago.pedido_get(pedido, bloquear=True)                  # el pago llego justo a tiempo y lo tiene bloqueado
        assert expiracion.ejecutar_una_vez() == []
    assert migrada.sql("SELECT estado FROM pedidos WHERE id = %s", (pedido,)) == [("PENDIENTE_PAGO",)]


# ------------------------------------------------------------------ concurrencia real
def test_concurrencia_real_sobre_el_mismo_isbn_nunca_sobrevende(api, migrada, fake_redis):
    """12 peticiones simultaneas, cada una en su conexion, por 1 unidad de un libro con 5: exactamente 5 ganan."""
    resultados, arranque = [], threading.Barrier(12)

    def comprar():
        cliente = api.application.test_client()
        arranque.wait()
        resp = cliente.post("/pedidos", headers=token(ANA_ID), json={"lineas": [{"isbn": CIEN, "cantidad": 1}]})
        resultados.append(resp.status_code)

    hilos = [threading.Thread(target=comprar) for _ in range(12)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)

    assert sorted(resultados) == [201] * 5 + [409] * 7, resultados
    assert migrada.stock(CIEN) == (0, 5)
    assert migrada.sql("SELECT COUNT(*), SUM(cantidad) FROM pedido_lineas WHERE isbn = %s", (CIEN,)) == [(5, 5)]


def test_pedidos_cruzados_no_se_bloquean_entre_si(api, migrada, fake_redis):
    """Unos piden CIEN+RAYUELA y otros RAYUELA+CIEN a la vez: el orden fijo de bloqueo evita el deadlock."""
    errores, arranque = [], threading.Barrier(8)

    def comprar(isbns):
        cliente = api.application.test_client()
        arranque.wait()
        resp = cliente.post("/pedidos", headers=token(ANA_ID),
                            json={"lineas": [{"isbn": isbn, "cantidad": 1} for isbn in isbns]})
        if resp.status_code not in (201, 409):
            errores.append(resp.get_json())

    hilos = [threading.Thread(target=comprar, args=((CIEN, RAYUELA) if i % 2 else (RAYUELA, CIEN),)) for i in range(8)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)

    assert errores == []
    disponible_cien, reservado_cien = migrada.stock(CIEN)
    assert (disponible_cien, reservado_cien) == (0, 5) and migrada.stock(RAYUELA) == (5, 5)
