"""
Pruebas contra un PostgreSQL REAL: migraciones, trigger, consultas del
repositorio y crear_admin.py. Solo corren si se define TEST_DATABASE_URL
(si no, se omiten):

    TEST_DATABASE_URL=postgresql://usuario:clave@localhost:5432/base_de_pruebas pytest tests/test_integracion_pg.py

Usa una base DESECHABLE, nunca la de la aplicacion. Cada prueba trabaja en
un esquema propio (test_users_<aleatorio>) que crea con el esquema real del
monolito (WebMonolito/db/01_schema.sql y 05_triggers.sql) y borra al terminar.
"""
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

from common import redis_client
from conftest import PASSWORD, RedisQueFallaAlRevocar
from db import repository
from db.repository import EmailDuplicado, UnSoloAdmin, UserRepository
from services import passwords

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="define TEST_DATABASE_URL (base desechable) para estas pruebas")

APPS = Path(__file__).resolve().parents[3]                      # apps/
SQL_BASE = [APPS / "WebMonolito" / "db" / "01_schema.sql", APPS / "WebMonolito" / "db" / "05_triggers.sql",
            APPS / "services" / "login" / "sql" / "auth_module.sql"]
SQL_VARIOS_ADMINS = APPS / "services" / "users" / "sql" / "opcional_permitir_varios_admins.sql"
SQL_USERS = [APPS / "services" / "users" / "sql" / "001_roles.sql", APPS / "services" / "users" / "sql" / "002_users.sql"]


class Base:
    def __init__(self, esquema):
        self.esquema = esquema

    def conectar(self, autocommit=False):
        import psycopg

        return psycopg.connect(URL, autocommit=autocommit, options=f"-c search_path={self.esquema}")

    def ejecutar_archivo(self, ruta):
        with self.conectar(autocommit=True) as conn:
            conn.execute(ruta.read_text(encoding="utf-8"))       # sin parametros: admite varias sentencias

    def sql(self, consulta, parametros=None):
        with self.conectar() as conn:
            cur = conn.execute(consulta, parametros)
            return cur.fetchall() if cur.description else None

    @contextmanager
    def unit_of_work(self):
        conn = self.conectar()
        try:
            yield UserRepository(conn)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def usuario(self, correo):
        filas = self.sql("SELECT id_usuario, es_admin, role_id, activo, password_hash, estado_cuenta "
                         "FROM usuarios WHERE correo = %s", (correo,))
        return filas[0] if filas else None


@pytest.fixture
def base():
    """Esquema nuevo con las tablas del monolito y los usuarios tal como estaban ANTES de la Parte 1."""
    import psycopg

    esquema = f"test_users_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {esquema}")
    db = Base(esquema)
    try:
        for ruta in SQL_BASE:
            db.ejecutar_archivo(ruta)
        db.sql("""
            INSERT INTO usuarios (nombre, apellido_paterno, correo, password_hash, es_admin, estado_cuenta) VALUES
                ('Admin', 'Principal', 'admin@libreria.com', 'CAMBIAR_POR_HASH_BCRYPT_REAL', TRUE, 'confirmado'),
                ('Maru', 'Valo', 'maruchanvalo@gmail.com', 'x', FALSE, 'confirmado'),
                ('Ana_100%', 'Pérez', 'ana@correo.com', 'x', FALSE, 'pendiente')
        """)
        yield db
    finally:
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA {esquema} CASCADE")


@pytest.fixture
def migrada(base):
    for ruta in SQL_USERS:
        base.ejecutar_archivo(ruta)
    return base


@pytest.fixture
def varios_admins(migrada):
    """La misma base despues de ejecutar el script OPCIONAL que quita el indice un_solo_admin."""
    migrada.ejecutar_archivo(SQL_VARIOS_ADMINS)
    migrada.ejecutar_archivo(SQL_VARIOS_ADMINS)          # idempotente
    return migrada


# ------------------------------------------------------------------ migraciones
def test_migraciones_roles_segun_es_admin(migrada):
    assert migrada.sql("SELECT role_id, nombre FROM roles ORDER BY 1") == [(1, "admin"), (2, "cliente")]
    assert migrada.usuario("admin@libreria.com")[1:3] == (True, 1)
    assert migrada.usuario("maruchanvalo@gmail.com")[1:3] == (False, 2)
    versiones = {v for (v,) in migrada.sql("SELECT version FROM schema_migraciones")}
    assert {"003_roles", "004_users"} <= versiones


def test_solo_se_agrega_lo_que_falta(migrada):
    columnas = {c for (c,) in migrada.sql(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
        "AND table_name = 'usuarios'")}
    assert columnas == {"id_usuario", "nombre", "apellido_paterno", "apellido_materno", "correo", "password_hash",
                        "es_admin", "fecha_registro", "activo", "estado_cuenta", "role_id", "updated_at"}
    # los datos existentes no se tocaron y updated_at nace igual a la fecha de alta
    assert migrada.usuario("admin@libreria.com")[4] == "CAMBIAR_POR_HASH_BCRYPT_REAL"
    assert migrada.sql("SELECT COUNT(*) FROM usuarios WHERE updated_at <> fecha_registro") == [(0,)]


def test_migraciones_idempotentes_y_no_pisan_cambios_posteriores(varios_admins):
    migrada = varios_admins
    migrada.sql("UPDATE usuarios SET role_id = 1 WHERE correo = 'maruchanvalo@gmail.com'")   # users la promovio
    antes = migrada.sql("SELECT * FROM usuarios ORDER BY id_usuario")
    for _ in range(2):
        for ruta in SQL_USERS:
            migrada.ejecutar_archivo(ruta)
    assert migrada.sql("SELECT * FROM usuarios ORDER BY id_usuario") == antes
    assert migrada.sql("SELECT COUNT(*) FROM roles") == [(2,)]


def test_002_resincroniza_si_el_monolito_cambio_es_admin_despues_de_la_001(base):
    base.ejecutar_archivo(SQL_USERS[0])
    # Entre la Parte 1 y la Parte 2 todavia no hay trigger: el monolito pasa el cargo de admin a otra cuenta.
    base.sql("UPDATE usuarios SET es_admin = FALSE WHERE correo = 'admin@libreria.com'")
    base.sql("UPDATE usuarios SET es_admin = TRUE WHERE correo = 'ana@correo.com'")
    assert base.usuario("ana@correo.com")[1:3] == (True, 2) and base.usuario("admin@libreria.com")[1:3] == (False, 1)
    base.ejecutar_archivo(SQL_USERS[1])
    assert base.usuario("ana@correo.com")[1:3] == (True, 1) and base.usuario("admin@libreria.com")[1:3] == (False, 2)


def test_trigger_mantiene_sincronizados_es_admin_y_role_id(varios_admins):
    migrada = varios_admins
    migrada.sql("UPDATE usuarios SET es_admin = TRUE WHERE correo = 'ana@correo.com'")       # lo hace el monolito
    assert migrada.usuario("ana@correo.com")[1:3] == (True, 1)
    migrada.sql("UPDATE usuarios SET role_id = 2 WHERE correo = 'ana@correo.com'")           # lo hace users
    assert migrada.usuario("ana@correo.com")[1:3] == (False, 2)
    migrada.sql("INSERT INTO usuarios (nombre, correo, password_hash, es_admin) VALUES ('Jefa', 'jefa@x.com', 'x', TRUE)")
    assert migrada.usuario("jefa@x.com")[1:3] == (True, 1)
    migrada.sql("INSERT INTO usuarios (nombre, correo, password_hash) VALUES ('Cliente', 'cliente@x.com', 'x')")
    assert migrada.usuario("cliente@x.com")[1:3] == (False, 2)
    # updated_at avanza con cualquier UPDATE (tambien los de login o el monolito)
    migrada.sql("UPDATE usuarios SET updated_at = '2000-01-01' WHERE correo = 'ana@correo.com'")
    assert migrada.sql("SELECT updated_at > '2020-01-01' FROM usuarios WHERE correo = 'ana@correo.com'") == [(True,)]


# ------------------------------------------------------------------ repositorio
def test_repositorio_respeta_el_indice_un_solo_admin_del_monolito(migrada):
    id_maru = migrada.usuario("maruchanvalo@gmail.com")[0]
    with pytest.raises(UnSoloAdmin):
        with migrada.unit_of_work() as repo:
            repo.update(id_maru, role_id=1)
    with pytest.raises(UnSoloAdmin):
        with migrada.unit_of_work() as repo:
            repo.insert(nombre="Otro", apellido_paterno=None, apellido_materno=None, correo="otro@correo.com",
                        password_hash="h", role_id=1, activo=True, estado_cuenta="confirmado")
    assert migrada.usuario("maruchanvalo@gmail.com")[1:3] == (False, 2) and migrada.usuario("otro@correo.com") is None
    # el traspaso del cargo si se puede: primero deja de serlo uno y luego se nombra al otro
    with migrada.unit_of_work() as repo:
        repo.update(migrada.usuario("admin@libreria.com")[0], role_id=2)
        repo.update(id_maru, role_id=1)
    assert migrada.usuario("maruchanvalo@gmail.com")[1:3] == (True, 1)


def test_repositorio_alta_lectura_y_duplicados(varios_admins):
    migrada = varios_admins
    with migrada.unit_of_work() as repo:
        fila = repo.insert(nombre="Luis", apellido_paterno="Soto", apellido_materno=None, correo="Luis@Correo.com",
                           password_hash="h", role_id=1, activo=True, estado_cuenta="confirmado")
    assert fila["correo"] == "luis@correo.com" and fila["role_id"] == 1         # trigger del monolito: minusculas
    assert "password_hash" not in fila and "es_admin" not in fila
    assert migrada.usuario("luis@correo.com")[1] is True

    with migrada.unit_of_work() as repo:
        assert repo.get(fila["id_usuario"]) == fila and repo.get_by_email("luis@correo.com") == fila
        assert repo.get(999999) is None and repo.get_by_email("nadie@x.com") is None
        assert repo.password_hash(fila["id_usuario"]) == "h" and repo.password_hash(999999) is None
        assert [r["nombre"] for r in repo.roles()] == ["admin", "cliente"]
        assert repo.role(2)["nombre"] == "cliente" and repo.role(99) is None

    with pytest.raises(EmailDuplicado):
        with migrada.unit_of_work() as repo:
            repo.insert(nombre="Otro", apellido_paterno=None, apellido_materno=None, correo="LUIS@correo.com",
                        password_hash="h", role_id=2, activo=True, estado_cuenta="confirmado")
    with pytest.raises(EmailDuplicado):
        with migrada.unit_of_work() as repo:
            repo.update(fila["id_usuario"], correo="admin@libreria.com")


def test_repositorio_lista_filtros_y_paginacion(migrada):
    with migrada.unit_of_work() as repo:
        todos, total = repo.list()
        assert total == 3 and [f["correo"] for f in todos] == ["admin@libreria.com", "maruchanvalo@gmail.com", "ana@correo.com"]
        assert [f["correo"] for f in repo.list(q="MARU")[0]] == ["maruchanvalo@gmail.com"]
        assert [f["correo"] for f in repo.list(q="principal")[0]] == ["admin@libreria.com"]
        assert [f["correo"] for f in repo.list(q="_100%")[0]] == ["ana@correo.com"]         # % y _ son literales
        assert repo.list(q="%")[1] == 1 and repo.list(q="_")[1] == 1
        assert [f["correo"] for f in repo.list(role_id=1)[0]] == ["admin@libreria.com"]
        assert repo.list(activo=False) == ([], 0) and repo.list(activo=True, role_id=2)[1] == 2
        pagina, total = repo.list(limit=2, offset=2)
        assert total == 3 and [f["correo"] for f in pagina] == ["ana@correo.com"]


def test_repositorio_update_y_conteo_de_admins(varios_admins):
    migrada = varios_admins
    id_maru = migrada.usuario("maruchanvalo@gmail.com")[0]
    id_admin = migrada.usuario("admin@libreria.com")[0]
    with migrada.unit_of_work() as repo:
        assert repo.otros_admins_activos(id_admin) == 0 and repo.otros_admins_activos(id_maru) == 1
        fila = repo.update(id_maru, role_id=1, nombre="María")
        assert fila["role_id"] == 1 and fila["nombre"] == "María" and fila["updated_at"] > fila["fecha_registro"]
        assert repo.otros_admins_activos(id_admin) == 1
        repo.update(id_maru, activo=False)
        assert repo.otros_admins_activos(id_admin) == 0                          # un admin inactivo no cuenta
        with pytest.raises(ValueError):
            repo.update(id_maru, id_usuario=5)
    assert migrada.usuario("maruchanvalo@gmail.com")[1:4] == (True, 1, False)     # es_admin sincronizado


def test_el_bloqueo_no_impide_a_login_crear_el_token_de_confirmacion(migrada):
    """users mantiene bloqueada la fila mientras login inserta en tokens_confirmacion (FK a esa fila)."""
    id_ana = migrada.usuario("ana@correo.com")[0]
    with migrada.unit_of_work() as repo:
        repo.get(id_ana, bloquear=True)
        with migrada.conectar() as login:                 # lo que hace login durante la llamada HTTP
            login.execute("SET lock_timeout = '2s'")
            login.execute("INSERT INTO tokens_confirmacion (id_usuario, token_hash, expira_en) "
                          "VALUES (%s, %s, NOW() + INTERVAL '1 hour')", (id_ana, "a" * 64))
        repo.update(id_ana, correo="ana.nueva@correo.com", estado_cuenta="pendiente")
    assert migrada.sql("SELECT COUNT(*) FROM tokens_confirmacion") == [(1,)]
    assert migrada.usuario("ana.nueva@correo.com")[5] == "pendiente"


# ------------------------------------------------------------------ crear_admin.py
def test_crear_admin_sobre_postgresql_es_idempotente(migrada):
    from test_crear_admin import crear_admin

    with migrada.unit_of_work() as repo:
        _, acciones = crear_admin.asegurar_admin(repo, "admin@libreria.com", "ClaveDelAdmin123")
    assert len(acciones) == 1 and "password_hash" in acciones[0]                 # el rol ya lo puso la migracion
    primera = migrada.usuario("admin@libreria.com")
    assert primera[2] == 1 and primera[3] is True and passwords.verify_password("ClaveDelAdmin123", primera[4])

    with migrada.unit_of_work() as repo:
        assert crear_admin.asegurar_admin(repo, "admin@libreria.com", "OtraDistinta456")[1] == []
    assert migrada.usuario("admin@libreria.com") == primera
    assert migrada.usuario("maruchanvalo@gmail.com")[1:3] == (False, 2)           # sigue como cliente


# ------------------------------------------------------------------ API completa sobre PostgreSQL
@pytest.fixture
def api(migrada, monkeypatch, client):
    monkeypatch.setattr(repository, "unit_of_work", migrada.unit_of_work)
    return client


def test_api_flujo_completo_sobre_postgresql(api, migrada, sesion, confirmaciones):
    id_admin = migrada.usuario("admin@libreria.com")[0]
    admin = sesion(id_admin, 1)

    creado = api.post("/users", headers=admin, json={"nombre": "Nueva", "apellido_paterno": "Cuenta",
                                                      "email": "nueva@correo.com", "password": PASSWORD})
    assert creado.status_code == 201
    nuevo_id = creado.get_json()["id_usuario"]
    fila = migrada.usuario("nueva@correo.com")
    assert fila[5] == "confirmado" and passwords.verify_password(PASSWORD, fila[4])

    assert api.post("/users", headers=admin, json={"nombre": "Otra", "email": "NUEVA@correo.com",
                                                    "password": PASSWORD}).status_code == 409
    assert api.get("/users?q=nueva", headers=admin).get_json()["total"] == 1
    assert api.get("/roles", headers=admin).get_json()[0]["nombre"] == "admin"

    nueva = sesion(nuevo_id, 2)
    assert api.get("/users", headers=nueva).status_code == 403
    assert api.patch(f"/users/{nuevo_id}/password", headers=nueva,
                     json={"password_actual": PASSWORD, "password_nueva": "OtraClave456"}).status_code == 200
    assert api.get("/users/me", headers=nueva).status_code == 401                 # token anterior revocado
    assert passwords.verify_password("OtraClave456", migrada.usuario("nueva@correo.com")[4])

    assert api.patch(f"/users/{nuevo_id}/email", headers=admin, json={"email": "otra@correo.com"}).status_code == 200
    assert migrada.usuario("otra@correo.com")[5] == "pendiente" and confirmaciones[0][:2] == (nuevo_id, "otra@correo.com")

    assert api.delete(f"/users/{id_admin}", headers=admin).status_code == 409     # ultimo admin
    assert api.delete(f"/users/{nuevo_id}", headers=admin).get_json()["activo"] is False


def test_api_un_solo_admin_409_sobre_postgresql(api, migrada, sesion):
    admin = sesion(migrada.usuario("admin@libreria.com")[0], 1)
    id_maru = migrada.usuario("maruchanvalo@gmail.com")[0]
    resp = api.patch(f"/users/{id_maru}/role", json={"role_id": 1}, headers=admin)
    assert resp.status_code == 409 and resp.get_json()["error"] == "UN_SOLO_ADMIN"
    assert migrada.usuario("maruchanvalo@gmail.com")[1:3] == (False, 2)


def test_api_redis_caido_hace_rollback_en_postgresql(api, varios_admins, sesion, fake_redis):
    migrada = varios_admins
    admin = sesion(migrada.usuario("admin@libreria.com")[0], 1)
    id_maru = migrada.usuario("maruchanvalo@gmail.com")[0]
    antes = migrada.usuario("maruchanvalo@gmail.com")

    redis_client.set_client(RedisQueFallaAlRevocar(fake_redis))
    for metodo, ruta, cuerpo in (("patch", f"/users/{id_maru}/role", {"role_id": 1}),
                                 ("patch", f"/users/{id_maru}/password", {"password_nueva": "Restablecida123"}),
                                 ("delete", f"/users/{id_maru}", None)):
        assert getattr(api, metodo)(ruta, json=cuerpo, headers=admin).status_code == 503
    assert migrada.usuario("maruchanvalo@gmail.com") == antes
