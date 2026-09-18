-- ============================================================
-- sql/auth_module.sql
-- Tablas propias del microservicio de autenticación.
-- Ejecutar como library_user (dueño de la BD 'library'), DESPUÉS de
-- WebMonolito/db/cambio_usuarios.sql (necesita usuarios.estado_cuenta):
--   psql -h localhost -U library_user -d library -f auth_module.sql
--
-- No se crea ninguna tabla de contraseñas: password_hash es una columna
-- de usuarios. Aquí solo vive lo que es exclusivo de este servicio: los
-- tokens de confirmación de correo.
-- ============================================================

-- Un token por registro. Se guarda solo el SHA-256 (hex, 64 caracteres) del
-- token: el valor real únicamente viaja en el correo.
CREATE TABLE IF NOT EXISTS tokens_confirmacion (
    id_token    SERIAL PRIMARY KEY,
    id_usuario  INTEGER   NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    token_hash  CHAR(64)  NOT NULL UNIQUE,
    creado_en   TIMESTAMP NOT NULL DEFAULT NOW(),
    expira_en   TIMESTAMP NOT NULL,
    usado_en    TIMESTAMP,                       -- NULL = aún sin usar (un solo uso)
    CONSTRAINT chk_token_vigencia CHECK (expira_en > creado_en)
);

CREATE INDEX IF NOT EXISTS idx_tokens_confirmacion_usuario ON tokens_confirmacion(id_usuario);

INSERT INTO schema_migraciones (version, descripcion)
VALUES ('002_auth_tokens_confirmacion', 'auth: tabla tokens_confirmacion (confirmación de correo)')
ON CONFLICT (version) DO NOTHING;
