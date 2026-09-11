"""
api/rest.py
Capa HTTP REST adicional (docs/04_prompt_soap.md), separada por
completo del servidor SOAP (/soap en app.py). Expone los mismos
datos de libros/conceptos en XML o JSON segun el query parameter
"format". No modifica el WSDL ni las operaciones SOAP existentes.
"""
import xml.etree.ElementTree as ET

from flask import Blueprint, Response, jsonify, request

from db.connection import get_connection

rest_bp = Blueprint("rest_api", __name__)

FORMATOS_VALIDOS = {"xml", "json"}
MODELOS_CLOUD = ("IaaS", "PaaS", "SaaS", "FaaS")


class FormatoInvalido(Exception):
    def __init__(self, valor):
        self.valor = valor


@rest_bp.errorhandler(FormatoInvalido)
def _formato_invalido(err):
    return jsonify({
        "error": "FORMATO_INVALIDO",
        "mensaje": f"El valor de 'format' ({err.valor!r}) no es valido.",
        "valoresValidos": sorted(FORMATOS_VALIDOS),
    }), 400


def _resolver_formato():
    formato = request.args.get("format", "xml").lower()
    if formato not in FORMATOS_VALIDOS:
        raise FormatoInvalido(formato)
    return formato


def _xml_response(root_element):
    body = ET.tostring(root_element, encoding="unicode")
    return Response(f'<?xml version="1.0" encoding="UTF-8"?>\n{body}', mimetype="application/xml")


# ============================================================
# Acceso a datos (solo lectura, consultas parametrizadas)
# ============================================================

def _fetch_libro(isbn):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT l.isbn, l.titulo, l.anio_publicacion, l.precio, l.stock, f.nombre
                FROM libros l
                JOIN formatos f ON f.id_formato = l.id_formato
                WHERE l.isbn = %s
                """,
                (isbn,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def _fetch_portada(isbn):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT url FROM imagenes
                WHERE isbn = %s
                ORDER BY es_principal DESC, orden ASC NULLS LAST
                LIMIT 1
                """,
                (isbn,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _fetch_todos_libros():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT l.isbn, l.titulo, l.anio_publicacion, l.precio, l.stock, f.nombre,
                       string_agg(DISTINCT a.nombre, ', ') AS autor,
                       string_agg(DISTINCT g.nombre, ', ') AS genero,
                       (
                           SELECT i.url FROM imagenes i
                           WHERE i.isbn = l.isbn
                           ORDER BY i.es_principal DESC, i.orden ASC NULLS LAST
                           LIMIT 1
                       ) AS imagen_url
                FROM libros l
                JOIN formatos f ON f.id_formato = l.id_formato
                LEFT JOIN libro_autor la ON la.isbn = l.isbn
                LEFT JOIN autores a ON a.id_autor = la.id_autor
                LEFT JOIN libro_genero lg ON lg.isbn = l.isbn
                LEFT JOIN generos g ON g.id_genero = lg.id_genero
                GROUP BY l.isbn, l.titulo, l.anio_publicacion, l.precio, l.stock, f.nombre
                ORDER BY l.isbn
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def _fetch_conceptos_cloud_libro(isbn):
    """Conceptos de Cloud Computing (IaaS/PaaS/SaaS/FaaS) que ya han sido
    asignados (via SOAP, tabla clasificaciones_cloud) a los conceptos
    literarios de este libro."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id_concepto, c.nombre, cc.modelo_cloud, COUNT(*)
                FROM libro_concepto lc
                JOIN conceptos c ON c.id_concepto = lc.id_concepto
                JOIN clasificaciones_cloud cc
                     ON cc.isbn = lc.isbn AND cc.id_concepto = c.id_concepto
                WHERE lc.isbn = %s
                GROUP BY c.id_concepto, c.nombre, cc.modelo_cloud
                ORDER BY c.id_concepto, cc.modelo_cloud
                """,
                (isbn,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def _fetch_todos_conceptos_cloud():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT l.isbn, l.titulo, c.id_concepto, c.nombre, cc.modelo_cloud
                FROM clasificaciones_cloud cc
                JOIN libros l ON l.isbn = cc.isbn
                JOIN conceptos c ON c.id_concepto = cc.id_concepto
                ORDER BY cc.modelo_cloud, l.isbn
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def _fetch_libros_minimos_con_imagenes():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT l.isbn, l.titulo, i.url, i.es_principal
                FROM libros l
                LEFT JOIN imagenes i ON i.isbn = l.isbn
                ORDER BY l.isbn, i.es_principal DESC NULLS LAST, i.orden
                """
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    libros = {}
    for isbn, titulo, url, es_principal in filas:
        entry = libros.setdefault(isbn, {"titulo": titulo, "imagenes": []})
        if url is not None:
            entry["imagenes"].append({"url": url, "principal": bool(es_principal)})
    return [(isbn, data["titulo"], data["imagenes"]) for isbn, data in libros.items()]


# ============================================================
# 1. Lista de todos los libros: xml -> conceptos cloud asociados
#    por libro, json -> tarjetas ("cards") de todos los libros.
# ============================================================
@rest_bp.route("/books", methods=["GET"])
def listar_libros():
    formato = _resolver_formato()
    libros = _fetch_todos_libros()

    if formato == "json":
        cards = [
            {
                "isbn": isbn,
                "titulo": titulo,
                "anio": anio,
                "precio": float(precio),
                "stock": stock,
                "formato": formato_nombre,
                "autor": autor,
                "genero": genero,
                "portada": imagen_url,
                "image_url": imagen_url,
                "href": f"{request.host_url.rstrip('/')}/books/{isbn}",
            }
            for isbn, titulo, anio, precio, stock, formato_nombre, autor, genero, imagen_url in libros
        ]
        return jsonify(cards), 200

    root = ET.Element("books")
    for isbn, titulo, anio, precio, stock, formato_nombre, autor, genero, imagen_url in libros:
        book_el = ET.SubElement(root, "book", {"isbn": isbn})
        ET.SubElement(book_el, "title").text = titulo
        ET.SubElement(book_el, "year").text = str(anio)
        ET.SubElement(book_el, "price").text = str(precio)
        ET.SubElement(book_el, "stock").text = str(stock)
        ET.SubElement(book_el, "format").text = formato_nombre
        ET.SubElement(book_el, "author").text = autor
        ET.SubElement(book_el, "genre").text = genero
        ET.SubElement(book_el, "image_url").text = imagen_url

        concepts_el = ET.SubElement(book_el, "cloudConcepts")
        for id_concepto, nombre_concepto, modelo_cloud, votos in _fetch_conceptos_cloud_libro(isbn):
            concept_el = ET.SubElement(concepts_el, "concept", {
                "id": str(id_concepto),
                "model": modelo_cloud,
                "votes": str(votos),
            })
            concept_el.text = nombre_concepto

    return _xml_response(root)


# ============================================================
# 2. Detalle de un libro: xml -> conceptos cloud asociados,
#    json -> tarjeta ("card") del libro.
# ============================================================
@rest_bp.route("/books/<isbn>", methods=["GET"])
def obtener_libro(isbn):
    formato = _resolver_formato()

    libro = _fetch_libro(isbn)
    if libro is None:
        return jsonify({
            "error": "LIBRO_NO_ENCONTRADO",
            "mensaje": f"No existe un libro con ISBN {isbn}.",
        }), 404

    isbn_db, titulo, anio, precio, stock, formato_nombre = libro

    if formato == "json":
        card = {
            "isbn": isbn_db,
            "titulo": titulo,
            "anio": anio,
            "precio": float(precio),
            "stock": stock,
            "formato": formato_nombre,
            "portada": _fetch_portada(isbn_db),
            "href": request.base_url,
        }
        return jsonify(card), 200

    book_el = ET.Element("book", {"isbn": isbn_db})
    ET.SubElement(book_el, "title").text = titulo
    ET.SubElement(book_el, "year").text = str(anio)
    ET.SubElement(book_el, "price").text = str(precio)
    ET.SubElement(book_el, "stock").text = str(stock)
    ET.SubElement(book_el, "format").text = formato_nombre

    concepts_el = ET.SubElement(book_el, "cloudConcepts")
    for id_concepto, nombre_concepto, modelo_cloud, votos in _fetch_conceptos_cloud_libro(isbn_db):
        concept_el = ET.SubElement(concepts_el, "concept", {
            "id": str(id_concepto),
            "model": modelo_cloud,
            "votes": str(votos),
        })
        concept_el.text = nombre_concepto

    return _xml_response(book_el)


# ============================================================
# 3. Conceptos de Cloud Computing (IaaS/PaaS/SaaS/FaaS) junto con
#    los libros clasificados bajo cada uno.
# ============================================================
@rest_bp.route("/cloud-concepts", methods=["GET"])
def obtener_conceptos_cloud():
    formato = _resolver_formato()
    filas = _fetch_todos_conceptos_cloud()

    if formato == "json":
        libros_por_isbn = {}
        for isbn, titulo, id_concepto, nombre_concepto, modelo_cloud in filas:
            entry = libros_por_isbn.setdefault(isbn, {
                "isbn": isbn,
                "titulo": titulo,
                "conceptosCloud": [],
            })
            entry["conceptosCloud"].append({"concepto": nombre_concepto, "modelo": modelo_cloud})

        return jsonify({
            "modelosCloud": list(MODELOS_CLOUD),
            "libros": list(libros_por_isbn.values()),
        }), 200

    root = ET.Element("cloudConcepts")
    for modelo in MODELOS_CLOUD:
        model_el = ET.SubElement(root, "model", {"name": modelo})
        for isbn, titulo, id_concepto, nombre_concepto, modelo_cloud in filas:
            if modelo_cloud != modelo:
                continue
            book_el = ET.SubElement(model_el, "book", {"isbn": isbn})
            ET.SubElement(book_el, "title").text = titulo
            ET.SubElement(book_el, "concept", {"id": str(id_concepto)}).text = nombre_concepto

    return _xml_response(root)


# ============================================================
# 4. Datos minimos de los libros junto con sus imagenes.
# ============================================================
@rest_bp.route("/books/gallery", methods=["GET"])
def obtener_libros_con_imagenes():
    formato = _resolver_formato()
    libros = _fetch_libros_minimos_con_imagenes()

    if formato == "json":
        cards = [
            {
                "isbn": isbn,
                "titulo": titulo,
                "imagenes": imagenes,
                "href": f"{request.host_url.rstrip('/')}/books/{isbn}",
            }
            for isbn, titulo, imagenes in libros
        ]
        return jsonify(cards), 200

    root = ET.Element("books")
    for isbn, titulo, imagenes in libros:
        book_el = ET.SubElement(root, "book", {"isbn": isbn})
        ET.SubElement(book_el, "title").text = titulo
        images_el = ET.SubElement(book_el, "images")
        for imagen in imagenes:
            ET.SubElement(images_el, "image", {
                "principal": str(imagen["principal"]).lower(),
            }).text = imagen["url"]

    return _xml_response(root)
