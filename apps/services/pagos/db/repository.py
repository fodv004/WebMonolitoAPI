"""
db/repository.py
Acceso a datos del microservicio pagos (psycopg 3, consultas
parametrizadas). Tabla propia: `pagos`.

Aqui nunca llega un numero de tarjeta ni un CVV: la unica columna con
datos de tarjeta es `ultimos4`.
"""
from contextlib import contextmanager

from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from common.db import get_conn

COLUMNAS = ("id, pedido_id, user_id, monto, metodo, estado, referencia, ultimos4, idempotency_key, "
            "sincronizado, notas, activo, created_at, updated_at")
_EDITABLES = {"estado", "referencia", "notas", "sincronizado", "activo"}      # el monto NUNCA se edita


class LlaveDuplicada(Exception):
    """Ya existe un pago con esa idempotency_key."""


class PedidoYaPagado(Exception):
    """El pedido ya tiene un pago APROBADO (indice unico uq_pagos_pedido_aprobado)."""


class PagosRepository:
    def __init__(self, conn):
        self.conn = conn

    def _cur(self):
        return self.conn.cursor(row_factory=dict_row)

    # ------------------------------------------------------------ lectura
    def get(self, pago_id, bloquear=False):
        """El pago (sin los borrados logicamente), opcionalmente bloqueado para modificarlo."""
        sql = f"SELECT {COLUMNAS} FROM pagos WHERE id = %s AND activo" + (" FOR UPDATE" if bloquear else "")
        return self._cur().execute(sql, (pago_id,)).fetchone()

    def get_by_key(self, idempotency_key):
        """Busca por llave de idempotencia (incluye los borrados: la llave sigue ocupada)."""
        return self._cur().execute(
            f"SELECT {COLUMNAS} FROM pagos WHERE idempotency_key = %s", (idempotency_key,)).fetchone()

    def aprobado_de_pedido(self, pedido_id):
        return self._cur().execute(
            f"SELECT {COLUMNAS} FROM pagos WHERE pedido_id = %s AND estado = 'APROBADO' AND activo",
            (pedido_id,)).fetchone()

    def de_pedido(self, pedido_id):
        return self._cur().execute(
            f"SELECT {COLUMNAS} FROM pagos WHERE pedido_id = %s AND activo ORDER BY id DESC", (pedido_id,)).fetchall()

    def list(self, user_id=None, estado=None, metodo=None, limit=20, offset=0):
        """(filas, total), los mas recientes primero."""
        condiciones, valores = ["activo"], []
        for columna, valor in (("user_id", user_id), ("estado", estado), ("metodo", metodo)):
            if valor is not None:
                condiciones.append(f"{columna} = %s")
                valores.append(valor)
        where = " AND ".join(condiciones)
        total = self.conn.execute(f"SELECT COUNT(*) FROM pagos WHERE {where}", valores).fetchone()[0]
        filas = self._cur().execute(
            f"SELECT {COLUMNAS} FROM pagos WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s",
            valores + [limit, offset]).fetchall()
        return filas, total

    def pendientes_de_sincronizar(self, limite=50):
        """Pagos APROBADO que pedidos todavia no conoce."""
        return self._cur().execute(
            f"SELECT {COLUMNAS} FROM pagos WHERE NOT sincronizado AND estado = 'APROBADO' AND activo "
            "ORDER BY id LIMIT %s", (limite,)).fetchall()

    # ------------------------------------------------------------ escritura
    def insert(self, pedido_id, user_id, monto, metodo, estado, referencia, ultimos4, idempotency_key,
               sincronizado):
        try:
            return self._cur().execute(
                f"""
                INSERT INTO pagos (pedido_id, user_id, monto, metodo, estado, referencia, ultimos4,
                                   idempotency_key, sincronizado)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {COLUMNAS}
                """,
                (pedido_id, user_id, monto, metodo, estado, referencia, ultimos4, idempotency_key, sincronizado),
            ).fetchone()
        except pg_errors.UniqueViolation as e:
            if e.diag.constraint_name == "uq_pagos_pedido_aprobado":
                raise PedidoYaPagado()
            raise LlaveDuplicada()

    def update(self, pago_id, **campos):
        """Actualiza solo las columnas indicadas y devuelve la fila resultante."""
        desconocidas = set(campos) - _EDITABLES
        if desconocidas:
            raise ValueError(f"Columnas no editables: {sorted(desconocidas)}")
        asignaciones = "".join(f"{columna} = %s, " for columna in campos)
        return self._cur().execute(
            f"UPDATE pagos SET {asignaciones}updated_at = NOW() WHERE id = %s RETURNING {COLUMNAS}",
            list(campos.values()) + [pago_id]).fetchone()


@contextmanager
def unit_of_work():
    """Una transaccion: COMMIT si el bloque termina bien, ROLLBACK si lanza."""
    with get_conn() as conn:
        yield PagosRepository(conn)
