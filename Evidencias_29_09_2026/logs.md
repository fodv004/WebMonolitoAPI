Prueba 1: login correcto (200 + token)

==============================================================================
>>> PETICION   [2026-09-29 15:38:46]
POST http://34.51.58.130:5000/login?format=json
--- Headers ---
  User-Agent: python-requests/2.32.3
  Accept-Encoding: gzip, deflate, br, zstd
  Accept: application/json
  Connection: keep-alive
  Content-Length: 63
  Content-Type: application/json
--- Body ---
{
  "email": "maruchanvalo@gmail.com",
  "password": "********"
}
------------------------------------------------------------------------------
<<< RESPUESTA  (339 ms)
Status: 200 OK
--- Headers ---
  Server: Werkzeug/3.1.8 Python/3.12.13
  Date: Tue, 29 Sep 2026 21:38:47 GMT
  Content-Type: application/json
  Content-Length: 524
  Cache-Control: no-store
  Vary: Cookie
  Set-Cookie: auth_session=eyJpZF91c3VhcmlvIjo0MiwiX3Blcm1hbmVudCI6dHJ1ZX0.arwv5w.6L1nN0gSuDaTnVFvzlnYOxHD9bg; Expires=Wed, 30 Sep 2026 05:38:47 GMT; HttpOnly; Path=/; SameSite=Lax
  Connection: close
--- Body ---
{
  "status": "ok",
  "code": "LOGIN_EXITOSO",
  "message": "Sesión iniciada.",
  "data": {
    "authenticated": true,
    "user": {
      "id_usuario": 42,
      "nombre": "Fernando",
      "apellido_paterno": "Olivares",
      "apellido_materno": "Del Valle",
      "email": "maruchanvalo@gmail.com",
      "es_admin": false,
      "estado_cuenta": "confirmado"
    },
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjo0MiwiZW1haWwiOiJtYXJ1Y2hhbnZhbG9AZ21haWwuY29tIiwiaWF0IjoxNzkwNzE3OTI3LCJleHAiOjE3OTA3MjE1Mjd9.Im3UusK48tqFyuSTtACe_AFNXGNTWMccbbf-O7u54qY",
    "token_type": "Bearer",
    "expires_in": 3600
  }
}


Prueba 2: login incorrecto (401)

==============================================================================
>>> PETICION   [2026-09-29 15:37:44]
POST http://34.51.58.130:5000/login?format=json
--- Headers ---
  User-Agent: python-requests/2.32.3
  Accept-Encoding: gzip, deflate, br, zstd
  Accept: application/json
  Connection: keep-alive
  Content-Length: 55
  Content-Type: application/json
--- Body ---
{
  "email": "maruchanvalo@gmail.com",
  "password": "********"
}
------------------------------------------------------------------------------
<<< RESPUESTA  (332 ms)
Status: 401 UNAUTHORIZED
--- Headers ---
  Server: Werkzeug/3.1.8 Python/3.12.13
  Date: Tue, 29 Sep 2026 21:37:45 GMT
  Content-Type: application/json
  Content-Length: 96
  Cache-Control: no-store
  Connection: close
--- Body ---
{
  "status": "error",
  "code": "CREDENCIALES_INVALIDAS",
  "message": "Email o contraseña incorrectos."
}
==============================================================================


prueba 3 obtener libros

==============================================================================
>>> PETICION   [2026-09-29 15:38:47]
GET http://34.51.58.130:5001/books?format=json
--- Headers ---
  User-Agent: python-requests/2.32.3
  Accept-Encoding: gzip, deflate, br, zstd
  Accept: application/json
  Connection: keep-alive
--- Body ---
(vacio)
------------------------------------------------------------------------------
<<< RESPUESTA  (1128 ms)
Status: 200 OK
--- Headers ---
  Server: Werkzeug/3.1.8 Python/3.12.13
  Date: Tue, 29 Sep 2026 21:38:48 GMT
  Content-Type: application/json
  Content-Length: 12870
  Connection: close
--- Body ---
[
  {
    "anio": 1967,
    "autor": "Gabriel García Márquez, Isabel Allende, Mario Vargas Llosa",
    "formato": "Tapa dura",
    "genero": "Realismo mágico",
    "href": "http://34.51.58.130:5001/books/9780000000001",
    "image_url": "https://picsum.photos/seed/libro1/400/600",
    "isbn": "9780000000001",
    "portada": "https://picsum.photos/seed/libro1/400/600",
    "precio": 162.0,
    "stock": 2,
    "titulo": "Cien años de soledad"
  },
  {
    "anio": 1982,
    "autor": "Isabel Allende",
    "formato": "Tapa blanda",
    "genero": "Ficción, Realismo mágico",
    "href": "http://34.51.58.130:5001/books/9780000000002",
    "image_url": "https://picsum.photos/seed/libro2/400/600",
    "isbn": "9780000000002",
    "portada": "https://picsum.photos/seed/libro2/400/600",
    "precio": 174.0,
    "stock": 3,
    "titulo": "La casa de los espíritus"
  },
  {
    "anio": 1963,
    "autor": "Jorge Luis Borges, Julio Cortázar",
    "formato": "Digital",
    "genero": "Ficción",
    "href": "http://34.51.58.130:5001/books/9780000000003",
    "image_url": "https://picsum.photos/seed/libro3/400/600",
    "isbn": "9780000000003",
    "portada": "https://picsum.photos/seed/libro3/400/600",
    "precio": 186.0,
    "stock": 4,
    "titulo": "Rayuela"
  },
  {
    "anio": 1944,
    "autor": "Jorge Luis Borges",
    "formato": "Audiolibro",
    "genero": "Fantasía, Ficción",
    "href": "http://34.51.58.130:5001/books/9780000000004",
    "image_url": "https://picsum.photos/seed/libro4/400/600",
    "isbn": "9780000000004",
    "portada": "https://picsum.photos/seed/libro4/400/600",
    "precio": 198.0,
    "stock": 5,
    "titulo": "Ficciones"
  },
  {
    "anio": 1963,
    "autor": "Mario Vargas Llosa",
    "formato": "Pasta rústica",
    "genero": "Ficción",
    "href": "http://34.51.58.130:5001/books/9780000000005",
    "image_url": "https://picsum.photos/seed/libro5/400/600",
    "isbn": "9780000000005",
    "portada": "https://picsum.photos/seed/libro5/400/600",
    "precio": 210.0,
    "stock": 6,
    "titulo": "La ciudad y los perros"
  },
  {
    "anio": 1950,
    "autor": "Octavio Paz",
    "formato": "Tapa dura",
    "genero": "Ensayo, Filosofía",
    "href": "http://34.51.58.130:5001/books/9780000000006",
    "image_url": "https://picsum.photos/seed/libro6/400/600",
    "isbn": "9780000000006",
    "portada": "https://picsum.photos/seed/libro6/400/600",
    "precio": 222.0,
    "stock": 7,
    "titulo": "El laberinto de la soledad"
  },
  {
    "anio": 1924,
    "autor": "Pablo Neruda",
    "formato": "Tapa blanda",
    "genero": "Poesía",
    "href": "http://34.51.58.130:5001/books/9780000000007",
    "image_url": "https://picsum.photos/seed/libro7/400/600",
    "isbn": "9780000000007",
    "portada": "https://picsum.photos/seed/libro7/400/600",
    "precio": 234.0,
    "stock": 8,
    "titulo": "Veinte poemas de amor y una canción desesperada"
  },
  {
    "anio": 1989,
    "autor": "Laura Esquivel",
    "formato": "Digital",
    "genero": "Ficción, Romance",
    "href": "http://34.51.58.130:5001/books/9780000000008",
    "image_url": "https://picsum.photos/seed/libro8/400/600",
    "isbn": "9780000000008",
    "portada": "https://picsum.photos/seed/libro8/400/600",
    "precio": 246.0,
    "stock": 9,
    "titulo": "Como agua para chocolate"
  },
  {
    "anio": 1955,
    "autor": "Juan Rulfo",
    "formato": "Audiolibro",
    "genero": "Ficción, Realismo mágico",
    "href": "http://34.51.58.130:5001/books/9780000000009",
    "image_url": "https://picsum.photos/seed/libro9/400/600",
    "isbn": "9780000000009",
    "portada": "https://picsum.photos/seed/libro9/400/600",
    "precio": 258.0,
    "stock": 10,
    "titulo": "Pedro Páramo"
  },
  {
    "anio": 1958,
    "autor": "Carlos Fuentes",
    "formato": "Pasta rústica",
    "genero": "Ficción",
    "href": "http://34.51.58.130:5001/books/9780000000010",
    "image_url": "https://picsum.photos/seed/libro10/400/600",
    "isbn": "9780000000010",
    "portada": "https:/
... (8599 caracteres mas, recortado)
==============================================================================


prueba 4: agregar libro


==============================================================================
>>> PETICION   [2026-09-29 15:45:23]
POST http://34.51.58.130:5001/books?format=json
--- Headers ---
  User-Agent: python-requests/2.32.3
  Accept-Encoding: gzip, deflate, br, zstd
  Accept: application/json
  Connection: keep-alive
  Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjo0MiwiZW1haWwiOiJtYXJ1Y2hhbnZhbG9AZ21haWwuY29tIiwiaWF0IjoxNzkwNzE3OTI3LCJleHAiOjE3OTA3MjE1Mjd9.Im3UusK48tqFyuSTtACe_AFNXGNTWMccbbf-O7u54qY
  Content-Length: 206
  Content-Type: application/json
--- Body ---
{
  "isbn": "9990000000002",
  "titulo": "Libro de prueba JWT",
  "anio": 2026,
  "precio": 100.0,
  "stock": 3,
  "formato": "Tapa dura",
  "autor": "JWT",
  "genero": "Ciencia",
  "portada": "https://picsum.photos/300/450"
}
------------------------------------------------------------------------------
<<< RESPUESTA  (107 ms)
Status: 201 CREATED
--- Headers ---
  Server: Werkzeug/3.1.8 Python/3.12.13
  Date: Tue, 29 Sep 2026 21:45:24 GMT
  Content-Type: application/json
  Content-Length: 333
  Connection: close
--- Body ---
{
  "anio": 2026,
  "autor": "JWT",
  "formato": "Tapa dura",
  "genero": "Ciencia",
  "href": "http://34.51.58.130:5001/books/9990000000002",
  "image_url": "https://picsum.photos/300/450",
  "isbn": "9990000000002",
  "portada": "https://picsum.photos/300/450",
  "precio": 100.0,
  "stock": 3,
  "titulo": "Libro de prueba JWT"
}
==============================================================================

prueba 5: PUT de un libro

==============================================================================
>>> PETICION   [2026-09-29 15:47:09]
PUT http://34.51.58.130:5001/books/9780000000002?format=json
--- Headers ---
  User-Agent: python-requests/2.32.3
  Accept-Encoding: gzip, deflate, br, zstd
  Accept: application/json
  Connection: keep-alive
  Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjo0MiwiZW1haWwiOiJtYXJ1Y2hhbnZhbG9AZ21haWwuY29tIiwiaWF0IjoxNzkwNzE3OTI3LCJleHAiOjE3OTA3MjE1Mjd9.Im3UusK48tqFyuSTtACe_AFNXGNTWMccbbf-O7u54qY
  Content-Length: 217
  Content-Type: application/json
--- Body ---
{
  "titulo": "ITC",
  "anio": 1982,
  "precio": 174.0,
  "stock": 3,
  "formato": "Tapa blanda",
  "autor": "Isabel Allende",
  "genero": "Ficción, Realismo mágico",
  "portada": "https://picsum.photos/seed/libro2/400/600"
}
------------------------------------------------------------------------------
<<< RESPUESTA  (84 ms)
Status: 200 OK
--- Headers ---
  Server: Werkzeug/3.1.8 Python/3.12.13
  Date: Tue, 29 Sep 2026 21:47:09 GMT
  Content-Type: application/json
  Content-Length: 381
  Connection: close
--- Body ---
{
  "anio": 1982,
  "autor": "Isabel Allende",
  "formato": "Tapa blanda",
  "genero": "Ficción, Realismo mágico",
  "href": "http://34.51.58.130:5001/books/9780000000002",
  "image_url": "https://picsum.photos/seed/libro2/400/600",
  "isbn": "9780000000002",
  "portada": "https://picsum.photos/seed/libro2/400/600",
  "precio": 174.0,
  "stock": 3,
  "titulo": "ITC"
}
==============================================================================


prueba 6: Eliminar libro

==============================================================================
>>> PETICION   [2026-09-29 15:49:14]
DELETE http://34.51.58.130:5001/books/9990000000002?format=json
--- Headers ---
  User-Agent: python-requests/2.32.3
  Accept-Encoding: gzip, deflate, br, zstd
  Accept: application/json
  Connection: keep-alive
  Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjo0MiwiZW1haWwiOiJtYXJ1Y2hhbnZhbG9AZ21haWwuY29tIiwiaWF0IjoxNzkwNzE3OTI3LCJleHAiOjE3OTA3MjE1Mjd9.Im3UusK48tqFyuSTtACe_AFNXGNTWMccbbf-O7u54qY
  Content-Length: 0
--- Body ---
(vacio)
------------------------------------------------------------------------------
<<< RESPUESTA  (92 ms)
Status: 200 OK
--- Headers ---
  Server: Werkzeug/3.1.8 Python/3.12.13
  Date: Tue, 29 Sep 2026 21:49:15 GMT
  Content-Type: application/json
  Content-Length: 95
  Connection: close
--- Body ---
{
  "isbn": "9990000000002",
  "mensaje": "Libro 9990000000002 eliminado.",
  "status": "ok"
}
==============================================================================