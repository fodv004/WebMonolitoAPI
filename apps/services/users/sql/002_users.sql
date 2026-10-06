-- ============================================================
-- sql/002_users.sql            (migración 004_users)
-- Lo que le falta a la tabla `usuarios` para el microservicio users.
-- La tabla NO se duplica: es la misma que usan login y el monolito.
--
-- Columnas que ya existen y se reutilizan tal cual (no se crean otras
-- con nombre distinto ni se renombran):
--   password_hash   -> contraseña (bcrypt, igual que login)
--   activo          -> baja lógica
--   fecha_registro  -> es el "created_at" de la API
--   estado_cuenta   -> es el "email_verificado" de la API
--                      ('confirmado' = true, 'pendiente' = false)
--   role_id         -> la agregó sql/001_roles.sql
--   es_admin        -> la sigue usando el monolito; se conserva
--
-- Lo único que falta de verdad: updated_at.
--
-- Ejecutar como library_user (dueño de la BD), después de 001_roles.sql,
-- o con scripts/levantar_servicios.sh:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f 002_users.sql
--
-- Propiedades: transaccional, idempotente y sin borrar ni reescribir
-- columnas. La resincronización es_admin -> role_id solo se hace la
-- primera vez (schema_migraciones); después la mantiene el trigger.
-- ============================================================

BEGIN;

CREATE TEMP TABLE _mig_users_ctx ON COMMIT DROP AS
SELECT NOT EXISTS (
           SELECT 1 FROM schema_migraciones WHERE version = '004_users'
       ) AS pendiente,
       NOT EXISTS (
           SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'usuarios' AND column_name = 'updated_at'
       ) AS sin_updated_at;

-- ------------------------------------------------------------
-- 1. Columnas: solo se agrega lo que falte
-- ------------------------------------------------------------
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS role_id    SMALLINT  NOT NULL DEFAULT 2 REFERENCES roles(role_id),
    ADD COLUMN IF NOT EXISTS activo     BOOLEAN   NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

-- Las cuentas que ya existían: su última modificación conocida es su alta.
UPDATE usuarios
   SET updated_at = fecha_registro
 WHERE (SELECT sin_updated_at FROM _mig_users_ctx);

-- ------------------------------------------------------------
-- 2. Roles a partir de la columna del monolito: es_admin = TRUE -> 1 (admin),
--    el resto -> 2 (cliente). Solo en la primera aplicación.
-- ------------------------------------------------------------
UPDATE usuarios
   SET role_id = CASE WHEN es_admin THEN 1 ELSE 2 END
 WHERE role_id <> CASE WHEN es_admin THEN 1 ELSE 2 END
   AND (SELECT pendiente FROM _mig_users_ctx);

-- ------------------------------------------------------------
-- 3. Trigger: mantiene es_admin y role_id sincronizados sin importar
--    quién escriba (users cambia role_id; el monolito cambia es_admin)
--    y actualiza updated_at en cada UPDATE.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_usuarios_rol_y_fecha()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.es_admin AND NEW.role_id = 2 THEN
            NEW.role_id := 1;                       -- alta de un admin desde el monolito
        ELSE
            NEW.es_admin := (NEW.role_id = 1);
        END IF;
    ELSE
        IF NEW.role_id IS DISTINCT FROM OLD.role_id THEN
            NEW.es_admin := (NEW.role_id = 1);
        ELSIF NEW.es_admin IS DISTINCT FROM OLD.es_admin THEN
            NEW.role_id := CASE WHEN NEW.es_admin THEN 1 ELSE 2 END;
        END IF;
        NEW.updated_at := NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_usuarios_rol_y_fecha ON usuarios;
CREATE TRIGGER trg_usuarios_rol_y_fecha
    BEFORE INSERT OR UPDATE ON usuarios
    FOR EACH ROW
    EXECUTE FUNCTION trg_fn_usuarios_rol_y_fecha();

INSERT INTO schema_migraciones (version, descripcion)
VALUES ('004_users', 'users: usuarios.updated_at y trigger de sincronía es_admin <-> role_id')
ON CONFLICT (version) DO NOTHING;

COMMIT;
