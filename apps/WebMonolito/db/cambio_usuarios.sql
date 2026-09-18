-- ============================================================
-- cambio_usuarios.sql            (migración 001_usuarios_1fn)
-- Normaliza la tabla usuarios a Primera Forma Normal (1FN):
--   nombre  (nombre completo en una sola columna)
--     -> nombre, apellido_paterno, apellido_materno  (atómicos)
-- y agrega el estado de la cuenta (pendiente / confirmado) que
-- necesita el microservicio de autenticación (apps/services/login).
--
-- DEBE EJECUTARSE ANTES de levantar el microservicio de auth y
-- antes de desplegar la versión nueva del monolito: ambos dependen
-- de esta estructura.
--
-- Uso (como library_user, dueño de la BD):
--   psql -h localhost -U library_user -d library -f cambio_usuarios.sql
--
-- Propiedades:
--   * Transaccional: si algo falla, no se aplica nada.
--   * Idempotente: se registra en schema_migraciones y puede
--     ejecutarse más de una vez sin volver a partir los nombres.
--   * Sin pérdida de datos: primero se agregan las columnas nuevas,
--     luego se migran los datos con UPDATE y solo entonces se
--     reescribe la columna vieja (nombre). Antes del COMMIT se
--     verifica que nombre + apellidos reconstruyen el original.
--   * No toca password_hash: la contraseña vive únicamente en
--     usuarios (no hay tabla aparte de passwords).
--
-- Regla de separación de los nombres existentes (sin diccionario,
-- así que es heurística; ver README/INSTRUCCIONES.txt):
--   1 palabra            -> nombre
--   2 o 3 palabras       -> último = apellido_paterno, resto = nombre
--                           ('María Fernanda López' -> María Fernanda | López)
--   4 o más palabras     -> penúltimo = apellido_paterno,
--                           último = apellido_materno, resto = nombre
--   Partículas (de, del, la, los, san, van...) se unen al apellido
--   que las sigue ('Juan Carlos de la Cruz' -> Juan Carlos | de la Cruz).
--   Cualquier caso ambiguo se corrige después desde /usuarios.
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 0. Control de versiones del esquema
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migraciones (
    version      VARCHAR(60) PRIMARY KEY,
    descripcion  TEXT        NOT NULL,
    aplicada_en  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- ¿Esta migración ya se aplicó antes? (se evalúa una sola vez)
CREATE TEMP TABLE _mig_ctx ON COMMIT DROP AS
SELECT NOT EXISTS (
           SELECT 1 FROM schema_migraciones WHERE version = '001_usuarios_1fn'
       ) AS pendiente;

-- ------------------------------------------------------------
-- 1. ALTER TABLE: columnas nuevas (nullable / con default, para
--    no romper las filas que ya existen)
-- ------------------------------------------------------------
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS apellido_paterno VARCHAR(100),
    ADD COLUMN IF NOT EXISTS apellido_materno VARCHAR(100),
    -- Las cuentas que ya existen estaban activas y en uso: nacen 'confirmado'.
    ADD COLUMN IF NOT EXISTS estado_cuenta    VARCHAR(10) NOT NULL DEFAULT 'confirmado';

-- Las cuentas NUEVAS nacen 'pendiente' hasta confirmar su correo.
ALTER TABLE usuarios ALTER COLUMN estado_cuenta SET DEFAULT 'pendiente';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_usuarios_estado_cuenta') THEN
        ALTER TABLE usuarios
            ADD CONSTRAINT chk_usuarios_estado_cuenta
            CHECK (estado_cuenta IN ('pendiente', 'confirmado'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_usuarios_nombre_no_vacio') THEN
        ALTER TABLE usuarios
            ADD CONSTRAINT chk_usuarios_nombre_no_vacio
            CHECK (btrim(nombre) <> '');
    END IF;
END $$;

-- ------------------------------------------------------------
-- 2. UPDATE: migrar los datos existentes ANTES de reescribir la
--    columna vieja. Solo se procesan filas que aún no tienen
--    apellidos, y solo si la migración está pendiente.
-- ------------------------------------------------------------

-- Copia temporal (se destruye sola al terminar la transacción)
-- del nombre completo original, para verificar que no se pierde nada.
CREATE TEMP TABLE _mig_original ON COMMIT DROP AS
SELECT id_usuario, nombre
FROM usuarios
WHERE (SELECT pendiente FROM _mig_ctx)
  AND apellido_paterno IS NULL
  AND apellido_materno IS NULL;

CREATE FUNCTION pg_temp.separar_nombre(
    p_completo TEXT,
    OUT o_nombre TEXT, OUT o_paterno TEXT, OUT o_materno TEXT
) AS $$
DECLARE
    particulas TEXT[] := ARRAY['de','del','la','las','los','y','e','san','santa',
                               'da','das','do','dos','di','van','von','der','den'];
    t          TEXT[];
    n          INT;
    x_ini      INT;   -- inicio del último apellido (incluye partículas)
    y_ini      INT;   -- inicio del apellido anterior (incluye partículas)
    restantes  INT;
BEGIN
    t := regexp_split_to_array(btrim(regexp_replace(p_completo, '\s+', ' ', 'g')), ' ');
    n := array_length(t, 1);

    x_ini := n;
    WHILE x_ini > 1 AND lower(t[x_ini - 1]) = ANY (particulas) LOOP
        x_ini := x_ini - 1;
    END LOOP;

    -- Una sola palabra (o solo partículas): todo queda como nombre.
    IF x_ini <= 1 THEN
        o_nombre := array_to_string(t, ' ');
        RETURN;
    END IF;

    restantes := x_ini - 1;              -- palabras antes del último apellido
    IF restantes >= 3 THEN               -- nombre + paterno + materno
        y_ini := restantes;
        WHILE y_ini > 1 AND lower(t[y_ini - 1]) = ANY (particulas) LOOP
            y_ini := y_ini - 1;
        END LOOP;
        IF y_ini > 1 THEN
            o_nombre  := array_to_string(t[1:y_ini - 1], ' ');
            o_paterno := array_to_string(t[y_ini:restantes], ' ');
            o_materno := array_to_string(t[x_ini:n], ' ');
            RETURN;
        END IF;
    END IF;

    o_nombre  := array_to_string(t[1:x_ini - 1], ' ');
    o_paterno := array_to_string(t[x_ini:n], ' ');
    o_materno := NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

UPDATE usuarios u
SET nombre           = s.o_nombre,
    apellido_paterno = s.o_paterno,
    apellido_materno = s.o_materno
FROM _mig_original o
CROSS JOIN LATERAL pg_temp.separar_nombre(o.nombre) s
WHERE u.id_usuario = o.id_usuario;

-- Verificación: nombre + apellidos debe reconstruir exactamente el
-- nombre completo original (ignorando espacios repetidos). Si una
-- sola fila difiere, se aborta y se revierte TODO.
DO $$
DECLARE
    v_distintos INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_distintos
    FROM usuarios u
    JOIN _mig_original o ON o.id_usuario = u.id_usuario
    WHERE concat_ws(' ', u.nombre, u.apellido_paterno, u.apellido_materno)
          IS DISTINCT FROM btrim(regexp_replace(o.nombre, '\s+', ' ', 'g'));

    IF v_distintos > 0 THEN
        RAISE EXCEPTION 'Migración abortada: % usuario(s) no reconstruyen su nombre original', v_distintos;
    END IF;
    RAISE NOTICE 'Nombres migrados y verificados: % usuario(s)', (SELECT COUNT(*) FROM _mig_original);
END $$;

-- ------------------------------------------------------------
-- 3. Objetos que dependían de la columna nombre única
-- ------------------------------------------------------------

-- Vista del panel de administración (sin password_hash).
DROP VIEW IF EXISTS vista_usuarios_admin;
CREATE VIEW vista_usuarios_admin AS
SELECT
    id_usuario,
    nombre,
    apellido_paterno,
    apellido_materno,
    concat_ws(' ', nombre, apellido_paterno, apellido_materno) AS nombre_completo,
    correo,
    es_admin,
    activo,
    estado_cuenta,
    fecha_registro
FROM usuarios
ORDER BY fecha_registro DESC;

-- Registro de usuario: la firma cambia (ahora recibe apellidos).
DROP FUNCTION IF EXISTS sp_registrar_usuario(VARCHAR, VARCHAR, VARCHAR);
CREATE OR REPLACE FUNCTION sp_registrar_usuario(
    p_nombre           VARCHAR(150),
    p_apellido_paterno VARCHAR(100),
    p_apellido_materno VARCHAR(100),
    p_correo           VARCHAR(150),
    p_password_hash    VARCHAR(255),
    p_estado_cuenta    VARCHAR(10) DEFAULT 'pendiente'
) RETURNS INTEGER AS $$
DECLARE
    v_id_usuario INTEGER;
BEGIN
    INSERT INTO usuarios (nombre, apellido_paterno, apellido_materno, correo,
                          password_hash, es_admin, estado_cuenta)
    VALUES (p_nombre, p_apellido_paterno, p_apellido_materno, p_correo,
            p_password_hash, FALSE, p_estado_cuenta)
    RETURNING id_usuario INTO v_id_usuario;

    RETURN v_id_usuario;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- 4. Registrar la versión
-- ------------------------------------------------------------
INSERT INTO schema_migraciones (version, descripcion)
VALUES ('001_usuarios_1fn',
        'usuarios: nombre -> nombre + apellido_paterno + apellido_materno (1FN); estado_cuenta pendiente/confirmado')
ON CONFLICT (version) DO NOTHING;

COMMIT;
