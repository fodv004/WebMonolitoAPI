-- ============================================================
-- sql/001_authors.sql            (migración 005_authors)
-- El microservicio authors NO crea tablas: usa las que ya existen en la
-- base `library`:
--
--   autores      (id_autor, nombre, nacionalidad)
--   libro_autor  (isbn, id_autor)      id_autor con ON DELETE RESTRICT
--
-- Esta migración solo deja constancia en schema_migraciones.
--
-- Ejecutar como library_user, o con scripts/levantar_servicios.sh:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f 001_authors.sql
-- Transaccional e idempotente.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migraciones (
    version      VARCHAR(60) PRIMARY KEY,
    descripcion  TEXT        NOT NULL,
    aplicada_en  TIMESTAMP   NOT NULL DEFAULT NOW()
);

INSERT INTO schema_migraciones (version, descripcion)
VALUES ('005_authors', 'authors: usa las tablas existentes autores y libro_autor (no crea tablas)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
