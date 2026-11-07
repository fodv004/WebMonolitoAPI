"""
locustfile.py
Prueba de estres con Locust para el microservicio books
(apps/services/library_soap_service, puerto 5001).

Escenario: 20 usuarios simultaneos (se configuran en la GUI de Locust,
ver README.md). Cada usuario virtual:

  1. Al arrancar (on_start) inicia sesion en el microservicio de login
     (POST http://34.51.8.25:5000/login) y guarda el JWT.
  2. Envia "Authorization: Bearer <token>" en TODAS las peticiones a books.
  3. Ejecuta al azar (segun su peso) las tareas de lectura sobre todos
     los endpoints de books y, con menor frecuencia, un flujo CRUD completo
     sobre un libro de prueba que siempre se borra al final.

Endpoints cubiertos (api/rest.py, app.py y el modulo comun):
  GET    /books                      (xml por defecto)
  GET    /books?format=json | xml
  GET    /books/<isbn>?format=json | xml
  GET    /books/<isbn>  inexistente  (se espera 404)
  GET    /books/gallery?format=json | xml
  GET    /cloud-concepts?format=json | xml
  GET    /formats?format=json | xml
  GET    /health
  GET    /metrics
  POST   /soap   (operaciones de solo lectura)
  POST   /books                          (JWT con rol admin)
  PUT    /books/<isbn>                   (JWT con rol admin)
  PATCH  /books/<isbn>                   (JWT con rol admin)
  DELETE /books/<isbn>                   (JWT con rol admin)
  POST   /books/internal/stock/reservar  (header X-Internal-Key)
  POST   /books/internal/stock/liberar   (header X-Internal-Key)

Variables de entorno:
  LOCUST_EMAIL          (obligatoria) email de la cuenta de prueba
  LOCUST_PASSWORD       (obligatoria) password de la cuenta de prueba
  LOCUST_LOGIN_URL      (opcional) por defecto http://34.51.8.25:5000/login
  LOCUST_INTERNAL_KEY   (opcional) INTERNAL_API_KEY de los servicios; sin
                        ella solo se comprueba que /books/internal/* responda 401

Limpieza de datos: los libros de prueba usan ISBN "999" + 10 digitos al
azar, no llevan autor, genero ni portada (esas tablas no se tocan) y usan
un formato que ya existe. Cada flujo CRUD borra su libro en un "finally"
y, al detener la prueba, test_stop borra cualquier libro que haya quedado.
"""
import os
import random
import threading
import time
import xml.etree.ElementTree as ET

import requests
from locust import HttpUser, between, events, task
from locust.exception import StopUser

DEFAULT_HOST = "http://34.51.8.25:5001"
LOGIN_URL = os.getenv("LOCUST_LOGIN_URL", "http://34.51.8.25:5000/login")
EMAIL = os.getenv("LOCUST_EMAIL")
PASSWORD = os.getenv("LOCUST_PASSWORD")
INTERNAL_KEY = os.getenv("LOCUST_INTERNAL_KEY")

ADMIN_ROLE_ID = 1
# El JWT dura 20 min: se renueva cuando le queda menos de este margen.
TOKEN_MARGIN_SECONDS = 60
# ISBN que nunca existe: sirve para medir la respuesta 404.
ISBN_INEXISTENTE = "0000000000000"
# Formato de respaldo si GET /formats no devuelve nada.
FORMATO_POR_DEFECTO = "Pasta blanda"

NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_TNS = "http://libraryclassifier/library/soap/classifier"

# Libros creados que aun no se borran, y ultimo token admin valido:
# los usa test_stop para limpiar si la prueba se detiene a mitad de un flujo.
_libros_pendientes = set()
_lock = threading.Lock()
_ultimo_token_admin = {"host": None, "token": None}


@events.test_start.add_listener
def _validar_credenciales(environment, **kwargs):
    """Avisa en consola si faltan las variables de entorno de las credenciales."""
    if not EMAIL or not PASSWORD:
        print("[locustfile] ERROR: define LOCUST_EMAIL y LOCUST_PASSWORD antes de iniciar la prueba.")


@events.test_stop.add_listener
def _limpiar_libros_restantes(environment, **kwargs):
    """Borra los libros de prueba que hayan quedado al detener la prueba."""
    with _lock:
        pendientes = list(_libros_pendientes)
    host, token = _ultimo_token_admin["host"], _ultimo_token_admin["token"]
    if not pendientes or not token:
        return
    for isbn in pendientes:
        try:
            r = requests.delete(f"{host}/books/{isbn}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
            if r.status_code in (200, 404):
                with _lock:
                    _libros_pendientes.discard(isbn)
            print(f"[locustfile] limpieza DELETE /books/{isbn} -> {r.status_code}")
        except requests.RequestException as e:
            print(f"[locustfile] no se pudo borrar el libro de prueba {isbn}: {e}")


def _soap_envelope(operacion, campos):
    """Arma un SOAP Envelope con ElementTree (mismo contrato que soap/envelope.py)."""
    envelope = ET.Element(f"{{{NS_SOAP}}}Envelope")
    ET.SubElement(envelope, f"{{{NS_SOAP}}}Header")
    body = ET.SubElement(envelope, f"{{{NS_SOAP}}}Body")
    op = ET.SubElement(body, f"{{{NS_TNS}}}{operacion}")
    for nombre, valor in campos.items():
        ET.SubElement(op, f"{{{NS_TNS}}}{nombre}").text = valor
    return ET.tostring(envelope, encoding="unicode")


class BooksUser(HttpUser):
    """Usuario virtual autenticado con JWT contra el microservicio books."""

    host = DEFAULT_HOST
    wait_time = between(1, 3)

    def on_start(self):
        if not EMAIL or not PASSWORD:
            raise StopUser("Faltan LOCUST_EMAIL / LOCUST_PASSWORD")
        self.isbns = []
        self.formato_prueba = FORMATO_POR_DEFECTO
        self._login()
        self._cargar_datos_iniciales()

    # ------------------------------------------------------------
    # Autenticacion
    # ------------------------------------------------------------
    def _login(self):
        """POST /login (servicio login) y guarda el JWT en los headers de la sesion."""
        with self.client.post(
            f"{LOGIN_URL}?format=json",
            json={"email": EMAIL, "password": PASSWORD},
            name="[login] POST /login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"login fallo: HTTP {resp.status_code}")
                raise StopUser(f"No se pudo iniciar sesion (HTTP {resp.status_code})")
            data = resp.json().get("data", {})
            token = data.get("token")
            if not token:
                resp.failure("la respuesta de login no trae data.token")
                raise StopUser("Login sin token")
            resp.success()

        self.client.headers["Authorization"] = f"Bearer {token}"
        self.token_expira = time.time() + int(data.get("expires_in", 1200))
        self.es_admin = data.get("user", {}).get("role_id") == ADMIN_ROLE_ID
        if self.es_admin:
            _ultimo_token_admin.update(host=self.host, token=token)

    def _asegurar_token(self):
        """Renueva el token si esta por expirar (pruebas de mas de 20 min)."""
        if time.time() > self.token_expira - TOKEN_MARGIN_SECONDS:
            self._login()

    def _cargar_datos_iniciales(self):
        """Obtiene ISBN reales (para GET /books/<isbn>) y un formato existente."""
        r = self.client.get("/books?format=json", name="/books?format=json")
        if r.ok:
            self.isbns = [libro["isbn"] for libro in r.json()]
        r = self.client.get("/formats?format=json", name="/formats?format=json")
        if r.ok and r.json():
            self.formato_prueba = r.json()[0]["nombre"]

    def _get(self, path, name=None):
        self._asegurar_token()
        return self.client.get(path, name=name or path)

    # ------------------------------------------------------------
    # Lecturas: /books (los tres URLs pedidos)
    # ------------------------------------------------------------
    @task(5)
    def listar_libros_default(self):
        self._get("/books")

    @task(5)
    def listar_libros_json(self):
        r = self._get("/books?format=json")
        if r.ok:
            self.isbns = [libro["isbn"] for libro in r.json()] or self.isbns

    @task(5)
    def listar_libros_xml(self):
        self._get("/books?format=xml")

    # ------------------------------------------------------------
    # Lecturas: detalle de un libro
    # ------------------------------------------------------------
    @task(3)
    def detalle_libro_json(self):
        if self.isbns:
            self._get(f"/books/{random.choice(self.isbns)}?format=json", name="/books/[isbn]?format=json")

    @task(3)
    def detalle_libro_xml(self):
        if self.isbns:
            self._get(f"/books/{random.choice(self.isbns)}?format=xml", name="/books/[isbn]?format=xml")

    @task(1)
    def detalle_libro_inexistente(self):
        """El 404 es la respuesta correcta: se marca como exito."""
        self._asegurar_token()
        with self.client.get(f"/books/{ISBN_INEXISTENTE}?format=json", name="/books/[isbn] (404 esperado)",
                             catch_response=True) as resp:
            if resp.status_code == 404:
                resp.success()
            else:
                resp.failure(f"se esperaba 404 y llego {resp.status_code}")

    # ------------------------------------------------------------
    # Lecturas: galeria, conceptos cloud, formatos
    # ------------------------------------------------------------
    @task(2)
    def galeria_json(self):
        self._get("/books/gallery?format=json")

    @task(2)
    def galeria_xml(self):
        self._get("/books/gallery?format=xml")

    @task(2)
    def conceptos_cloud_json(self):
        self._get("/cloud-concepts?format=json")

    @task(2)
    def conceptos_cloud_xml(self):
        self._get("/cloud-concepts?format=xml")

    @task(2)
    def formatos_json(self):
        self._get("/formats?format=json")

    @task(2)
    def formatos_xml(self):
        self._get("/formats?format=xml")

    # ------------------------------------------------------------
    # Salud y metricas
    # ------------------------------------------------------------
    @task(2)
    def health(self):
        self._get("/health")

    @task(1)
    def metrics(self):
        self._get("/metrics")

    # ------------------------------------------------------------
    # SOAP: solo operaciones de lectura (RegistrarClasificacion escribe
    # y ObtenerEstadisticasPorModelo pide WS-Security; no se incluyen).
    # ------------------------------------------------------------
    @task(1)
    def soap_conceptos_pendientes(self):
        self._soap("ObtenerConceptosPendientesRequest")

    @task(1)
    def soap_progreso_usuario(self):
        self._soap("ObtenerProgresoUsuarioRequest")

    def _soap(self, operacion):
        self._asegurar_token()
        self.client.post(
            "/soap",
            data=_soap_envelope(operacion, {"correoClasificador": EMAIL}),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            name=f"/soap {operacion}",
        )

    # ------------------------------------------------------------
    # Escrituras: flujo CRUD sobre un libro de prueba
    # ------------------------------------------------------------
    @task(1)
    def crud_libro_prueba(self):
        """POST -> GET -> PUT -> PATCH -> stock interno -> DELETE (siempre)."""
        self._asegurar_token()
        if not self.es_admin:
            self._escritura_sin_permiso()
            return

        isbn = "999" + "".join(random.choices("0123456789", k=10))
        libro = {
            "isbn": isbn,
            "titulo": f"Libro de prueba Locust {isbn}",
            "anio": 2026,
            "precio": 199.90,
            "stock": 10,
            "formato": self.formato_prueba,
        }
        with self.client.post("/books?format=json", json=libro, name="POST /books",
                              catch_response=True) as resp:
            if resp.status_code != 201:
                resp.failure(f"se esperaba 201 y llego {resp.status_code}: {resp.text[:200]}")
                return
            resp.success()

        with _lock:
            _libros_pendientes.add(isbn)
        try:
            self.client.get(f"/books/{isbn}?format=json", name="/books/[isbn] (libro de prueba)")
            self.client.put(f"/books/{isbn}?format=json", name="PUT /books/[isbn]",
                            json={"titulo": f"Libro de prueba Locust {isbn} (PUT)", "precio": 249.50, "stock": 8})
            self.client.patch(f"/books/{isbn}?format=json", name="PATCH /books/[isbn]", json={"stock": 12})
            self._stock_interno(isbn)
        finally:
            self._borrar_libro_prueba(isbn)

    def _borrar_libro_prueba(self, isbn):
        with self.client.delete(f"/books/{isbn}", name="DELETE /books/[isbn]", catch_response=True) as resp:
            if resp.status_code in (200, 404):
                resp.success()
                with _lock:
                    _libros_pendientes.discard(isbn)
            else:
                resp.failure(f"no se pudo borrar {isbn}: HTTP {resp.status_code}")

    def _stock_interno(self, isbn):
        """Reserva y libera 1 unidad del libro de prueba (el stock queda igual)."""
        if not INTERNAL_KEY:
            return
        body = {"items": [{"isbn": isbn, "cantidad": 1}]}
        headers = {"X-Internal-Key": INTERNAL_KEY}
        self.client.post("/books/internal/stock/reservar", json=body, headers=headers,
                         name="POST /books/internal/stock/reservar")
        self.client.post("/books/internal/stock/liberar", json=body, headers=headers,
                         name="POST /books/internal/stock/liberar")

    def _escritura_sin_permiso(self):
        """Cuenta sin rol admin: POST /books debe responder 403 y no crea nada."""
        with self.client.post("/books?format=json", json={}, name="POST /books (403 esperado, sin admin)",
                              catch_response=True) as resp:
            if resp.status_code == 403:
                resp.success()
            else:
                resp.failure(f"se esperaba 403 y llego {resp.status_code}")

    @task(1)
    def stock_interno_sin_clave(self):
        """Sin X-Internal-Key los endpoints internos deben responder 401 (no tocan stock)."""
        if INTERNAL_KEY:
            return
        self._asegurar_token()
        body = {"items": [{"isbn": ISBN_INEXISTENTE, "cantidad": 1}]}
        for accion in ("reservar", "liberar"):
            with self.client.post(f"/books/internal/stock/{accion}", json=body,
                                  name=f"POST /books/internal/stock/{accion} (401 esperado)",
                                  catch_response=True) as resp:
                if resp.status_code == 401:
                    resp.success()
                else:
                    resp.failure(f"se esperaba 401 y llego {resp.status_code}")
