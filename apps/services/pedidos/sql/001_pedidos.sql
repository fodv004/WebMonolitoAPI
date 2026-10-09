-- ============================================================
-- sql/001_pedidos.sql            (migración 006_pedidos)
-- Tablas propias del microservicio pedidos:
--
--   pedidos           (id, user_id, estado, total, created_at, updated_at, expira_en, eliminado_en)
--   pedido_lineas     (id, pedido_id, isbn, titulo, cantidad, precio_unitario, subtotal)
--   pedido_historial  (id, pedido_id, estado_anterior, estado_nuevo, actor, fecha)
--
-- Sin llaves foráneas hacia otros servicios: user_id es de users e isbn es
-- de books; se validan por HTTP al crear el pedido. El título y el precio
-- se COPIAN a pedido_lineas: un pedido no cambia si después cambia el libro.
--
-- Stock: NO hay tabla de inventario. El stock real es libros.stock y lo mueve el
-- microservicio books (POST /books/internal/stock/reservar y /liberar): pedidos
-- lo llama al crear, cancelar o expirar un pedido.
--
-- pedidos.eliminado_en: borrado lógico (DELETE /pedidos/{id}); NULL = visible.
--
-- Ejecutar como library_user, o con scripts/levantar_servicios.sh:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f 001_pedidos.sql
-- Transaccional e idempotente.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migraciones (
    version      VARCHAR(60) PRIMARY KEY,
    descripcion  TEXT        NOT NULL,
    aplicada_en  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Pedidos, líneas e historial
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pedidos (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER       NOT NULL,                -- sin FK: el usuario vive en users
    estado        VARCHAR(20)   NOT NULL DEFAULT 'PENDIENTE_PAGO'
                  CONSTRAINT chk_pedidos_estado CHECK (estado IN
                      ('PENDIENTE_PAGO', 'PAGADO', 'ENVIADO', 'ENTREGADO', 'CANCELADO', 'EXPIRADO')),
    total         NUMERIC(12,2) NOT NULL DEFAULT 0 CONSTRAINT chk_pedidos_total CHECK (total >= 0),
    created_at    TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP     NOT NULL DEFAULT NOW(),
    expira_en     TIMESTAMP     NOT NULL,                -- fin de la reserva de stock (PENDIENTE_PAGO)
    eliminado_en  TIMESTAMP                              -- borrado lógico
);

CREATE INDEX IF NOT EXISTS idx_pedidos_user ON pedidos(user_id);
-- Lo que revisa la tarea de expiración cada minuto.
CREATE INDEX IF NOT EXISTS idx_pedidos_por_expirar ON pedidos(expira_en) WHERE estado = 'PENDIENTE_PAGO';

CREATE TABLE IF NOT EXISTS pedido_lineas (
    id               SERIAL PRIMARY KEY,
    pedido_id        INTEGER       NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    isbn             VARCHAR(13)   NOT NULL,
    titulo           VARCHAR(255)  NOT NULL,             -- copiado de books al crear el pedido
    cantidad         INTEGER       NOT NULL CONSTRAINT chk_lineas_cantidad CHECK (cantidad > 0),
    precio_unitario  NUMERIC(10,2) NOT NULL CONSTRAINT chk_lineas_precio CHECK (precio_unitario >= 0),
    subtotal         NUMERIC(12,2) NOT NULL,
    CONSTRAINT uq_pedido_isbn UNIQUE (pedido_id, isbn)
);

CREATE TABLE IF NOT EXISTS pedido_historial (
    id               SERIAL PRIMARY KEY,
    pedido_id        INTEGER     NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    estado_anterior  VARCHAR(20),                        -- NULL en la creación
    estado_nuevo     VARCHAR(20) NOT NULL,
    actor            VARCHAR(60) NOT NULL,               -- user:<id>, admin:<id>, servicio:pagos, sistema:expiracion
    fecha            TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_historial_pedido ON pedido_historial(pedido_id);

INSERT INTO schema_migraciones (version, descripcion)
VALUES ('006_pedidos', 'pedidos: pedidos, pedido_lineas y pedido_historial (el stock es libros.stock, en books)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
