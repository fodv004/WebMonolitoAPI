-- ============================================================
-- Paso 8 — Mínimo privilegio: rol soap_user
-- Ejecutar como superusuario (postgres) UNA SOLA VEZ.
-- ============================================================

-- 1. Crear el rol de login para el módulo SOAP
CREATE ROLE soap_user WITH LOGIN PASSWORD 'soap666';

-- 2. Permitir que se conecte a la base de datos
GRANT CONNECT ON DATABASE library TO soap_user;  -- ajusta 'libreria' al nombre real de tu BD
GRANT USAGE ON SCHEMA public TO soap_user;

-- ============================================================
-- 3. SOLO LECTURA — tablas del monolito que el módulo SOAP consulta
-- ============================================================
GRANT SELECT ON libros          TO soap_user;
GRANT SELECT ON conceptos       TO soap_user;
GRANT SELECT ON libro_concepto  TO soap_user;
GRANT SELECT ON generos         TO soap_user;

-- ============================================================
-- 4. LECTURA + ESCRITURA — tablas propias del módulo SOAP
-- ============================================================
GRANT SELECT, INSERT, UPDATE ON clasificadores        TO soap_user;
GRANT SELECT, INSERT, UPDATE ON clasificaciones_cloud  TO soap_user;
GRANT SELECT, INSERT, UPDATE ON clientes_servidos      TO soap_user;

-- Las 3 tablas usan SERIAL (id autoincremental) -> el rol necesita
-- permiso sobre las secuencias asociadas para poder hacer INSERT.
GRANT USAGE, SELECT ON SEQUENCE clasificadores_id_clasificador_seq       TO soap_user;
GRANT USAGE, SELECT ON SEQUENCE clasificaciones_cloud_id_clasificacion_seq TO soap_user;
GRANT USAGE, SELECT ON SEQUENCE clientes_servidos_id_cliente_servido_seq TO soap_user;

-- ============================================================
-- 5. SIN NINGÚN PERMISO (por defecto, no se hace nada) sobre:
-- usuarios, autores, libro_autor, libro_genero, imagenes, formatos
-- No se otorga ningún GRANT sobre estas tablas -> quedan bloqueadas.
-- ============================================================
