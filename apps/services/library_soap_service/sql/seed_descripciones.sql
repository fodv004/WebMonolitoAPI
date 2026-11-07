-- ============================================================
-- sql/seed_descripciones.sql   (OPCIONAL, NO es una migración)
-- Descripciones de ejemplo para libros.descripcion. Edítalas a tu gusto.
-- No lleva número al inicio, así que scripts/levantar_servicios.sh NO lo
-- ejecuta: córrelo a mano DESPUÉS de 001_libros_descripcion.sql:
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f apps/services/library_soap_service/sql/seed_descripciones.sql
--
-- Los ISBN son los del seed del monolito (978 + 10 dígitos). Un ISBN que no
-- exista simplemente actualiza 0 filas. Tras correrlo, la caché de Redis de
-- GET /books se renueva sola en 60 s (o reinicia books).
-- ============================================================
BEGIN;

UPDATE libros SET descripcion = 'La saga de la familia Buendía a lo largo de siete generaciones en el pueblo de Macondo, entre el realismo mágico y la soledad.'
WHERE isbn = '9780000000001';

UPDATE libros SET descripcion = 'Historia de la familia Trueba en un país latinoamericano sin nombre, marcada por los espíritus, el amor y la política.'
WHERE isbn = '9780000000002';

UPDATE libros SET descripcion = 'Novela que se puede leer en orden o saltando capítulos: Oliveira entre París y Buenos Aires, en busca de sentido.'
WHERE isbn = '9780000000003';

UPDATE libros SET descripcion = 'Cuentos de laberintos, bibliotecas infinitas y espejos que juegan con el tiempo, la identidad y la realidad.'
WHERE isbn = '9780000000004';

UPDATE libros SET descripcion = 'La vida de unos cadetes en un colegio militar de Lima y la violencia que los forma.'
WHERE isbn = '9780000000005';

UPDATE libros SET descripcion = 'Ensayo sobre la identidad mexicana, sus máscaras, sus fiestas y su relación con la historia.'
WHERE isbn = '9780000000006';

-- Plantilla para agregar más:
-- UPDATE libros SET descripcion = 'Escribe aquí la descripción.' WHERE isbn = '978XXXXXXXXXX';

COMMIT;
