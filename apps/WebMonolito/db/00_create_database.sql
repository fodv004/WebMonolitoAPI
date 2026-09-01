-- ============================================================
-- 00_create_database.sql
-- Creación del usuario de aplicación y la base de datos.
-- Ejecutar conectado como superusuario (postgres).
-- ============================================================

-- Usuario de aplicación con privilegios mínimos (no es superusuario).
-- Reemplaza 'CAMBIA_ESTA_PASSWORD' por la contraseña real antes de ejecutar
-- y NUNCA publiques este archivo con la contraseña real dentro.
CREATE ROLE library_user LOGIN PASSWORD 'CAMBIA_ESTA_PASSWORD';

-- Base de datos de la aplicación, con library_user como dueño.
CREATE DATABASE library_db
    OWNER library_user
    ENCODING 'UTF8';

-- Privilegios explícitos (por si el owner no basta en tu instalación de Postgres)
GRANT ALL PRIVILEGES ON DATABASE library_db TO library_user;

-- A partir de aquí, conéctate a library_db como library_user para correr
-- 01_schema.sql en adelante:
--   psql -U library_user -d library_db -f 01_schema.sql