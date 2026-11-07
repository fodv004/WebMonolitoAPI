-- ============================================================
-- sql/001_libros_descripcion.sql    (migración 009_libros_descripcion)
-- Agrega a la tabla existente `libros` la columna opcional:
--
--   descripcion  TEXT NULL     sinopsis del libro para la app cliente
--
-- Cambio aditivo: no toca ninguna otra columna, y los INSERT existentes
-- (monolito, books, pruebas) usan lista de columnas, así que siguen
-- funcionando (la columna queda en NULL). Los permisos a nivel de tabla
-- (GRANT ... ON libros) ya cubren la columna nueva.
--
-- Idempotente y transaccional. Datos de ejemplo (opcional, a mano):
--   sql/seed_descripciones.sql
-- ============================================================
BEGIN;

CREATE TABLE IF NOT EXISTS schema_migraciones (
    version      VARCHAR(60) PRIMARY KEY,
    descripcion  TEXT        NOT NULL,
    aplicada_en  TIMESTAMP   NOT NULL DEFAULT NOW()
);

ALTER TABLE libros ADD COLUMN IF NOT EXISTS descripcion TEXT;

INSERT INTO schema_migraciones (version, descripcion)
VALUES ('009_libros_descripcion', 'books: columna opcional libros.descripcion (TEXT NULL)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
