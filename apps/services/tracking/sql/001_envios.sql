-- ============================================================
-- sql/001_envios.sql           (migración 008_envios)
-- Tablas propias del microservicio tracking:
--
--   envios (id, codigo UNIQUE, pedido_id UNIQUE, user_id, ruta_id, estado,
--           progreso, ultima_lat, ultima_lon, ultima_velocidad, ultimo_rumbo,
--           ultima_posicion_en, estado_desde, pedido_estado_sync, sync_error,
--           created_at, updated_at, entregado_en)
--   envio_posiciones (id, envio_id, latitude, longitude, speed, heading,
--                     progreso, received_at)   -- ruta recorrida, últimas 500
--
--   codigo  LIB-MTY-<año>-<pedido_id con 6 dígitos>, uno por pedido
--   estado  CONFIRMADO -> PREPARANDO -> ENVIADO   (por tiempo)
--           ENVIADO -> EN_RUTA                    (primera posición del simulador)
--           EN_RUTA -> ENTREGADO                  (posición final a < 30 m del último punto)
--
-- Sin llaves foráneas hacia otros servicios: pedido_id es de pedidos y
-- user_id es de users; el pedido se valida por HTTP al crear el envío.
--
-- pedido_estado_sync: último estado que pedidos YA conoce (NULL, ENVIADO
--   o ENTREGADO). Si pedidos no respondió, la tarea en segundo plano lo
--   reintenta. sync_error: pedidos rechazó la transición (409) y no se
--   reintenta más (por ejemplo, el pedido fue cancelado).
--
-- Idempotente y transaccional.
-- ============================================================
BEGIN;

CREATE TABLE IF NOT EXISTS schema_migraciones (
    version      VARCHAR(60) PRIMARY KEY,
    descripcion  TEXT        NOT NULL,
    aplicada_en  TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS envios (
    id                  SERIAL PRIMARY KEY,
    codigo              VARCHAR(30)  NOT NULL CONSTRAINT uq_envios_codigo UNIQUE,
    pedido_id           INTEGER      NOT NULL CONSTRAINT uq_envios_pedido UNIQUE,   -- sin FK: vive en pedidos
    user_id             INTEGER      NOT NULL,                                       -- sin FK: vive en users
    ruta_id             VARCHAR(60)  NOT NULL,                                       -- clave en tracking/rutas.json
    estado              VARCHAR(15)  NOT NULL DEFAULT 'CONFIRMADO'
                        CONSTRAINT chk_envios_estado CHECK (estado IN
                            ('CONFIRMADO', 'PREPARANDO', 'ENVIADO', 'EN_RUTA', 'ENTREGADO')),
    progreso            NUMERIC(5,4) NOT NULL DEFAULT 0
                        CONSTRAINT chk_envios_progreso CHECK (progreso >= 0 AND progreso <= 1),
    ultima_lat          DOUBLE PRECISION,
    ultima_lon          DOUBLE PRECISION,
    ultima_velocidad    DOUBLE PRECISION,
    ultimo_rumbo        DOUBLE PRECISION,
    ultima_posicion_en  TIMESTAMP,
    estado_desde        TIMESTAMP    NOT NULL DEFAULT NOW(),
    pedido_estado_sync  VARCHAR(15),
    sync_error          TEXT,
    created_at          TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP    NOT NULL DEFAULT NOW(),
    entregado_en        TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_envios_user ON envios(user_id);
CREATE INDEX IF NOT EXISTS idx_envios_estado ON envios(estado) WHERE estado <> 'ENTREGADO';

CREATE TABLE IF NOT EXISTS envio_posiciones (
    id           BIGSERIAL PRIMARY KEY,
    envio_id     INTEGER          NOT NULL REFERENCES envios(id) ON DELETE CASCADE,
    latitude     DOUBLE PRECISION NOT NULL,
    longitude    DOUBLE PRECISION NOT NULL,
    speed        DOUBLE PRECISION NOT NULL,
    heading      DOUBLE PRECISION NOT NULL,
    progreso     NUMERIC(5,4)     NOT NULL,
    received_at  TIMESTAMP        NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_posiciones_envio ON envio_posiciones(envio_id, id);

INSERT INTO schema_migraciones (version, descripcion)
VALUES ('008_envios', 'tracking: envios y envio_posiciones (rastreo de pedidos pagados)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
