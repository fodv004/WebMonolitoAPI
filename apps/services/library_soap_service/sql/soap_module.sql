-- ============================================================
-- sql/soap_module.sql
-- Tablas propias del módulo SOAP de clasificación.
-- NO modifica ninguna tabla del monolito (libros, conceptos,
-- libro_concepto, generos, usuarios). Solo referencia libros.isbn
-- y conceptos.id_concepto vía FK (solo lectura hacia esas tablas).
-- ============================================================

-- ============================================================
-- 1. CLASIFICADORES
-- Identidad del usuario del cliente SOAP (NO reutiliza usuarios
-- del monolito, ver decisión de ingeniería Paso 1/4).
-- ============================================================
CREATE TABLE clasificadores (
    id_clasificador     SERIAL PRIMARY KEY,
    nombre               VARCHAR(150) NOT NULL,
    apellidos             VARCHAR(150) NOT NULL,
    correo               VARCHAR(150) NOT NULL UNIQUE,
    fecha_registro        TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 2. CLASIFICACIONES_CLOUD
-- Cada registro = un clasificador clasificó un concepto (de un
-- libro específico) con un modelo Cloud (IaaS/PaaS/SaaS/FaaS).
-- ============================================================
CREATE TABLE clasificaciones_cloud (
    id_clasificacion    SERIAL PRIMARY KEY,
    isbn                 VARCHAR(13) NOT NULL REFERENCES libros(isbn) ON DELETE RESTRICT,
    id_concepto          INTEGER NOT NULL REFERENCES conceptos(id_concepto) ON DELETE RESTRICT,
    id_clasificador      INTEGER NOT NULL REFERENCES clasificadores(id_clasificador) ON DELETE RESTRICT,
    modelo_cloud          VARCHAR(10) NOT NULL CHECK (modelo_cloud IN ('IaaS', 'PaaS', 'SaaS', 'FaaS')),
    fecha_clasificacion   TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Regla de negocio: un mismo clasificador no puede clasificar
    -- el mismo concepto dos veces (detectado como SOAP Fault 409).
    CONSTRAINT uq_clasificador_concepto UNIQUE (id_clasificador, id_concepto)
);

CREATE INDEX idx_clasificaciones_cloud_isbn      ON clasificaciones_cloud(isbn);
CREATE INDEX idx_clasificaciones_cloud_concepto  ON clasificaciones_cloud(id_concepto);
CREATE INDEX idx_clasificaciones_cloud_clasif    ON clasificaciones_cloud(id_clasificador);

-- ============================================================
-- 3. CLIENTES_SERVIDOS
-- Registra qué tipo de cliente de escritorio ha hecho peticiones
-- al módulo SOAP y cuántas ha atendido.
-- ============================================================
CREATE TABLE clientes_servidos (
    id_cliente_servido   SERIAL PRIMARY KEY,
    tipo_cliente          VARCHAR(50) NOT NULL,      -- ej: 'Escritorio-Java', 'Escritorio-Python'
    identificador         VARCHAR(150) NOT NULL,      -- ej: hostname, usuario del SO, o correo del clasificador
    peticiones_atendidas  INTEGER NOT NULL DEFAULT 0 CHECK (peticiones_atendidas >= 0),
    primera_peticion      TIMESTAMP NOT NULL DEFAULT NOW(),
    ultima_peticion       TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_tipo_identificador UNIQUE (tipo_cliente, identificador)
);