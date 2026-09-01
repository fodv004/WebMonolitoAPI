-- ============================================================
-- Base de datos: Sistema de Gestión de Libros
-- Motor: PostgreSQL
-- Normalizado hasta 4NF (dependencias multivaluadas separadas)
-- ============================================================

-- ============================================================
-- 1. CATÁLOGOS INDEPENDIENTES
-- ============================================================

CREATE TABLE formatos (
    id_formato      SERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL UNIQUE  -- Ej: Tapa dura, Tapa blanda, Digital, Audiolibro
);

CREATE TABLE generos (
    id_genero       SERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL UNIQUE  -- catálogo de géneros/categorías
);

CREATE TABLE autores (
    id_autor        SERIAL PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL,
    nacionalidad    VARCHAR(80)
);

CREATE TABLE conceptos (
    id_concepto     SERIAL PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL UNIQUE  -- ej: "Realismo mágico"
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
-- El índice único parcial solo indexa filas con es_admin = TRUE,
-- por lo que Postgres rechaza un segundo INSERT/UPDATE con es_admin = TRUE.
CREATE UNIQUE INDEX un_solo_admin
    ON usuarios (es_admin)
    WHERE es_admin = TRUE;

-- ============================================================
-- 3. LIBROS (tabla principal, atributos con dependencia funcional simple)
-- ============================================================

CREATE TABLE libros (
    isbn                VARCHAR(13) PRIMARY KEY,   -- ISBN-13
    titulo              VARCHAR(255) NOT NULL,
    anio_publicacion    SMALLINT NOT NULL CHECK (anio_publicacion > 0),
    precio              NUMERIC(10,2) NOT NULL CHECK (precio >= 0),
    stock               INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    id_formato          INTEGER NOT NULL REFERENCES formatos(id_formato),
    fecha_creacion      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 4. RELACIONES MULTIVALUADAS (M:N) — resuelven las MVD detectadas
-- ============================================================

-- Libro <-> Autor
CREATE TABLE libro_autor (
    isbn        VARCHAR(13) REFERENCES libros(isbn) ON DELETE CASCADE,
    id_autor    INTEGER REFERENCES autores(id_autor) ON DELETE RESTRICT,
    PRIMARY KEY (isbn, id_autor)
);

-- Libro <-> Género
CREATE TABLE libro_genero (
    isbn        VARCHAR(13) REFERENCES libros(isbn) ON DELETE CASCADE,
    id_genero   INTEGER REFERENCES generos(id_genero) ON DELETE RESTRICT,
    PRIMARY KEY (isbn, id_genero)
);

-- Libro <-> Concepto, con atributo propio: la definición depende del par (libro, concepto)
CREATE TABLE libro_concepto (
    isbn         VARCHAR(13) REFERENCES libros(isbn) ON DELETE CASCADE,
    id_concepto  INTEGER REFERENCES conceptos(id_concepto) ON DELETE RESTRICT,
    definicion   TEXT NOT NULL,
    PRIMARY KEY (isbn, id_concepto)
);

-- Imágenes del libro (relación 1:N)
CREATE TABLE imagenes (
    id_imagen    SERIAL PRIMARY KEY,
    isbn         VARCHAR(13) NOT NULL REFERENCES libros(isbn) ON DELETE CASCADE,
    url          VARCHAR(500) NOT NULL,
    es_principal BOOLEAN NOT NULL DEFAULT FALSE,
    orden        SMALLINT DEFAULT 0
);

-- A lo sumo una imagen marcada como principal por libro
CREATE UNIQUE INDEX una_imagen_principal
    ON imagenes (isbn)
    WHERE es_principal = TRUE;

-- ============================================================
-- 5. ÍNDICES DE APOYO (mejoran JOINs y búsquedas frecuentes)
-- ============================================================

CREATE INDEX idx_libro_autor_autor      ON libro_autor(id_autor);
CREATE INDEX idx_libro_genero_genero    ON libro_genero(id_genero);
CREATE INDEX idx_libro_concepto_concepto ON libro_concepto(id_concepto);
CREATE INDEX idx_imagenes_isbn          ON imagenes(isbn);
CREATE INDEX idx_libros_titulo          ON libros(titulo);

-- ============================================================
-- 6. DATOS DE EJEMPLO (opcional, para probar el modelo)
-- ============================================================

INSERT INTO formatos (nombre) VALUES ('Tapa dura'), ('Tapa blanda'), ('Digital'), ('Audiolibro');
INSERT INTO generos (nombre) VALUES ('Ficción'), ('Ciencia'), ('Historia'), ('Realismo mágico');
INSERT INTO autores (nombre, nacionalidad) VALUES ('Gabriel García Márquez', 'Colombiana'), ('Isabel Allende', 'Chilena');
INSERT INTO conceptos (nombre) VALUES ('Realismo mágico'), ('Soledad'), ('Memoria histórica');

INSERT INTO usuarios (nombre, correo, password_hash, es_admin)
VALUES ('Admin Principal', 'admin@libreria.com', 'hash_de_ejemplo', TRUE);

-- Usuario de demostración con contraseña SIN hashear (texto plano).
-- El login detecta que password_hash no tiene formato bcrypt y compara en texto plano,
-- permitiendo entrar al catálogo/búsqueda sin depender de un hash generado previamente.
-- Uso exclusivo de pruebas/demo: no usar este patrón para cuentas reales en producción.
INSERT INTO usuarios (nombre, correo, password_hash, es_admin)
VALUES ('Usuario Demo', 'demo@libreria.com', 'demo1234', FALSE);

INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, id_formato)
VALUES ('9780307474728', 'Cien años de soledad', 1967, 350.00, 20, 1);

INSERT INTO libro_autor (isbn, id_autor) VALUES ('9780307474728', 1);
INSERT INTO libro_genero (isbn, id_genero) VALUES ('9780307474728', 1), ('9780307474728', 4);
INSERT INTO libro_concepto (isbn, id_concepto, definicion)
VALUES ('9780307474728', 1, 'Técnica narrativa donde eventos fantásticos se presentan como parte de la realidad cotidiana, característica del estilo de García Márquez en esta obra.');
INSERT INTO imagenes (isbn, url, es_principal) VALUES ('9780307474728', '/img/cien-anos-portada.jpg', TRUE);
