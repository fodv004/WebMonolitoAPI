-- ============================================================
-- sql/001_roles.sql            (migración 003_roles)
-- Roles del sistema y rol de cada usuario. El microservicio users es el
-- dueño de `roles` y de `usuarios`; login solo LEE usuarios.role_id para
-- ponerlo en el JWT (claims role_id y role).
--
--   roles: 1 = admin, 2 = cliente
--   usuarios.role_id: FK a roles, NOT NULL, default 2 (cliente)
--
-- Ejecutar como library_user (dueño de la BD), o con
-- scripts/levantar_servicios.sh:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f 001_roles.sql
--
-- Propiedades:
--   * Transaccional: si algo falla, no se aplica nada.
--   * Idempotente: puede ejecutarse más de una vez. La copia inicial
--     es_admin -> role_id solo se hace la primera vez (schema_migraciones),
--     para no pisar los roles que después administre el servicio users.
--   * No borra ni reescribe columnas: es_admin se conserva para el monolito.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migraciones (
    version      VARCHAR(60) PRIMARY KEY,
    descripcion  TEXT        NOT NULL,
    aplicada_en  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- ¿Esta migración ya se aplicó antes? (se evalúa una sola vez)
CREATE TEMP TABLE _mig_roles_ctx ON COMMIT DROP AS
SELECT NOT EXISTS (
           SELECT 1 FROM schema_migraciones WHERE version = '003_roles'
       ) AS pendiente;

-- ------------------------------------------------------------
-- 1. Catálogo de roles
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS roles (
    role_id      SMALLINT    PRIMARY KEY,
    nombre       VARCHAR(30) NOT NULL UNIQUE,
    descripcion  TEXT
);

INSERT INTO roles (role_id, nombre, descripcion) VALUES
    (1, 'admin',   'Administra el catálogo, los usuarios, los pedidos y los pagos'),
    (2, 'cliente', 'Consulta el catálogo y gestiona sus propios pedidos y pagos')
ON CONFLICT (role_id) DO UPDATE
    SET nombre = EXCLUDED.nombre, descripcion = EXCLUDED.descripcion;

-- ------------------------------------------------------------
-- 2. usuarios.role_id (FK, default 2 = cliente)
-- ------------------------------------------------------------
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS role_id SMALLINT NOT NULL DEFAULT 2;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_usuarios_role') THEN
        ALTER TABLE usuarios
            ADD CONSTRAINT fk_usuarios_role FOREIGN KEY (role_id) REFERENCES roles(role_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_usuarios_role_id ON usuarios(role_id);

-- ------------------------------------------------------------
-- 3. Datos existentes: los que ya eran administradores (es_admin)
--    nacen con role_id = 1. Solo en la primera aplicación.
-- ------------------------------------------------------------
UPDATE usuarios
   SET role_id = 1
 WHERE es_admin
   AND role_id <> 1
   AND (SELECT pendiente FROM _mig_roles_ctx);

-- ------------------------------------------------------------
-- 4. Permisos de lectura para los roles de mínimo privilegio que ya
--    existan (login usa auth_user; books usa soap_user). El SELECT que
--    ya tienen sobre usuarios cubre la columna nueva.
-- ------------------------------------------------------------
DO $$
DECLARE
    rol TEXT;
BEGIN
    FOREACH rol IN ARRAY ARRAY['auth_user', 'soap_user'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
            EXECUTE format('GRANT SELECT ON roles TO %I', rol);
        END IF;
    END LOOP;
END $$;

INSERT INTO schema_migraciones (version, descripcion)
VALUES ('003_roles', 'users: tabla roles (1 admin, 2 cliente) y usuarios.role_id')
ON CONFLICT (version) DO NOTHING;

COMMIT;
