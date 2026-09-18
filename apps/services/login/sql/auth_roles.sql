-- ============================================================
-- sql/auth_roles.sql
-- Mínimo privilegio para el microservicio de autenticación (mismo
-- patrón que soap_roles.sql del servicio de libros).
-- Ejecutar como superusuario (postgres) UNA SOLA VEZ, después de
-- cambio_usuarios.sql y auth_module.sql:
--   psql -h localhost -U postgres -d library -f auth_roles.sql
--
-- Cada microservicio tiene su propio rol y solo ve lo que necesita, así
-- ninguno puede romper las tablas del otro:
--   auth_user  -> usuarios (leer, insertar, cambiar SOLO estado_cuenta)
--                 y tokens_confirmacion.
--   soap_user  -> libros y catálogos (ver soap_roles.sql).
-- La contraseña de abajo es la de desarrollo (igual que .env.example);
-- cámbiala en cualquier despliegue real y actualiza DB_PASSWORD en .env.
-- ============================================================

CREATE ROLE auth_user WITH LOGIN PASSWORD 'auth666';

GRANT CONNECT ON DATABASE library TO auth_user;
GRANT USAGE ON SCHEMA public TO auth_user;

-- usuarios: login/sesión leen; register inserta; confirm solo actualiza estado_cuenta.
GRANT SELECT, INSERT ON usuarios TO auth_user;
GRANT UPDATE (estado_cuenta) ON usuarios TO auth_user;
GRANT USAGE, SELECT ON SEQUENCE usuarios_id_usuario_seq TO auth_user;

-- tokens propios del servicio
GRANT SELECT, INSERT, UPDATE ON tokens_confirmacion TO auth_user;
GRANT USAGE, SELECT ON SEQUENCE tokens_confirmacion_id_token_seq TO auth_user;

-- Sin ningún permiso (por defecto) sobre libros, autores, generos, formatos,
-- conceptos, imagenes, libro_* ni las tablas del módulo SOAP.
