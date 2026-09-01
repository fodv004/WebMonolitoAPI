-- ============================================================
-- 06_views.sql
-- Vistas de consulta para simplificar el acceso desde la app.
-- ============================================================

-- ------------------------------------------------------------
-- vista_catalogo_libros: catálogo con formato, autores y géneros
-- agregados en una sola fila por libro — ideal para la pantalla
-- de listado/búsqueda (RF-04, RF-05).
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW vista_catalogo_libros AS
SELECT
    l.isbn,
    l.titulo,
    l.anio_publicacion,
    l.precio,
    l.stock,
    f.nombre AS formato,
    COALESCE(STRING_AGG(DISTINCT a.nombre, ', '), '') AS autores,
    COALESCE(STRING_AGG(DISTINCT g.nombre, ', '), '') AS generos,
    img.url AS portada_url
FROM libros l
JOIN formatos f ON f.id_formato = l.id_formato
LEFT JOIN libro_autor la ON la.isbn = l.isbn
LEFT JOIN autores a ON a.id_autor = la.id_autor
LEFT JOIN libro_genero lg ON lg.isbn = l.isbn
LEFT JOIN generos g ON g.id_genero = lg.id_genero
LEFT JOIN imagenes img ON img.isbn = l.isbn AND img.es_principal = TRUE
GROUP BY l.isbn, l.titulo, l.anio_publicacion, l.precio, l.stock, f.nombre, img.url;

-- ------------------------------------------------------------
-- vista_libro_conceptos: conceptos y definiciones de cada libro,
-- una fila por concepto (para la pantalla de detalle, RF-08).
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW vista_libro_conceptos AS
SELECT
    lc.isbn,
    l.titulo,
    c.nombre AS concepto,
    lc.definicion
FROM libro_concepto lc
JOIN libros l ON l.isbn = lc.isbn
JOIN conceptos c ON c.id_concepto = lc.id_concepto;

-- ------------------------------------------------------------
-- vista_usuarios_admin: listado de usuarios para el panel de
-- administración, sin exponer el password_hash.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW vista_usuarios_admin AS
SELECT
    id_usuario,
    nombre,
    correo,
    es_admin,
    activo,
    fecha_registro
FROM usuarios
ORDER BY fecha_registro DESC;

-- ------------------------------------------------------------
-- vista_stock_bajo: libros con 5 unidades o menos, útil para
-- alertar al Administrador sobre reabastecimiento.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW vista_stock_bajo AS
SELECT isbn, titulo, stock
FROM libros
WHERE stock <= 5
ORDER BY stock ASC;
