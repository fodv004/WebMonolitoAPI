import os

from dotenv import load_dotenv

load_dotenv()

from flasgger import Swagger
from flask import Flask, jsonify, request
from flask_cors import CORS
from psycopg2 import errors as pg_errors

import db

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": os.getenv("CORS_ORIGINS", "*")}})

SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "Library Books API",
        "description": (
            "Flask microservice for CRUD operations on books, backed by PostgreSQL. "
            "Book shape mirrors apps/services/soap/library.xml."
        ),
        "version": "1.0.0",
    },
    "schemes": ["http", "https"],
    "definitions": {
        "Author": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "example": "Gabriel García Márquez"},
                "nationality": {"type": "string", "example": "Colombian"},
            },
        },
        "Image": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "example": "https://covers.openlibrary.org/b/id/12627383-L.jpg"},
                "main": {"type": "boolean", "example": True},
                "order": {"type": "integer", "example": 0},
            },
        },
        "Concept": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "example": "Solitude"},
                "definition": {"type": "string"},
            },
        },
        "Book": {
            "type": "object",
            "properties": {
                "isbn": {"type": "string", "example": "9780000000001"},
                "title": {"type": "string", "example": "Cien años de soledad"},
                "publicationYear": {"type": "integer", "example": 1967},
                "price": {"type": "number", "format": "float", "example": 350.0},
                "stock": {"type": "integer", "example": 20},
                "format": {"type": "string", "example": "Tapa dura"},
                "authors": {"type": "array", "items": {"$ref": "#/definitions/Author"}},
                "genres": {"type": "array", "items": {"type": "string"}, "example": ["Ficción"]},
                "images": {"type": "array", "items": {"$ref": "#/definitions/Image"}},
                "concepts": {"type": "array", "items": {"$ref": "#/definitions/Concept"}},
            },
        },
        "Error": {
            "type": "object",
            "properties": {"error": {"type": "string"}},
        },
    },
}

SWAGGER_CONFIG = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
}

Swagger(app, template=SWAGGER_TEMPLATE, config=SWAGGER_CONFIG)

REQUIRED_BOOK_FIELDS = ["isbn", "title", "publicationYear", "price", "stock", "format"]


def _missing_fields(data, require_isbn=True):
    required = REQUIRED_BOOK_FIELDS if require_isbn else [f for f in REQUIRED_BOOK_FIELDS if f != "isbn"]
    return [f for f in required if data.get(f) in (None, "")]


@app.get("/health")
def health():
    """
    Health check
    ---
    tags:
      - Health
    responses:
      200:
        description: Service is up
        schema:
          type: object
          properties:
            status:
              type: string
              example: ok
    """
    return jsonify(status="ok")


@app.get("/api/books")
def api_list_books():
    """
    List all books, or search by attributes
    ---
    tags:
      - Books
    parameters:
      - name: isbn
        in: query
        type: string
      - name: title
        in: query
        type: string
        description: Case-insensitive partial match
      - name: author
        in: query
        type: string
        description: Case-insensitive partial match on author name
      - name: genre
        in: query
        type: string
        description: Case-insensitive partial match on genre name
      - name: format
        in: query
        type: string
        description: Case-insensitive partial match on format (e.g. Tapa dura, Digital)
      - name: year
        in: query
        type: integer
      - name: min_price
        in: query
        type: number
      - name: max_price
        in: query
        type: number
      - name: min_stock
        in: query
        type: integer
    responses:
      200:
        description: Books matching the given filters (all books when no filters are given)
        schema:
          type: array
          items:
            $ref: '#/definitions/Book'
    """
    raw_filters = {
        "isbn": request.args.get("isbn"),
        "title": request.args.get("title"),
        "author": request.args.get("author"),
        "genre": request.args.get("genre"),
        "format": request.args.get("format"),
        "year": request.args.get("year", type=int),
        "min_price": request.args.get("min_price", type=float),
        "max_price": request.args.get("max_price", type=float),
        "min_stock": request.args.get("min_stock", type=int),
    }
    filters = {k: v for k, v in raw_filters.items() if v is not None}
    return jsonify(db.list_books(filters))


@app.get("/api/books/<isbn>")
def api_get_book(isbn):
    """
    Get one book by ISBN
    ---
    tags:
      - Books
    parameters:
      - name: isbn
        in: path
        type: string
        required: true
    responses:
      200:
        description: The book
        schema:
          $ref: '#/definitions/Book'
      404:
        description: Book not found
        schema:
          $ref: '#/definitions/Error'
    """
    book = db.get_book(isbn)
    if book is None:
        return jsonify(error="Book not found"), 404
    return jsonify(book)


@app.post("/api/books")
def api_create_book():
    """
    Create a book
    ---
    tags:
      - Books
    consumes:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/Book'
    responses:
      201:
        description: Book created
        schema:
          $ref: '#/definitions/Book'
      400:
        description: Missing or invalid fields
        schema:
          $ref: '#/definitions/Error'
      409:
        description: A book with this isbn already exists
        schema:
          $ref: '#/definitions/Error'
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Request body must be a JSON object"), 400

    missing = _missing_fields(data)
    if missing:
        return jsonify(error="Missing required fields", fields=missing), 400

    try:
        book = db.create_book(data)
    except pg_errors.UniqueViolation:
        return jsonify(error=f"Book with isbn {data['isbn']} already exists"), 409
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400

    return jsonify(book), 201


@app.put("/api/books/<isbn>")
def api_replace_book(isbn):
    """
    Replace a book (full update)
    ---
    tags:
      - Books
    consumes:
      - application/json
    parameters:
      - name: isbn
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        description: All fields except isbn are required; authors/genres/images/concepts are fully replaced
        schema:
          $ref: '#/definitions/Book'
    responses:
      200:
        description: Book updated
        schema:
          $ref: '#/definitions/Book'
      400:
        description: Missing or invalid fields
        schema:
          $ref: '#/definitions/Error'
      404:
        description: Book not found
        schema:
          $ref: '#/definitions/Error'
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Request body must be a JSON object"), 400

    missing = _missing_fields(data, require_isbn=False)
    if missing:
        return jsonify(error="Missing required fields", fields=missing), 400

    try:
        book = db.replace_book(isbn, data)
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400

    if book is None:
        return jsonify(error="Book not found"), 404
    return jsonify(book)


@app.patch("/api/books/<isbn>")
def api_patch_book(isbn):
    """
    Modify a book (partial update)
    ---
    tags:
      - Books
    consumes:
      - application/json
    parameters:
      - name: isbn
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        description: Only the fields to change; authors/genres/images/concepts are fully replaced when included
        schema:
          $ref: '#/definitions/Book'
    responses:
      200:
        description: Book updated
        schema:
          $ref: '#/definitions/Book'
      400:
        description: Empty or invalid body
        schema:
          $ref: '#/definitions/Error'
      404:
        description: Book not found
        schema:
          $ref: '#/definitions/Error'
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error="Request body must be a JSON object with at least one field"), 400

    try:
        book = db.patch_book(isbn, data)
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400

    if book is None:
        return jsonify(error="Book not found"), 404
    return jsonify(book)


@app.delete("/api/books/<isbn>")
def api_delete_book(isbn):
    """
    Delete a book
    ---
    tags:
      - Books
    parameters:
      - name: isbn
        in: path
        type: string
        required: true
    responses:
      204:
        description: Book deleted
      404:
        description: Book not found
        schema:
          $ref: '#/definitions/Error'
    """
    if not db.delete_book(isbn):
        return jsonify(error="Book not found"), 404
    return "", 204


@app.errorhandler(404)
def handle_404(_exc):
    return jsonify(error="Not found"), 404


@app.errorhandler(500)
def handle_500(_exc):
    return jsonify(error="Internal server error"), 500


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5001))
    app.run(host="0.0.0.0", port=port)
