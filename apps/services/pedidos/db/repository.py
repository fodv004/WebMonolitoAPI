"""
db/repository.py
Acceso a datos del microservicio pedidos (psycopg 3, consultas
parametrizadas). Tablas propias: inventario, pedidos, pedido_lineas y
pedido_historial.

Aqui no hay reglas de negocio: solo operaciones pequeñas que
services/ combina dentro de una transaccion (unit_of_work). Los bloqueos
(SELECT ... FOR UPDATE) siempre se toman en el mismo orden -primero el
pedido, despues las filas de inventario ordenadas por isbn- para que dos
peticiones simultaneas no se bloqueen entre si.
"""
from contextlib import contextmanager

from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from common.db import get_conn

_PEDIDO = "p.id, p.user_id, p.estado, p.total, p.created_at, p.updated_at, p.expira_en"
_CON_ARTICULOS = (f"{_PEDIDO}, (SELECT COALESCE(SUM(l.cantidad), 0) FROM pedido_lineas l "
                  "WHERE l.pedido_id = p.id) AS articulos")
_INVENTARIO = "isbn, stock_disponible, stock_reservado, updated_at"


class InventarioDuplicado(Exception):
    pass


class PedidosRepository:
    def __init__(self, conn):
        self.conn = conn

    def _cur(self):
        return self.conn.cursor(row_factory=dict_row)

    def ahora(self):
        """Hora de PostgreSQL (la misma con la que se calcula expira_en)."""
        return self.conn.execute("SELECT NOW()::timestamp").fetchone()[0]

    # ------------------------------------------------------------ inventario
    def inventario_get(self, isbn):
        return self._cur().execute(f"SELECT {_INVENTARIO} FROM inventario WHERE isbn = %s", (isbn,)).fetchone()

    def inventario_list(self, limit=100, offset=0):
        total = self.conn.execute("SELECT COUNT(*) FROM inventario").fetchone()[0]
        filas = self._cur().execute(
            f"SELECT {_INVENTARIO} FROM inventario ORDER BY isbn LIMIT %s OFFSET %s", (limit, offset)).fetchall()
        return filas, total

    def inventario_bloquear(self, isbns):
        """{isbn: fila} de los ISBN pedidos, BLOQUEADOS (FOR UPDATE) y siempre en orden de isbn."""
        filas = self._cur().execute(
            f"SELECT {_INVENTARIO} FROM inventario WHERE isbn = ANY(%s) ORDER BY isbn FOR UPDATE",
            (sorted(set(isbns)),)).fetchall()
        return {fila["isbn"]: fila for fila in filas}

    def inventario_ajustar(self, isbn, disponible=0, reservado=0):
        """Suma (o resta) unidades. La fila debe estar bloqueada; los CHECK impiden negativos."""
        self.conn.execute(
            "UPDATE inventario SET stock_disponible = stock_disponible + %s, "
            "stock_reservado = stock_reservado + %s, updated_at = NOW() WHERE isbn = %s",
            (disponible, reservado, isbn))

    def inventario_insert(self, isbn, stock_disponible):
        try:
            return self._cur().execute(
                f"INSERT INTO inventario (isbn, stock_disponible) VALUES (%s, %s) RETURNING {_INVENTARIO}",
                (isbn, stock_disponible)).fetchone()
        except pg_errors.UniqueViolation:
            raise InventarioDuplicado()

    def inventario_fijar_disponible(self, isbn, stock_disponible):
        return self._cur().execute(
            f"UPDATE inventario SET stock_disponible = %s, updated_at = NOW() WHERE isbn = %s RETURNING {_INVENTARIO}",
            (stock_disponible, isbn)).fetchone()

    def inventario_delete(self, isbn):
        return self.conn.execute("DELETE FROM inventario WHERE isbn = %s", (isbn,)).rowcount > 0

    # ------------------------------------------------------------ pedidos
    def pedido_insert(self, user_id, total, minutos_de_reserva):
        return self._cur().execute(
            f"""
            INSERT INTO pedidos AS p (user_id, estado, total, expira_en)
            VALUES (%s, 'PENDIENTE_PAGO', %s, NOW() + %s * INTERVAL '1 minute')
            RETURNING {_PEDIDO}
            """,
            (user_id, total, minutos_de_reserva)).fetchone()

    def pedido_get(self, pedido_id, bloquear=False):
        """El pedido (sin los borrados logicamente), opcionalmente bloqueado para modificarlo."""
        sql = (f"SELECT {_PEDIDO} FROM pedidos p WHERE p.id = %s AND p.eliminado_en IS NULL"
               + (" FOR UPDATE" if bloquear else ""))
        return self._cur().execute(sql, (pedido_id,)).fetchone()

    def pedido_list(self, user_id=None, estado=None, limit=20, offset=0):
        """(filas, total), los mas recientes primero."""
        condiciones, valores = ["p.eliminado_en IS NULL"], []
        if user_id is not None:
            condiciones.append("p.user_id = %s")
            valores.append(user_id)
        if estado is not None:
            condiciones.append("p.estado = %s")
            valores.append(estado)
        where = " AND ".join(condiciones)
        total = self.conn.execute(f"SELECT COUNT(*) FROM pedidos p WHERE {where}", valores).fetchone()[0]
        filas = self._cur().execute(
            f"SELECT {_CON_ARTICULOS} FROM pedidos p WHERE {where} ORDER BY p.id DESC LIMIT %s OFFSET %s",
            valores + [limit, offset]).fetchall()
        return filas, total

    def pedido_cambiar_estado(self, pedido_id, estado):
        self.conn.execute("UPDATE pedidos SET estado = %s, updated_at = NOW() WHERE id = %s", (estado, pedido_id))

    def pedido_fijar_total(self, pedido_id, total):
        self.conn.execute("UPDATE pedidos SET total = %s, updated_at = NOW() WHERE id = %s", (total, pedido_id))

    def pedido_eliminar(self, pedido_id):
        """Borrado logico."""
        self.conn.execute("UPDATE pedidos SET eliminado_en = NOW(), updated_at = NOW() WHERE id = %s", (pedido_id,))

    def pedidos_vencidos(self, limite=100):
        """ids de pedidos PENDIENTE_PAGO con la reserva vencida, ya bloqueados. SKIP LOCKED: los
        que otra peticion esta modificando ahora mismo (p. ej. un pago) se dejan para la siguiente vuelta."""
        filas = self.conn.execute(
            "SELECT id FROM pedidos WHERE estado = 'PENDIENTE_PAGO' AND expira_en <= NOW() "
            "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED", (limite,)).fetchall()
        return [fila[0] for fila in filas]

    # ------------------------------------------------------------ lineas e historial
    def lineas_get(self, pedido_id):
        return self._cur().execute(
            "SELECT isbn, titulo, cantidad, precio_unitario, subtotal FROM pedido_lineas "
            "WHERE pedido_id = %s ORDER BY id", (pedido_id,)).fetchall()

    def lineas_reemplazar(self, pedido_id, lineas):
        """Sustituye todas las lineas del pedido por `lineas` (dicts con isbn, titulo, cantidad,
        precio_unitario y subtotal)."""
        self.conn.execute("DELETE FROM pedido_lineas WHERE pedido_id = %s", (pedido_id,))
        with self.conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO pedido_lineas (pedido_id, isbn, titulo, cantidad, precio_unitario, subtotal) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [(pedido_id, l["isbn"], l["titulo"], l["cantidad"], l["precio_unitario"], l["subtotal"])
                 for l in lineas])

    def historial_insert(self, pedido_id, estado_anterior, estado_nuevo, actor):
        self.conn.execute(
            "INSERT INTO pedido_historial (pedido_id, estado_anterior, estado_nuevo, actor) VALUES (%s, %s, %s, %s)",
            (pedido_id, estado_anterior, estado_nuevo, actor))

    def historial_get(self, pedido_id):
        return self._cur().execute(
            "SELECT estado_anterior, estado_nuevo, actor, fecha FROM pedido_historial "
            "WHERE pedido_id = %s ORDER BY id", (pedido_id,)).fetchall()


@contextmanager
def unit_of_work():
    """Una transaccion: COMMIT si el bloque termina bien, ROLLBACK si lanza."""
    with get_conn() as conn:
        yield PedidosRepository(conn)
