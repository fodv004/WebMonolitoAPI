-- ============================================================
-- sql/soap_module_crud_grants.sql
-- Cambio 1 (docs/04_prompt_soap.md): WebMonolito deja de tocar
-- PostgreSQL directamente y pasa a hacerlo TODO via SOAP. Este
-- script amplia los permisos de soap_user (Paso 8 / soap_roles.sql)
-- para que el modulo SOAP pueda hacer CRUD completo sobre las
-- tablas del monolito, no solo lectura.
-- Ejecutar como superusuario (postgres) UNA SOLA VEZ, despues de
-- soap_roles.sql.
-- ============================================================

-- Tablas del monolito que antes eran solo lectura -> ahora CRUD completo
GRANT SELECT, INSERT, UPDATE, DELETE ON libros          TO soap_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON generos         TO soap_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON conceptos       TO soap_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON libro_concepto  TO soap_user;

-- Tablas del monolito que antes no tenian ningun permiso -> ahora CRUD completo
GRANT SELECT, INSERT, UPDATE, DELETE ON autores      TO soap_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON formatos     TO soap_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON libro_autor  TO soap_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON libro_genero TO soap_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON imagenes     TO soap_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON usuarios     TO soap_user;

-- Secuencias de las tablas con SERIAL que ahora reciben INSERT
GRANT USAGE, SELECT ON SEQUENCE generos_id_genero_seq       TO soap_user;
GRANT USAGE, SELECT ON SEQUENCE conceptos_id_concepto_seq   TO soap_user;
GRANT USAGE, SELECT ON SEQUENCE autores_id_autor_seq        TO soap_user;
GRANT USAGE, SELECT ON SEQUENCE formatos_id_formato_seq     TO soap_user;
GRANT USAGE, SELECT ON SEQUENCE imagenes_id_imagen_seq      TO soap_user;
GRANT USAGE, SELECT ON SEQUENCE usuarios_id_usuario_seq     TO soap_user;
