"""
api/rest.py
Capa HTTP REST adicional (docs/04_prompt_soap.md), separada por
completo del servidor SOAP (/soap en app.py). Expone los mismos
datos de libros/conceptos en XML o JSON segun el query parameter
"format". No modifica el WSDL ni las operaciones SOAP existentes.
"""
import xml.etree.ElementTree as ET

import psycopg2
from flask import Blueprint, Response, jsonify, request

from db.connection import get_connection

rest_bp = Blueprint("rest_api", __name__)

FORMATOS_VALIDOS = {"xml", "json"}
MODELOS_CLOUD = ("IaaS", "PaaS", "SaaS", "FaaS")


class FormatoInvalido(Exception):
    def __init__(self, valor):
        self.valor = valor


class ValidacionError(Exception):
    def __init__(self, mensaje):
        self.mensaje = mensaje


@rest_bp.errorhandler(FormatoInvalido)
def _formato_invalido(err):
    return jsonify({
        "error": "FORMATO_INVALIDO",
        "mensaje": f"El valor de 'format' ({err.valor!r}) no es valido.",
        "valoresValidos": sorted(FORMATOS_VALIDOS),
    }), 400


@rest_bp.errorhandler(ValidacionError)
def _validacion_error(err):
    return jsonify({"error": "VALIDACION", "mensaje": err.mensaje}), 400


@rest_bp.errorhandler(psycopg2.Error)
def _db_error(err):
    return jsonify({"error": "ERROR_BASE_DE_DATOS", "mensaje": str(err).strip()}), 400


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


def _fetch_libro_card(isbn):
    """Igual que una fila de _fetch_todos_libros pero para un solo isbn (usada tras insertar/editar)."""
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
                WHERE l.isbn = %s
                GROUP BY l.isbn, l.titulo, l.anio_publicacion, l.precio, l.stock, f.nombre
                """,
                (isbn,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def _card_dict(row):
    isbn, titulo, anio, precio, stock, formato_nombre, autor, genero, imagen_url = row
    return {
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


# ============================================================
# Validacion y escritura (POST/PUT/DELETE) - usadas por las
# operaciones de CRUD de mas abajo. Consultas parametrizadas.
# ============================================================

def _read_payload():
    if request.is_json:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValidacionError("El cuerpo JSON no es un objeto valido.")
        return data
    if request.form:
        return request.form.to_dict()
    raise ValidacionError("Envia el cuerpo como JSON (application/json) o como formulario.")


def _texto(data, campo, requerido=False, maximo=None):
    valor = data.get(campo)
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if requerido:
            raise ValidacionError(f"El campo '{campo}' es obligatorio.")
        return None
    if not isinstance(valor, str):
        raise ValidacionError(f"El campo '{campo}' debe ser texto.")
    valor = valor.strip()
    if maximo and len(valor) > maximo:
        raise ValidacionError(f"El campo '{campo}' no puede exceder {maximo} caracteres.")
    return valor


def _numero(data, campo, tipo, requerido=False, minimo=None):
    valor = data.get(campo)
    if valor is None or valor == "":
        if requerido:
            raise ValidacionError(f"El campo '{campo}' es obligatorio.")
        return None
    try:
        valor = tipo(valor)
    except (TypeError, ValueError):
        raise ValidacionError(f"El campo '{campo}' debe ser numerico.")
    if minimo is not None and valor < minimo:
        raise ValidacionError(f"El campo '{campo}' debe ser mayor o igual a {minimo}.")
    return valor


def _get_or_create_formato(nombre, cur):
    cur.execute(
        """
        INSERT INTO formatos (nombre) VALUES (%s)
        ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
        RETURNING id_formato
        """,
        (nombre,),
    )
    return cur.fetchone()[0]


def _get_or_create_genero(nombre, cur):
    cur.execute(
        """
        INSERT INTO generos (nombre) VALUES (%s)
        ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
        RETURNING id_genero
        """,
        (nombre,),
    )
    return cur.fetchone()[0]


def _get_or_create_autor(nombre, cur):
    # 'autores.nombre' no es UNIQUE en el esquema original: se reutiliza por
    # coincidencia exacta (sin importar mayusculas) y si no existe se crea.
    cur.execute("SELECT id_autor FROM autores WHERE lower(nombre) = lower(%s) LIMIT 1", (nombre,))
    fila = cur.fetchone()
    if fila:
        return fila[0]
    cur.execute("INSERT INTO autores (nombre) VALUES (%s) RETURNING id_autor", (nombre,))
    return cur.fetchone()[0]


def _set_autor(isbn, nombre, cur):
    id_autor = _get_or_create_autor(nombre, cur)
    cur.execute("DELETE FROM libro_autor WHERE isbn = %s", (isbn,))
    cur.execute("INSERT INTO libro_autor (isbn, id_autor) VALUES (%s, %s)", (isbn, id_autor))


def _set_genero(isbn, nombre, cur):
    id_genero = _get_or_create_genero(nombre, cur)
    cur.execute("DELETE FROM libro_genero WHERE isbn = %s", (isbn,))
    cur.execute("INSERT INTO libro_genero (isbn, id_genero) VALUES (%s, %s)", (isbn, id_genero))


def _set_portada(isbn, url, cur):
    cur.execute("UPDATE imagenes SET url = %s WHERE isbn = %s AND es_principal", (url, isbn))
    if cur.rowcount == 0:
        cur.execute(
            "INSERT INTO imagenes (isbn, url, es_principal, orden) VALUES (%s, %s, TRUE, 0)",
            (isbn, url),
        )


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
        return jsonify([_card_dict(fila) for fila in libros]), 200

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


# ============================================================
# 5. Salud del servicio (usado por el semaforo de la app cliente).
# ============================================================
@rest_bp.route("/health", methods=["GET"])
def salud():
    formato = _resolver_formato()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    except psycopg2.Error:
        return jsonify({
            "status": "error",
            "code": "BASE_DE_DATOS_NO_DISPONIBLE",
            "mensaje": "PostgreSQL no responde.",
        }), 503
    finally:
        conn.close()

    if formato == "json":
        return jsonify({"status": "ok", "service": "books"}), 200
    root = ET.Element("health")
    ET.SubElement(root, "status").text = "ok"
    ET.SubElement(root, "service").text = "books"
    return _xml_response(root)


# ============================================================
# 6. Formatos existentes (para el selector de la app cliente).
# ============================================================
@rest_bp.route("/formats", methods=["GET"])
def listar_formatos():
    formato = _resolver_formato()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id_formato, nombre FROM formatos ORDER BY nombre")
            filas = cur.fetchall()
    finally:
        conn.close()

    if formato == "json":
        return jsonify([{"id_formato": id_formato, "nombre": nombre} for id_formato, nombre in filas]), 200

    root = ET.Element("formats")
    for id_formato, nombre in filas:
        ET.SubElement(root, "format", {"id": str(id_formato)}).text = nombre
    return _xml_response(root)


# ============================================================
# 7. Crear libro. Body: isbn, titulo, anio, precio, stock, formato
#    (nombre; se crea si no existe) y, opcionales, autor, genero,
#    portada (url de la imagen principal).
# ============================================================
@rest_bp.route("/books", methods=["POST"])
def crear_libro():
    _resolver_formato()
    data = _read_payload()

    isbn = _texto(data, "isbn", requerido=True, maximo=13)
    titulo = _texto(data, "titulo", requerido=True, maximo=255)
    anio = _numero(data, "anio", int, requerido=True, minimo=1)
    precio = _numero(data, "precio", float, requerido=True, minimo=0)
    stock = _numero(data, "stock", int, requerido=True, minimo=0)
    nombre_formato = _texto(data, "formato", requerido=True, maximo=50)
    autor = _texto(data, "autor", maximo=150)
    genero = _texto(data, "genero", maximo=50)
    portada = _texto(data, "portada", maximo=500)

    conn = get_connection()
    try:
        try:
            with conn:
                with conn.cursor() as cur:
                    id_formato = _get_or_create_formato(nombre_formato, cur)
                    cur.execute(
                        """
                        INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, id_formato)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (isbn, titulo, anio, precio, stock, id_formato),
                    )
                    if autor:
                        _set_autor(isbn, autor, cur)
                    if genero:
                        _set_genero(isbn, genero, cur)
                    if portada:
                        _set_portada(isbn, portada, cur)
        except psycopg2.errors.UniqueViolation:
            return jsonify({
                "error": "ISBN_DUPLICADO",
                "mensaje": f"Ya existe un libro con ISBN {isbn}.",
            }), 409
    finally:
        conn.close()

    return jsonify(_card_dict(_fetch_libro_card(isbn))), 201


# ============================================================
# 8. Editar libro. Body: cualquier subconjunto de titulo, anio,
#    precio, stock, formato, autor, genero, portada.
# ============================================================
@rest_bp.route("/books/<isbn>", methods=["PUT"])
def actualizar_libro(isbn):
    _resolver_formato()
    if _fetch_libro(isbn) is None:
        return jsonify({
            "error": "LIBRO_NO_ENCONTRADO",
            "mensaje": f"No existe un libro con ISBN {isbn}.",
        }), 404

    data = _read_payload()
    titulo = _texto(data, "titulo", maximo=255)
    anio = _numero(data, "anio", int, minimo=1)
    precio = _numero(data, "precio", float, minimo=0)
    stock = _numero(data, "stock", int, minimo=0)
    nombre_formato = _texto(data, "formato", maximo=50)
    autor = _texto(data, "autor", maximo=150)
    genero = _texto(data, "genero", maximo=50)
    portada = _texto(data, "portada", maximo=500)

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                campos, valores = [], []
                if titulo is not None:
                    campos.append("titulo = %s")
                    valores.append(titulo)
                if anio is not None:
                    campos.append("anio_publicacion = %s")
                    valores.append(anio)
                if precio is not None:
                    campos.append("precio = %s")
                    valores.append(precio)
                if stock is not None:
                    campos.append("stock = %s")
                    valores.append(stock)
                if nombre_formato is not None:
                    campos.append("id_formato = %s")
                    valores.append(_get_or_create_formato(nombre_formato, cur))
                if campos:
                    valores.append(isbn)
                    cur.execute(f"UPDATE libros SET {', '.join(campos)} WHERE isbn = %s", valores)
                if autor:
                    _set_autor(isbn, autor, cur)
                if genero:
                    _set_genero(isbn, genero, cur)
                if portada:
                    _set_portada(isbn, portada, cur)
    finally:
        conn.close()

    return jsonify(_card_dict(_fetch_libro_card(isbn))), 200


# ============================================================
# 9. Eliminar libro.
# ============================================================
@rest_bp.route("/books/<isbn>", methods=["DELETE"])
def eliminar_libro(isbn):
    if _fetch_libro(isbn) is None:
        return jsonify({
            "error": "LIBRO_NO_ENCONTRADO",
            "mensaje": f"No existe un libro con ISBN {isbn}.",
        }), 404

    conn = get_connection()
    try:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM libros WHERE isbn = %s", (isbn,))
        except psycopg2.errors.ForeignKeyViolation:
            return jsonify({
                "error": "LIBRO_EN_USO",
                "mensaje": "No se puede eliminar: el libro tiene clasificaciones Cloud asociadas.",
            }), 409
    finally:
        conn.close()

    return jsonify({"status": "ok", "mensaje": f"Libro {isbn} eliminado.", "isbn": isbn}), 200
