"""
db/repository.py
Acceso a datos del microservicio tracking (psycopg 3, consultas
parametrizadas). Tablas propias: `envios` y `envio_posiciones`.
"""
from contextlib import contextmanager

from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from common.db import get_conn

COLUMNAS = ("id, codigo, pedido_id, user_id, ruta_id, estado, progreso, ultima_lat, ultima_lon, ultima_velocidad, "
            "ultimo_rumbo, ultima_posicion_en, estado_desde, pedido_estado_sync, sync_error, created_at, updated_at, "
            "entregado_en")
COLUMNAS_POSICION = "latitude, longitude, speed, heading, progreso, received_at"
_EDITABLES = {"estado", "progreso", "ultima_lat", "ultima_lon", "ultima_velocidad", "ultimo_rumbo",
              "ultima_posicion_en", "estado_desde", "pedido_estado_sync", "sync_error", "entregado_en"}


class _Ahora:
    """Marcador para update(): la columna toma NOW() de PostgreSQL (mismo reloj que vencidos())."""

    def __repr__(self):
        return "AHORA"


AHORA = _Ahora()


class EnvioDuplicado(Exception):
    """Ya existe un envio para ese pedido (uq_envios_pedido) o con ese codigo (uq_envios_codigo)."""


class TrackingRepository:
    def __init__(self, conn):
        self.conn = conn

    def _cur(self):
        return self.conn.cursor(row_factory=dict_row)

    # ------------------------------------------------------------ lectura
    def get_by_codigo(self, codigo, bloquear=False):
        sql = f"SELECT {COLUMNAS} FROM envios WHERE codigo = %s" + (" FOR UPDATE" if bloquear else "")
        return self._cur().execute(sql, (codigo,)).fetchone()

    def get_by_pedido(self, pedido_id):
        return self._cur().execute(f"SELECT {COLUMNAS} FROM envios WHERE pedido_id = %s", (pedido_id,)).fetchone()

    def list(self, user_id=None, estado=None, limit=20, offset=0):
        """(filas, total), los mas recientes primero."""
        condiciones, valores = ["TRUE"], []
        for columna, valor in (("user_id", user_id), ("estado", estado)):
            if valor is not None:
                condiciones.append(f"{columna} = %s")
                valores.append(valor)
        where = " AND ".join(condiciones)
        total = self.conn.execute(f"SELECT COUNT(*) FROM envios WHERE {where}", valores).fetchone()[0]
        filas = self._cur().execute(
            f"SELECT {COLUMNAS} FROM envios WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s",
            valores + [limit, offset]).fetchall()
        return filas, total

    def con_estado(self, estados):
        return self._cur().execute(
            f"SELECT {COLUMNAS} FROM envios WHERE estado = ANY(%s) ORDER BY id", (list(estados),)).fetchall()

    def vencidos(self, estado, segundos):
        """Envios que llevan al menos `segundos` en `estado` (bloqueados para cambiarlos)."""
        return self._cur().execute(
            f"SELECT {COLUMNAS} FROM envios WHERE estado = %s AND estado_desde <= NOW() - make_interval(secs => %s) "
            "ORDER BY id FOR UPDATE SKIP LOCKED", (estado, segundos)).fetchall()

    def pendientes_de_sincronizar(self, limite=50):
        """Envios cuyo estado (ENVIADO/EN_RUTA -> ENVIADO, ENTREGADO -> ENTREGADO) pedidos todavia no conoce."""
        return self._cur().execute(
            f"""
            SELECT {COLUMNAS} FROM envios
            WHERE sync_error IS NULL AND (
                  (estado IN ('ENVIADO', 'EN_RUTA') AND pedido_estado_sync IS NULL)
               OR (estado = 'ENTREGADO' AND pedido_estado_sync IS DISTINCT FROM 'ENTREGADO'))
            ORDER BY id LIMIT %s
            """, (limite,)).fetchall()

    def posiciones(self, envio_id, limite):
        """Ruta recorrida: las ultimas `limite` posiciones, de la mas vieja a la mas nueva."""
        return self._cur().execute(
            f"""
            SELECT {COLUMNAS_POSICION} FROM (
                SELECT id, {COLUMNAS_POSICION} FROM envio_posiciones WHERE envio_id = %s ORDER BY id DESC LIMIT %s
            ) ultimas ORDER BY id
            """, (envio_id, limite)).fetchall()

    # ------------------------------------------------------------ escritura
    def insert(self, codigo, pedido_id, user_id, ruta_id):
        try:
            return self._cur().execute(
                f"""
                INSERT INTO envios (codigo, pedido_id, user_id, ruta_id)
                VALUES (%s, %s, %s, %s)
                RETURNING {COLUMNAS}
                """, (codigo, pedido_id, user_id, ruta_id)).fetchone()
        except pg_errors.UniqueViolation:
            raise EnvioDuplicado()

    def update(self, envio_id, **campos):
        """Actualiza solo las columnas indicadas y devuelve la fila resultante."""
        desconocidas = set(campos) - _EDITABLES
        if desconocidas:
            raise ValueError(f"Columnas no editables: {sorted(desconocidas)}")
        asignaciones = "".join(f"{columna} = {'NOW()' if valor is AHORA else '%s'}, "
                               for columna, valor in campos.items())
        valores = [valor for valor in campos.values() if valor is not AHORA]
        return self._cur().execute(
            f"UPDATE envios SET {asignaciones}updated_at = NOW() WHERE id = %s RETURNING {COLUMNAS}",
            valores + [envio_id]).fetchone()

    def posicion_insert(self, envio_id, latitude, longitude, speed, heading, progreso, maximo):
        """Guarda la posicion y recorta la ruta recorrida a las ultimas `maximo`. Devuelve la fila guardada."""
        fila = self._cur().execute(
            f"""
            INSERT INTO envio_posiciones (envio_id, latitude, longitude, speed, heading, progreso)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING {COLUMNAS_POSICION}
            """, (envio_id, latitude, longitude, speed, heading, progreso)).fetchone()
        self.conn.execute(
            """
            DELETE FROM envio_posiciones
            WHERE envio_id = %s AND id <= (SELECT id FROM envio_posiciones WHERE envio_id = %s
                                           ORDER BY id DESC OFFSET %s LIMIT 1)
            """, (envio_id, envio_id, maximo))
        return fila


@contextmanager
def unit_of_work():
    """Una transaccion: COMMIT si el bloque termina bien, ROLLBACK si lanza."""
    with get_conn() as conn:
        yield TrackingRepository(conn)
