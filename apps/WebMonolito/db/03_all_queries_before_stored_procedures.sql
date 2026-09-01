-- ============================================================
-- 03_all_queries_before_stored_procedures.sql
-- Consultas SQL básicas que resuelven los casos de uso principales
-- de la aplicación, escritas de forma directa (sin stored
-- procedures). Sirven como evidencia del SQL "crudo" equivalente
-- al que usan los archivos de src/models/, antes de envolver las
-- operaciones más repetidas en funciones (ver 04_stored_procedures.sql).
-- ============================================================

-- ------------------------------------------------------------
-- LOGIN: buscar usuario por correo (authController.login)
-- ------------------------------------------------------------
SELECT id_usuario, nombre, correo, password_hash, es_admin, activo
FROM usuarios
WHERE correo = 'admin@libreria.com';

-- ------------------------------------------------------------
-- CATÁLOGO: listar libros con formato, autores y géneros (RF-04)
-- ------------------------------------------------------------
SELECT
    l.isbn,
    l.titulo,
    l.anio_publicacion,
    l.precio,
    l.stock,
    f.nombre AS formato,
    STRING_AGG(DISTINCT a.nombre, ', ') AS autores,
    STRING_AGG(DISTINCT g.nombre, ', ') AS generos
FROM libros l
JOIN formatos f ON f.id_formato = l.id_formato
LEFT JOIN libro_autor la ON la.isbn = l.isbn
LEFT JOIN autores a ON a.id_autor = la.id_autor
LEFT JOIN libro_genero lg ON lg.isbn = l.isbn
LEFT JOIN generos g ON g.id_genero = lg.id_genero
GROUP BY l.isbn, l.titulo, l.anio_publicacion, l.precio, l.stock, f.nombre
ORDER BY l.titulo;

-- ------------------------------------------------------------
-- BÚSQUEDA por ISBN exacto (RF-05)
-- ------------------------------------------------------------
SELECT * FROM libros WHERE isbn = '9780000000001';

-- ------------------------------------------------------------
-- BÚSQUEDA por título parcial, sin distinguir mayúsculas (RF-05)
-- ------------------------------------------------------------
SELECT isbn, titulo, precio, stock
FROM libros
WHERE titulo ILIKE '%soledad%';

-- ------------------------------------------------------------
-- DETALLE de un libro: datos propios + conceptos y definiciones (RF-08)
-- ------------------------------------------------------------
SELECT l.isbn, l.titulo, c.nombre AS concepto, lc.definicion
FROM libros l
JOIN libro_concepto lc ON lc.isbn = l.isbn
JOIN conceptos c ON c.id_concepto = lc.id_concepto
WHERE l.isbn = '9780000000002';

-- ------------------------------------------------------------
-- DETALLE de un libro: imágenes asociadas, portada primero (RF-09)
-- ------------------------------------------------------------
SELECT id_imagen, url, es_principal, orden
FROM imagenes
WHERE isbn = '9780000000002'
ORDER BY es_principal DESC, orden ASC;

-- ------------------------------------------------------------
-- CREATE: insertar un libro nuevo (RF-06)
-- ------------------------------------------------------------
INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, id_formato)
VALUES ('9780000099999', 'Libro de prueba manual', 2024, 199.99, 10, 1);

-- ------------------------------------------------------------
-- UPDATE: actualizar precio y stock de un libro (RF-06, RF-10)
-- ------------------------------------------------------------
UPDATE libros
SET precio = 219.99, stock = 8
WHERE isbn = '9780000099999';

-- ------------------------------------------------------------
-- DELETE: eliminar un libro (RF-06)
-- (las filas relacionadas en libro_autor/libro_genero/libro_concepto/
--  imagenes se eliminan solas por ON DELETE CASCADE)
-- ------------------------------------------------------------
DELETE FROM libros WHERE isbn = '9780000099999';

-- ------------------------------------------------------------
-- RELACIÓN M:N: asociar un autor existente a un libro existente (RF-07)
-- ------------------------------------------------------------
INSERT INTO libro_autor (isbn, id_autor)
VALUES ('9780000000001', 2)
ON CONFLICT (isbn, id_autor) DO NOTHING;

-- ------------------------------------------------------------
-- RELACIÓN M:N: quitar un género de un libro (RF-07)
-- ------------------------------------------------------------
DELETE FROM libro_genero
WHERE isbn = '9780000000001' AND id_genero = 1;

-- ------------------------------------------------------------
-- REGISTRO de usuario nuevo (RF-01)
-- ------------------------------------------------------------
INSERT INTO usuarios (nombre, correo, password_hash, es_admin)
VALUES ('Usuario de prueba', 'prueba@libreria.com', '$2b$12$hashDeEjemploGeneradoPorBcrypt', FALSE);

-- ------------------------------------------------------------
-- CRUD de catálogos independientes: crear un autor nuevo (RF-06)
-- ------------------------------------------------------------
INSERT INTO autores (nombre, nacionalidad)
VALUES ('Nueva Autora de Prueba', 'Mexicana');

-- ------------------------------------------------------------
-- Marcar una imagen como portada, desmarcando la anterior (RF-09)
-- ------------------------------------------------------------
UPDATE imagenes SET es_principal = FALSE WHERE isbn = '9780000000001';
UPDATE imagenes SET es_principal = TRUE
WHERE isbn = '9780000000001'
  AND id_imagen = (SELECT MIN(id_imagen) FROM imagenes WHERE isbn = '9780000000001');

-- ------------------------------------------------------------
-- Libros con stock bajo (apoyo para el Administrador)
-- ------------------------------------------------------------
SELECT isbn, titulo, stock FROM libros WHERE stock <= 5 ORDER BY stock ASC;
