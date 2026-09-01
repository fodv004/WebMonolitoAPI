-- ============================================================
-- 01_schema.sql
-- Tablas, PK, FK, UNIQUE, CHECK e índices.
-- Normalizado hasta 4FN (dependencias multivaluadas separadas).
-- ============================================================

-- ============================================================
-- 1. CATÁLOGOS INDEPENDIENTES
-- ============================================================

CREATE TABLE formatos (
    id_formato      SERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE generos (
    id_genero       SERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE autores (
    id_autor        SERIAL PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL,
    nacionalidad    VARCHAR(80)
);

CREATE TABLE conceptos (
    id_concepto     SERIAL PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL UNIQUE
);

-- ============================================================
-- 2. USUARIOS REGISTRADOS
-- ============================================================

CREATE TABLE usuarios (
    id_usuario      SERIAL PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL,
    correo          VARCHAR(150) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    es_admin        BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_registro  TIMESTAMP NOT NULL DEFAULT NOW(),
    activo          BOOLEAN NOT NULL DEFAULT TRUE
);

-- Regla de negocio: como máximo un administrador en todo el sistema.
CREATE UNIQUE INDEX un_solo_admin
    ON usuarios (es_admin)
    WHERE es_admin = TRUE;

-- ============================================================
-- 3. LIBROS
-- ============================================================

CREATE TABLE libros (
    isbn                VARCHAR(13) PRIMARY KEY,
    titulo              VARCHAR(255) NOT NULL,
    anio_publicacion    SMALLINT NOT NULL CHECK (anio_publicacion > 0),
    precio              NUMERIC(10,2) NOT NULL CHECK (precio >= 0),
    stock               INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    id_formato          INTEGER NOT NULL REFERENCES formatos(id_formato),
    fecha_creacion      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 4. RELACIONES MULTIVALUADAS (M:N)
-- ============================================================

CREATE TABLE libro_autor (
    isbn        VARCHAR(13) REFERENCES libros(isbn) ON DELETE CASCADE,
    id_autor    INTEGER REFERENCES autores(id_autor) ON DELETE RESTRICT,
    PRIMARY KEY (isbn, id_autor)
);

CREATE TABLE libro_genero (
    isbn        VARCHAR(13) REFERENCES libros(isbn) ON DELETE CASCADE,
    id_genero   INTEGER REFERENCES generos(id_genero) ON DELETE RESTRICT,
    PRIMARY KEY (isbn, id_genero)
);

CREATE TABLE libro_concepto (
    isbn         VARCHAR(13) REFERENCES libros(isbn) ON DELETE CASCADE,
    id_concepto  INTEGER REFERENCES conceptos(id_concepto) ON DELETE RESTRICT,
    definicion   TEXT NOT NULL,
    PRIMARY KEY (isbn, id_concepto)
);

CREATE TABLE imagenes (
    id_imagen    SERIAL PRIMARY KEY,
    isbn         VARCHAR(13) NOT NULL REFERENCES libros(isbn) ON DELETE CASCADE,
    url          VARCHAR(500) NOT NULL,
    es_principal BOOLEAN NOT NULL DEFAULT FALSE,
    orden        SMALLINT  -- sin DEFAULT: el trigger trg_auto_orden_imagen (05_triggers.sql)
                            -- calcula el siguiente valor cuando se inserta sin especificarlo
);

CREATE UNIQUE INDEX una_imagen_principal
    ON imagenes (isbn)
    WHERE es_principal = TRUE;

-- ============================================================
-- 5. ÍNDICES DE APOYO
-- ============================================================

CREATE INDEX idx_libro_autor_autor       ON libro_autor(id_autor);
CREATE INDEX idx_libro_genero_genero     ON libro_genero(id_genero);
CREATE INDEX idx_libro_concepto_concepto ON libro_concepto(id_concepto);
CREATE INDEX idx_imagenes_isbn           ON imagenes(isbn);
CREATE INDEX idx_libros_titulo           ON libros(titulo);
