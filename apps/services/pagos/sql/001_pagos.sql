-- ============================================================
-- sql/001_pagos.sql            (migración 007_pagos)
-- Tabla propia del microservicio pagos (pago SIMULADO, sin pasarela real):
--
--   pagos (id, pedido_id, user_id, monto, metodo, estado, referencia,
--          ultimos4, idempotency_key UNIQUE, sincronizado, notas, activo,
--          created_at, updated_at)
--
--   metodo  TARJETA_SIMULADA | TRANSFERENCIA | EFECTIVO
--   estado  APROBADO | RECHAZADO | REEMBOLSADO
--
-- Datos de tarjeta: NUNCA se guarda el número completo ni el CVV. Solo
-- `ultimos4` (los últimos 4 dígitos), que basta para el comprobante.
--
-- Sin llaves foráneas hacia otros servicios: pedido_id es de pedidos y
-- user_id es de users; el pedido se valida por HTTP al pagar.
--
-- sincronizado: TRUE cuando el microservicio pedidos ya conoce el
--   resultado (pedido en PAGADO). FALSE = pago aprobado que todavía no se
--   pudo avisar a pedidos; lo reintenta la tarea en segundo plano.
-- activo: borrado lógico (DELETE /pagos/{id}, solo pagos RECHAZADO).
--
-- Ejecutar como library_user sobre la base `library`, o con
-- scripts/levantar_servicios.sh:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f 001_pagos.sql
-- Transaccional e idempotente. No toca ninguna tabla existente.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migraciones (
    version      VARCHAR(60) PRIMARY KEY,
    descripcion  TEXT        NOT NULL,
    aplicada_en  TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pagos (
    id               SERIAL PRIMARY KEY,
    pedido_id        INTEGER       NOT NULL,              -- sin FK: el pedido vive en pedidos
    user_id          INTEGER       NOT NULL,              -- sin FK: el usuario vive en users
    monto            NUMERIC(12,2) NOT NULL CONSTRAINT chk_pagos_monto CHECK (monto >= 0),
    metodo           VARCHAR(20)   NOT NULL
                     CONSTRAINT chk_pagos_metodo CHECK (metodo IN ('TARJETA_SIMULADA', 'TRANSFERENCIA', 'EFECTIVO')),
    estado           VARCHAR(15)   NOT NULL
                     CONSTRAINT chk_pagos_estado CHECK (estado IN ('APROBADO', 'RECHAZADO', 'REEMBOLSADO')),
    referencia       VARCHAR(40)   NOT NULL,
    ultimos4         CHAR(4)       CONSTRAINT chk_pagos_ultimos4 CHECK (ultimos4 ~ '^[0-9]{4}$'),
    idempotency_key  VARCHAR(100)  NOT NULL CONSTRAINT uq_pagos_idempotency_key UNIQUE,
    sincronizado     BOOLEAN       NOT NULL DEFAULT FALSE,
    notas            TEXT,
    activo           BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pagos_pedido ON pagos(pedido_id);
CREATE INDEX IF NOT EXISTS idx_pagos_user   ON pagos(user_id);

-- Un pedido no puede tener dos pagos aprobados: última barrera contra el doble cobro
-- (antes están la llave de idempotencia y el lock de Redis).
CREATE UNIQUE INDEX IF NOT EXISTS uq_pagos_pedido_aprobado ON pagos(pedido_id) WHERE estado = 'APROBADO';

-- Lo que revisa la tarea de sincronización.
CREATE INDEX IF NOT EXISTS idx_pagos_por_sincronizar ON pagos(id) WHERE NOT sincronizado AND estado = 'APROBADO';

INSERT INTO schema_migraciones (version, descripcion)
VALUES ('007_pagos', 'pagos: tabla pagos (pago simulado, idempotencia y sincronización con pedidos)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
