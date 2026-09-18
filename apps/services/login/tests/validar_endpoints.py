#!/usr/bin/env python
"""
tests/validar_endpoints.py
Validacion de punta a punta del microservicio de autenticacion. Solo usa la
libreria estandar de Python. Requiere el servicio (puerto 5000), PostgreSQL y
Mailpit corriendo:

    python tests/validar_endpoints.py
    python tests/validar_endpoints.py --base http://IP:5000 --mailpit http://IP:8025

Crea usuarios nuevos (correos unicos por corrida). Sale con codigo 0 si todo
paso y 1 si algo fallo.
"""
import argparse
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Cliente:
    """Cliente HTTP con cookie jar propio (cada uno es un 'navegador')."""

    def __init__(self, base, seguir_redirecciones=False):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(self.jar)]
        if not seguir_redirecciones:
            handlers.append(_SinRedireccion())
        self.opener = urllib.request.build_opener(*handlers)

    def request(self, metodo, ruta, cuerpo=None, como="json"):
        datos, headers = None, {}
        if cuerpo is not None:
            if como == "json":
                datos, headers["Content-Type"] = json.dumps(cuerpo).encode(), "application/json"
            else:
                datos, headers["Content-Type"] = urllib.parse.urlencode(cuerpo).encode(), "application/x-www-form-urlencoded"
        req = urllib.request.Request(self.base + ruta, data=datos, headers=headers, method=metodo)
        try:
            with self.opener.open(req, timeout=15) as r:
                return r.status, dict(r.headers), r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read().decode("utf-8")

    def cookie(self, nombre):
        return next((c for c in self.jar if c.name == nombre), None)


def campo(texto, ruta):
    """Lee un campo del sobre: JSON o XML segun lo que llegue. ruta = 'data.user.email'."""
    partes = ruta.split(".")
    if texto.lstrip().startswith("{"):
        nodo = json.loads(texto)
        for p in partes:
            nodo = nodo[p]
        return nodo
    nodo = ET.fromstring(texto)
    for p in partes:
        nodo = nodo.find(p)
    return nodo.text


resultados = []


def check(nombre, condicion, detalle=""):
    resultados.append((nombre, bool(condicion)))
    print(f"  [{'OK ' if condicion else 'FALLO'}] {nombre}" + (f"  -> {detalle}" if not condicion and detalle else ""))
    return bool(condicion)


def seccion(titulo):
    print(f"\n== {titulo}")


def token_desde_mailpit(mailpit, correo, intentos=10):
    for _ in range(intentos):
        q = urllib.parse.quote(f"to:{correo}")
        with urllib.request.urlopen(f"{mailpit}/api/v1/search?query={q}", timeout=10) as r:
            lista = json.load(r)
        if lista.get("messages"):
            msg_id = lista["messages"][0]["ID"]
            with urllib.request.urlopen(f"{mailpit}/api/v1/message/{msg_id}", timeout=10) as r:
                return json.load(r)
        time.sleep(0.5)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5000")
    ap.add_argument("--mailpit", default="http://localhost:8025")
    a = ap.parse_args()

    sufijo = str(int(time.time()))
    correo_xml = f"prueba.xml.{sufijo}@prueba-libreria.com"
    correo_json = f"prueba.json.{sufijo}@prueba-libreria.com"
    password = "ClaveSegura123"
    datos = {"nombre": "María José", "apellido_paterno": "Pérez", "apellido_materno": "O'Brien-Ruiz",
             "email": correo_xml, "password": password}

    web = Cliente(a.base)  # navegador del usuario

    # ------------------------------------------------------------
    seccion("GET /health")
    for etiqueta, q in (("sin format (xml por defecto)", ""), ("?format=xml", "?format=xml"), ("?format=json", "?format=json"), ("?format=JSON (mayusculas)", "?format=JSON")):
        st, h, body = web.request("GET", "/health" + q)
        esperado = "json" if "json" in q.lower() else "xml"
        check(f"health {etiqueta}: 200 y {esperado}", st == 200 and esperado in h["Content-Type"] and campo(body, "data.database.status") == "up",
              f"{st} {h.get('Content-Type')} {body[:120]}")
    st, h, body = web.request("GET", "/health?format=yaml")
    check("format inválido -> 400 FORMATO_INVALIDO", st == 400 and campo(body, "code") == "FORMATO_INVALIDO", f"{st} {body[:120]}")
    st, h, body = web.request("GET", "/ruta-inexistente?format=json")
    check("ruta inexistente -> 404 con el mismo sobre (json)", st == 404 and campo(body, "status") == "error", f"{st} {body[:100]}")

    # ------------------------------------------------------------
    seccion("POST /register — validaciones")
    st, h, body = web.request("POST", "/register", {})
    check("cuerpo vacío {} -> 400 con los 5 campos señalados (xml)",
          st == 400 and all(f"<field>{c}</field>" in body for c in ("nombre", "apellido_paterno", "apellido_materno", "email", "password")), f"{st} {body[:200]}")
    st, h, body = web.request("POST", "/register?format=json", {**datos, "email": "no-es-un-correo"})
    check("email mal formado -> 400 (json)", st == 400 and any(e["field"] == "email" for e in json.loads(body)["errors"]), f"{st} {body[:200]}")
    st, h, body = web.request("POST", "/register?format=json", {**datos, "password": "corta"})
    check("password < 8 caracteres -> 400", st == 400 and any(e["field"] == "password" for e in json.loads(body)["errors"]), body[:200])
    st, h, body = web.request("POST", "/register?format=json", {**datos, "password": "a" * 80})
    check("password > 72 bytes -> 400", st == 400 and any(e["field"] == "password" for e in json.loads(body)["errors"]), body[:200])
    st, h, body = web.request("POST", "/register?format=json", {**datos, "nombre": "<script>alert(1)</script>"})
    check("nombre con markup/HTML -> 400", st == 400 and any(e["field"] == "nombre" for e in json.loads(body)["errors"]), body[:200])
    st, h, body = web.request("POST", "/register?format=json", {**datos, "apellido_materno": 12345})
    check("apellido_materno no textual -> 400", st == 400, body[:200])
    st, h, body = web.request("POST", "/register?format=json", None)
    check("sin cuerpo -> 400 CUERPO_INVALIDO", st == 400 and json.loads(body)["code"] == "CUERPO_INVALIDO", body[:200])

    # ------------------------------------------------------------
    seccion("POST /register — alta correcta (XML por defecto y JSON)")
    st, h, body = web.request("POST", "/register", datos)
    check("register sin format -> 201 y XML", st == 201 and "xml" in h["Content-Type"], f"{st} {body[:200]}")
    check("estado_cuenta = pendiente", st == 201 and campo(body, "data.estado_cuenta") == "pendiente")
    check("apellidos guardados atómicamente en la respuesta",
          st == 201 and campo(body, "data.apellido_paterno") == "Pérez" and campo(body, "data.apellido_materno") == "O'Brien-Ruiz")
    check("la respuesta no expone password ni hash", "password" not in body.lower() and "$2" not in body)

    st, h, body = web.request("POST", "/register?format=json", {**datos, "email": correo_json}, como="form")
    check("register ?format=json (cuerpo de formulario) -> 201 y JSON", st == 201 and "json" in h["Content-Type"] and json.loads(body)["data"]["email"] == correo_json, f"{st} {body[:200]}")

    st, h, body = web.request("POST", "/register?format=json", {**datos, "email": correo_xml.upper()})
    check("email duplicado (otra capitalización) -> 409 EMAIL_DUPLICADO", st == 409 and json.loads(body)["code"] == "EMAIL_DUPLICADO", f"{st} {body[:200]}")
    st, h, body = web.request("POST", "/register?format=xml", datos)
    check("email duplicado en xml -> 409", st == 409 and campo(body, "code") == "EMAIL_DUPLICADO")

    # ------------------------------------------------------------
    seccion("Mailpit — correo de confirmación")
    msg = token_desde_mailpit(a.mailpit, correo_xml)
    check("el correo llegó a Mailpit", msg is not None)
    enlace = None
    if msg:
        m = re.search(r"https?://[^\s\"<>]+/confirm\?token=[A-Za-z0-9_\-%]+", msg["Text"])
        enlace = m.group(0) if m else None
        check("asunto correcto", "Confirma tu cuenta" in msg["Subject"], msg["Subject"])
        check("destinatario correcto", any(t["Address"] == correo_xml for t in msg["To"]))
        check("contiene link /confirm?token=... (texto)", enlace is not None, msg["Text"][:200])
        check("contiene versión HTML con el mismo enlace", enlace is not None and enlace in msg["HTML"].replace("&amp;", "&"))
        check("el nombre aparece en el correo", "María José" in msg["Text"])
    with urllib.request.urlopen(f"{a.mailpit}/api/v1/search?query=" + urllib.parse.quote(f"to:{correo_xml}")) as r:
        check("un solo correo por registro (el 409 no reenvía)", json.load(r)["messages_count"] == 1)

    # ------------------------------------------------------------
    seccion("POST /login — antes de confirmar")
    st, h, body = web.request("POST", "/login", {"email": correo_xml, "password": password})
    check("cuenta pendiente con password correcto -> 403 CUENTA_NO_CONFIRMADA (xml)", st == 403 and campo(body, "code") == "CUENTA_NO_CONFIRMADA", f"{st} {body[:160]}")
    check("no se crea cookie de sesión", web.cookie("auth_session") is None)
    st, h, body = web.request("POST", "/login?format=json", {"email": correo_xml, "password": "otra-clave"})
    check("password incorrecto -> 401 (sin revelar estado)", st == 401 and json.loads(body)["code"] == "CREDENCIALES_INVALIDAS")
    st, h, body = web.request("POST", "/login?format=json", {"email": "nadie@prueba-libreria.com", "password": password})
    check("email desconocido -> 401 con el MISMO mensaje", st == 401 and json.loads(body)["code"] == "CREDENCIALES_INVALIDAS")
    st, h, body = web.request("POST", "/login?format=json", {"email": correo_xml})
    check("falta password -> 400", st == 400 and json.loads(body)["code"] == "VALIDACION")

    # ------------------------------------------------------------
    seccion("GET /session — sin sesión")
    st, h, body = web.request("GET", "/session")
    check("sin cookie -> 200, authenticated=false (xml)", st == 200 and campo(body, "data.authenticated") == "false", body[:160])
    st, h, body = web.request("GET", "/session?format=json")
    check("sin cookie -> 200, authenticated=false (json)", st == 200 and json.loads(body)["data"]["authenticated"] is False)

    # ------------------------------------------------------------
    seccion("GET /confirm y /confirmed")
    st, h, body = web.request("GET", "/confirm?token=token-inventado")
    check("token inválido -> 302 a /confirmed?status=invalid", st == 302 and "status=invalid" in h.get("Location", ""), f"{st} {h.get('Location')}")
    st, h, body = web.request("GET", "/confirm")
    check("sin token -> 302 a status=invalid", st == 302 and "status=invalid" in h.get("Location", ""))
    st, h, body = web.request("GET", "/confirm?token=xxx&format=json")
    check("token inválido con format=json -> 400 TOKEN_INVALIDO", st == 400 and json.loads(body)["code"] == "TOKEN_INVALIDO", body[:160])
    if enlace:
        ruta = enlace.replace(a.base, "") if enlace.startswith(a.base) else urllib.parse.urlparse(enlace).path + "?" + urllib.parse.urlparse(enlace).query
        st, h, body = web.request("GET", ruta)
        check("token válido -> 302 a /confirmed?status=ok", st == 302 and "status=ok" in h.get("Location", ""), f"{st} {h.get('Location')}")
        st, h, body = web.request("GET", h.get("Location", "/confirmed?status=ok"))
        check("/confirmed muestra visualmente 'Cuenta activada'", st == 200 and "Cuenta activada" in body and "text/html" in h["Content-Type"], f"{st}")
        st, h, body = web.request("GET", ruta)
        check("reusar el token -> 302 a status=already (no error)", st == 302 and "status=already" in h.get("Location", ""), f"{st} {h.get('Location')}")
        st, h, body = web.request("GET", ruta + "&format=json")
        check("reusar con format=json -> 200 CUENTA_YA_CONFIRMADA", st == 200 and json.loads(body)["code"] == "CUENTA_YA_CONFIRMADA", body[:160])
    st, h, body = web.request("GET", "/confirmed?status=invalid")
    check("/confirmed?status=invalid muestra error (400)", st == 400 and "Enlace no válido" in body)

    # ------------------------------------------------------------
    seccion("POST /login — cuenta confirmada")
    st, h, body = web.request("POST", "/login", {"email": correo_xml.upper(), "password": password})
    check("login (xml por defecto, email en mayúsculas) -> 200", st == 200 and "xml" in h["Content-Type"] and campo(body, "code") == "LOGIN_EXITOSO", f"{st} {body[:200]}")
    check("devuelve nombre y apellidos", st == 200 and campo(body, "data.user.nombre") == "María José" and campo(body, "data.user.apellido_paterno") == "Pérez")
    ck = web.cookie("auth_session")
    check("cookie auth_session creada", ck is not None)
    check("cookie HttpOnly", ck is not None and ck.has_nonstandard_attr("HttpOnly"))
    check("la respuesta no expone el hash", "$2" not in body and "password" not in body.lower())

    seccion("GET /session — con sesión")
    st, h, body = web.request("GET", "/session")
    check("session xml -> authenticated=true y usuario", st == 200 and campo(body, "data.authenticated") == "true" and campo(body, "data.user.email") == correo_xml, body[:200])
    st, h, body = web.request("GET", "/session?format=json")
    check("session json -> authenticated=true", st == 200 and json.loads(body)["data"]["authenticated"] is True and json.loads(body)["data"]["user"]["estado_cuenta"] == "confirmado")
    otro = Cliente(a.base)
    st, h, body = otro.request("GET", "/session?format=json")
    check("otro navegador (sin cookie) no ve la sesión", json.loads(body)["data"]["authenticated"] is False)

    seccion("POST /logout")
    st, h, body = web.request("POST", "/logout")
    check("logout (xml) -> 200 LOGOUT_EXITOSO", st == 200 and campo(body, "code") == "LOGOUT_EXITOSO", body[:160])
    st, h, body = web.request("GET", "/session?format=json")
    check("después del logout /session -> authenticated=false", json.loads(body)["data"]["authenticated"] is False)
    st, h, body = web.request("POST", "/logout?format=json")
    check("logout sin sesión es idempotente (200, json)", st == 200 and json.loads(body)["data"]["authenticated"] is False)
    st, h, body = web.request("POST", "/login?format=json", {"email": correo_xml, "password": password})
    check("login otra vez (json) -> 200", st == 200 and json.loads(body)["code"] == "LOGIN_EXITOSO")

    # ------------------------------------------------------------
    seccion("Swagger")
    st, h, body = web.request("GET", "/apidocs/")
    check("/apidocs/ (Swagger UI) -> 200 html", st == 200 and "text/html" in h["Content-Type"])
    st, h, body = web.request("GET", "/apispec_1.json")
    spec = json.loads(body) if st == 200 else {"paths": {}}
    for ruta, metodo in (("/register", "post"), ("/login", "post"), ("/logout", "post"), ("/session", "get"), ("/health", "get"), ("/confirm", "get")):
        op = spec["paths"].get(ruta, {}).get(metodo)
        ok = bool(op) and {"application/xml", "application/json"} <= set(op.get("produces", []))
        check(f"spec documenta {metodo.upper()} {ruta} con application/xml y application/json", ok)

    fallos = [n for n, ok in resultados if not ok]
    print(f"\n{len(resultados) - len(fallos)}/{len(resultados)} comprobaciones correctas")
    if fallos:
        print("FALLARON:\n  - " + "\n  - ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
