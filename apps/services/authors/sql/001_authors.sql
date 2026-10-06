-- ============================================================
-- sql/001_authors.sql            (migración 005_authors)
-- Tablas propias del microservicio authors:
--
--   authors       (id, nombre, apellido, nacionalidad, fecha_nacimiento,
--                  biografia, created_at, updated_at)
--   author_books  (author_id, isbn, orden)   PK compuesta (author_id, isbn)
--
-- author_books.isbn NO tiene llave foránea a libros: los libros son del
-- microservicio books. Antes de crear una relación, authors valida por
-- HTTP que el libro exista (GET {BOOKS_URL}/books/{isbn}).
-- `orden` es la posición del autor entre los autores de ese libro (1 = primero).
--
-- Carga inicial (solo la primera vez): copia los autores y las relaciones
-- que ya existían en las tablas del monolito (autores, libro_autor) para
-- no empezar vacío. Esas tablas NO se modifican ni se borran: el monolito
-- y el campo "autor" de books las siguen usando. El nombre completo se
-- copia tal cual a `nombre` (apellido queda NULL): partirlo sin conocer
-- cada caso daría apellidos equivocados; se corrige editando el autor.
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

CREATE TEMP TABLE _mig_authors_ctx ON COMMIT DROP AS
SELECT NOT EXISTS (
           SELECT 1 FROM schema_migraciones WHERE version = '005_authors'
       ) AS pendiente;

-- ------------------------------------------------------------
-- 1. Tablas
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS authors (
    id                SERIAL PRIMARY KEY,
    nombre            VARCHAR(150) NOT NULL CONSTRAINT chk_authors_nombre_no_vacio CHECK (btrim(nombre) <> ''),
    apellido          VARCHAR(150),
    nacionalidad      VARCHAR(80),
    fecha_nacimiento  DATE,
    biografia         TEXT,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS author_books (
    author_id  INTEGER     NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    isbn       VARCHAR(13) NOT NULL,            -- sin FK: el libro vive en el microservicio books
    orden      INTEGER     NOT NULL DEFAULT 1 CONSTRAINT chk_author_books_orden CHECK (orden >= 1),
    PRIMARY KEY (author_id, isbn)
);

CREATE INDEX IF NOT EXISTS idx_author_books_isbn ON author_books(isbn);
CREATE INDEX IF NOT EXISTS idx_authors_nacionalidad ON authors(lower(nacionalidad));

-- ------------------------------------------------------------
-- 2. Carga inicial desde las tablas del monolito (si existen)
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT (SELECT pendiente FROM _mig_authors_ctx) OR to_regclass('autores') IS NULL THEN
        RETURN;
    END IF;

    -- Se conserva el mismo id que en `autores` para poder rastrear cada registro.
    INSERT INTO authors (id, nombre, nacionalidad)
    SELECT id_autor, btrim(nombre), NULLIF(btrim(nacionalidad), '')
      FROM autores
     WHERE btrim(nombre) <> ''
    ON CONFLICT (id) DO NOTHING;

    IF EXISTS (SELECT 1 FROM authors) THEN
        PERFORM setval(pg_get_serial_sequence('authors', 'id'), (SELECT MAX(id) FROM authors));
    END IF;

    IF to_regclass('libro_autor') IS NOT NULL THEN
        INSERT INTO author_books (author_id, isbn, orden)
        SELECT la.id_autor, la.isbn, ROW_NUMBER() OVER (PARTITION BY la.isbn ORDER BY la.id_autor)
          FROM libro_autor la
          JOIN authors a ON a.id = la.id_autor
        ON CONFLICT (author_id, isbn) DO NOTHING;
    END IF;
END $$;

INSERT INTO schema_migraciones (version, descripcion)
VALUES ('005_authors', 'authors: tablas authors y author_books (carga inicial desde autores y libro_autor)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
