import os

import psycopg2
import psycopg2.extras


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


BOOK_SELECT = """
SELECT
    l.isbn,
    l.titulo AS title,
    l.anio_publicacion AS "publicationYear",
    l.precio::float AS price,
    l.stock AS stock,
    f.nombre AS format,
    COALESCE(authors.data, '[]'::json) AS authors,
    COALESCE(genres.data, '[]'::json) AS genres,
    COALESCE(images.data, '[]'::json) AS images,
    COALESCE(concepts.data, '[]'::json) AS concepts
"""

BOOK_FROM = """
FROM libros l
JOIN formatos f ON f.id_formato = l.id_formato
LEFT JOIN LATERAL (
    SELECT json_agg(json_build_object('name', a.nombre, 'nationality', a.nacionalidad)) AS data
    FROM libro_autor la JOIN autores a ON a.id_autor = la.id_autor
    WHERE la.isbn = l.isbn
) authors ON true
LEFT JOIN LATERAL (
    SELECT json_agg(g.nombre) AS data
    FROM libro_genero lg JOIN generos g ON g.id_genero = lg.id_genero
    WHERE lg.isbn = l.isbn
) genres ON true
LEFT JOIN LATERAL (
    SELECT json_agg(
        json_build_object('url', im.url, 'main', im.es_principal, 'order', im.orden)
        ORDER BY im.orden
    ) AS data
    FROM imagenes im
    WHERE im.isbn = l.isbn
) images ON true
LEFT JOIN LATERAL (
    SELECT json_agg(json_build_object('name', c.nombre, 'definition', lc.definicion)) AS data
    FROM libro_concepto lc JOIN conceptos c ON c.id_concepto = lc.id_concepto
    WHERE lc.isbn = l.isbn
) concepts ON true
"""


def get_book(isbn):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"{BOOK_SELECT}{BOOK_FROM}WHERE l.isbn = %s", (isbn,))
            return cur.fetchone()
    finally:
        conn.close()


def list_books(filters):
    conditions = []
    params = []

    if filters.get("isbn"):
        conditions.append("l.isbn = %s")
        params.append(filters["isbn"])
    if filters.get("title"):
        conditions.append("l.titulo ILIKE %s")
        params.append(f"%{filters['title']}%")
    if filters.get("format"):
        conditions.append("f.nombre ILIKE %s")
        params.append(f"%{filters['format']}%")
    if filters.get("year") is not None:
        conditions.append("l.anio_publicacion = %s")
        params.append(filters["year"])
    if filters.get("min_price") is not None:
        conditions.append("l.precio >= %s")
        params.append(filters["min_price"])
    if filters.get("max_price") is not None:
        conditions.append("l.precio <= %s")
        params.append(filters["max_price"])
    if filters.get("min_stock") is not None:
        conditions.append("l.stock >= %s")
        params.append(filters["min_stock"])
    if filters.get("author"):
        conditions.append(
            """EXISTS (
                SELECT 1 FROM libro_autor la JOIN autores a ON a.id_autor = la.id_autor
                WHERE la.isbn = l.isbn AND a.nombre ILIKE %s
            )"""
        )
        params.append(f"%{filters['author']}%")
    if filters.get("genre"):
        conditions.append(
            """EXISTS (
                SELECT 1 FROM libro_genero lg JOIN generos g ON g.id_genero = lg.id_genero
                WHERE lg.isbn = l.isbn AND g.nombre ILIKE %s
            )"""
        )
        params.append(f"%{filters['genre']}%")

    where_clause = f"WHERE {' AND '.join(conditions)} " if conditions else ""
    query = f"{BOOK_SELECT}{BOOK_FROM}{where_clause}ORDER BY l.titulo"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        conn.close()


def _get_or_create_formato(cur, nombre):
    cur.execute("SELECT id_formato FROM formatos WHERE nombre ILIKE %s", (nombre,))
    row = cur.fetchone()
    if row:
        return row["id_formato"]
    cur.execute("INSERT INTO formatos (nombre) VALUES (%s) RETURNING id_formato", (nombre,))
    return cur.fetchone()["id_formato"]


def _get_or_create_autor(cur, nombre, nacionalidad):
    cur.execute("SELECT id_autor FROM autores WHERE nombre ILIKE %s", (nombre,))
    row = cur.fetchone()
    if row:
        return row["id_autor"]
    cur.execute(
        "INSERT INTO autores (nombre, nacionalidad) VALUES (%s, %s) RETURNING id_autor",
        (nombre, nacionalidad),
    )
    return cur.fetchone()["id_autor"]


def _get_or_create_genero(cur, nombre):
    cur.execute("SELECT id_genero FROM generos WHERE nombre ILIKE %s", (nombre,))
    row = cur.fetchone()
    if row:
        return row["id_genero"]
    cur.execute("INSERT INTO generos (nombre) VALUES (%s) RETURNING id_genero", (nombre,))
    return cur.fetchone()["id_genero"]


def _get_or_create_concepto(cur, nombre):
    cur.execute("SELECT id_concepto FROM conceptos WHERE nombre ILIKE %s", (nombre,))
    row = cur.fetchone()
    if row:
        return row["id_concepto"]
    cur.execute("INSERT INTO conceptos (nombre) VALUES (%s) RETURNING id_concepto", (nombre,))
    return cur.fetchone()["id_concepto"]


def _sync_authors(cur, isbn, authors):
    cur.execute("DELETE FROM libro_autor WHERE isbn = %s", (isbn,))
    for author in authors:
        id_autor = _get_or_create_autor(cur, author["name"], author.get("nationality"))
        cur.execute(
            "INSERT INTO libro_autor (isbn, id_autor) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (isbn, id_autor),
        )


def _sync_genres(cur, isbn, genres):
    cur.execute("DELETE FROM libro_genero WHERE isbn = %s", (isbn,))
    for genre in genres:
        id_genero = _get_or_create_genero(cur, genre)
        cur.execute(
            "INSERT INTO libro_genero (isbn, id_genero) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (isbn, id_genero),
        )


def _sync_concepts(cur, isbn, concepts):
    cur.execute("DELETE FROM libro_concepto WHERE isbn = %s", (isbn,))
    for concept in concepts:
        id_concepto = _get_or_create_concepto(cur, concept["name"])
        cur.execute(
            "INSERT INTO libro_concepto (isbn, id_concepto, definicion) VALUES (%s, %s, %s)",
            (isbn, id_concepto, concept.get("definition", "")),
        )


def _sync_images(cur, isbn, images):
    cur.execute("DELETE FROM imagenes WHERE isbn = %s", (isbn,))
    for image in images:
        cur.execute(
            "INSERT INTO imagenes (isbn, url, es_principal, orden) VALUES (%s, %s, %s, %s)",
            (isbn, image["url"], bool(image.get("main", False)), image.get("order", 0)),
        )


def create_book(data):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                id_formato = _get_or_create_formato(cur, data["format"])
                cur.execute(
                    """INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, id_formato)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        data["isbn"],
                        data["title"],
                        data["publicationYear"],
                        data["price"],
                        data["stock"],
                        id_formato,
                    ),
                )
                isbn = data["isbn"]
                _sync_authors(cur, isbn, data.get("authors", []))
                _sync_genres(cur, isbn, data.get("genres", []))
                _sync_concepts(cur, isbn, data.get("concepts", []))
                _sync_images(cur, isbn, data.get("images", []))
    finally:
        conn.close()
    return get_book(data["isbn"])


def replace_book(isbn, data):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM libros WHERE isbn = %s", (isbn,))
                if not cur.fetchone():
                    return None
                id_formato = _get_or_create_formato(cur, data["format"])
                cur.execute(
                    """UPDATE libros
                       SET titulo = %s, anio_publicacion = %s, precio = %s, stock = %s, id_formato = %s
                       WHERE isbn = %s""",
                    (
                        data["title"],
                        data["publicationYear"],
                        data["price"],
                        data["stock"],
                        id_formato,
                        isbn,
                    ),
                )
                _sync_authors(cur, isbn, data.get("authors", []))
                _sync_genres(cur, isbn, data.get("genres", []))
                _sync_concepts(cur, isbn, data.get("concepts", []))
                _sync_images(cur, isbn, data.get("images", []))
    finally:
        conn.close()
    return get_book(isbn)


def patch_book(isbn, data):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM libros WHERE isbn = %s", (isbn,))
                if not cur.fetchone():
                    return None

                fields, params = [], []
                if "title" in data:
                    fields.append("titulo = %s")
                    params.append(data["title"])
                if "publicationYear" in data:
                    fields.append("anio_publicacion = %s")
                    params.append(data["publicationYear"])
                if "price" in data:
                    fields.append("precio = %s")
                    params.append(data["price"])
                if "stock" in data:
                    fields.append("stock = %s")
                    params.append(data["stock"])
                if "format" in data:
                    fields.append("id_formato = %s")
                    params.append(_get_or_create_formato(cur, data["format"]))

                if fields:
                    params.append(isbn)
                    cur.execute(f"UPDATE libros SET {', '.join(fields)} WHERE isbn = %s", params)

                if "authors" in data:
                    _sync_authors(cur, isbn, data["authors"])
                if "genres" in data:
                    _sync_genres(cur, isbn, data["genres"])
                if "concepts" in data:
                    _sync_concepts(cur, isbn, data["concepts"])
                if "images" in data:
                    _sync_images(cur, isbn, data["images"])
    finally:
        conn.close()
    return get_book(isbn)


def delete_book(isbn):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM libros WHERE isbn = %s", (isbn,))
                return cur.rowcount > 0
    finally:
        conn.close()
