"""CRUD, permisos (401/403), revocacion de sesiones, ultimo admin y Redis caido."""
import pytest

from common import redis_client, redis_keys
from conftest import ADMIN_ID, ANA_ID, LUIS_ID, PASSWORD, RedisQueFallaAlRevocar
from services import login_client, passwords

NUEVO = {"nombre": "María José", "apellido_paterno": "O'Brien-Ruiz", "apellido_materno": "",
         "email": "Maria@Correo.com", "password": "ClaveNueva123"}


def _error(resp):
    return resp.get_json()["error"]


def _sesiones_de(fake_redis, user_id):
    return fake_redis.smembers(redis_keys.user_sessions(user_id))


# ------------------------------------------------------------------ 401 y 403
@pytest.mark.parametrize("metodo, ruta", [
    ("get", "/users"), ("get", "/users/me"), ("get", "/users/31"), ("post", "/users"), ("put", "/users/31"),
    ("patch", "/users/31"), ("delete", "/users/31"), ("patch", "/users/31/password"),
    ("patch", "/users/31/email"), ("patch", "/users/31/role"), ("get", "/roles"),
])
def test_sin_token_401(client, fake_redis, metodo, ruta):
    resp = getattr(client, metodo)(ruta, json={})
    assert resp.status_code == 401 and _error(resp) == "TOKEN_AUSENTE"


@pytest.mark.parametrize("metodo, ruta, cuerpo", [
    ("get", "/users", None),
    ("post", "/users", NUEVO),
    ("delete", f"/users/{LUIS_ID}", None),
    ("patch", f"/users/{ANA_ID}/role", {"role_id": 1}),
    ("get", f"/users/{LUIS_ID}", None),                       # otro usuario
    ("patch", f"/users/{LUIS_ID}", {"nombre": "Otro"}),
    ("patch", f"/users/{LUIS_ID}/password", {"password_nueva": "ClaveNueva123"}),
    ("patch", f"/users/{LUIS_ID}/email", {"email": "x@correo.com"}),
    ("get", "/users/9999", None),                             # 403 antes que 404: no revela que ids existen
])
def test_cliente_recibe_403(client, repo, ana, confirmaciones, metodo, ruta, cuerpo):
    antes = {k: dict(v) for k, v in repo.filas.items()}
    resp = getattr(client, metodo)(ruta, json=cuerpo, headers=ana)
    assert resp.status_code == 403 and _error(resp) == "ROL_INSUFICIENTE"
    assert repo.filas == antes and confirmaciones == []


@pytest.mark.parametrize("cuerpo", [{"role_id": 1}, {"activo": False}, {"nombre": "Ana", "role_id": 1}])
def test_cliente_no_cambia_su_rol_ni_su_estado(client, repo, ana, cuerpo):
    for metodo in (client.patch, client.put):
        assert metodo(f"/users/{ANA_ID}", json=cuerpo, headers=ana).status_code == 403
    assert repo.filas[ANA_ID]["role_id"] == 2 and repo.filas[ANA_ID]["activo"] is True


# ------------------------------------------------------------------ lectura
def test_listado_paginado(client, admin):
    resp = client.get("/users?per_page=2", headers=admin)
    datos = resp.get_json()
    assert resp.status_code == 200
    assert [u["id_usuario"] for u in datos["items"]] == [ADMIN_ID, ANA_ID]
    assert (datos["page"], datos["per_page"], datos["total"], datos["pages"]) == (1, 2, 3, 2)
    assert [u["id_usuario"] for u in client.get("/users?per_page=2&page=2", headers=admin).get_json()["items"]] == [LUIS_ID]


def test_listado_con_filtros(client, repo, admin):
    repo.filas[LUIS_ID]["activo"] = False
    ids = lambda q: [u["id_usuario"] for u in client.get(f"/users?{q}", headers=admin).get_json()["items"]]  # noqa: E731
    assert ids("q=ANA") == [ANA_ID]
    assert ids("q=correo.com") == [ANA_ID, LUIS_ID]
    assert ids("role_id=1") == [ADMIN_ID]
    assert ids("activo=false") == [LUIS_ID]
    assert ids("activo=true&role_id=2") == [ANA_ID]
    assert ids("q=nadie") == []


@pytest.mark.parametrize("query", ["page=0", "page=x", "role_id=abc", "activo=quiza", "per_page=0"])
def test_listado_filtros_invalidos_400(client, admin, query):
    resp = client.get(f"/users?{query}", headers=admin)
    assert resp.status_code == 400 and _error(resp) == "VALIDACION"


def test_per_page_tiene_tope(client, admin):
    assert client.get("/users?per_page=5000", headers=admin).get_json()["per_page"] == 100


def test_me_y_formato_del_usuario(client, ana):
    resp = client.get("/users/me", headers=ana)
    assert resp.status_code == 200
    assert resp.get_json() == {
        "id_usuario": ANA_ID, "nombre": "Ana", "apellido_paterno": "Pérez", "apellido_materno": None,
        "email": "ana@correo.com", "role_id": 2, "role": "cliente", "activo": True, "email_verificado": True,
        "created_at": "2026-09-01T10:00:00", "updated_at": "2026-09-01T10:00:00",
    }


def test_usuario_ve_su_cuenta_y_admin_cualquiera(client, admin, ana):
    assert client.get(f"/users/{ANA_ID}", headers=ana).get_json()["email"] == "ana@correo.com"
    assert client.get(f"/users/{ANA_ID}", headers=admin).status_code == 200
    resp = client.get("/users/9999", headers=admin)
    assert resp.status_code == 404 and _error(resp) == "USUARIO_NO_ENCONTRADO"


def test_nunca_se_devuelve_password_hash(client, repo, admin, ana, confirmaciones):
    respuestas = [
        client.get("/users", headers=admin), client.get("/users/me", headers=ana),
        client.get(f"/users/{ANA_ID}", headers=admin), client.post("/users", json=NUEVO, headers=admin),
        client.patch(f"/users/{LUIS_ID}", json={"nombre": "Luisa"}, headers=admin),
        client.patch(f"/users/{LUIS_ID}/email", json={"email": "luisa@correo.com"}, headers=admin),
        client.get(f"/users/internal/{ANA_ID}", headers={"X-Internal-Key": "clave-interna-de-pruebas"}),
    ]
    for resp in respuestas:
        assert resp.status_code in (200, 201)
        texto = resp.get_data(as_text=True)
        assert "password" not in texto and "$2b$" not in texto


def test_roles(client, ana):
    resp = client.get("/roles", headers=ana)
    assert resp.status_code == 200 and [(r["role_id"], r["nombre"]) for r in resp.get_json()] == [(1, "admin"), (2, "cliente")]


# ------------------------------------------------------------------ alta
def test_admin_crea_usuario_que_puede_iniciar_sesion(client, repo, admin):
    resp = client.post("/users", json=NUEVO, headers=admin)
    assert resp.status_code == 201
    creado = resp.get_json()
    assert creado["email"] == "maria@correo.com" and creado["nombre"] == "María José"
    assert creado["role_id"] == 2 and creado["activo"] and creado["email_verificado"]      # confirmado: login lo acepta
    assert creado["apellido_materno"] is None

    fila = repo.filas[creado["id_usuario"]]
    assert fila["estado_cuenta"] == "confirmado" and fila["es_admin"] is False
    assert passwords.es_hash_bcrypt(fila["password_hash"]) and fila["password_hash"] != NUEVO["password"]
    assert passwords.verify_password(NUEVO["password"], fila["password_hash"])              # mismo algoritmo que login


def test_admin_crea_otro_admin(client, repo, admin):
    creado = client.post("/users", json={**NUEVO, "role_id": 1}, headers=admin).get_json()
    assert creado["role"] == "admin" and repo.filas[creado["id_usuario"]]["es_admin"] is True


def test_alta_con_email_duplicado_409(client, repo, admin):
    resp = client.post("/users", json={**NUEVO, "email": "ANA@correo.com"}, headers=admin)
    assert resp.status_code == 409 and _error(resp) == "EMAIL_DUPLICADO" and len(repo.filas) == 3


@pytest.mark.parametrize("cambio", [
    {"nombre": ""}, {"nombre": "R2D2"}, {"nombre": "<script>"}, {"email": "no-es-correo"},
    {"email": "ana@sin-mx.test"}, {"password": "corta"}, {"password": "x" * 80}, {"role_id": 99},
    {"role_id": "1"}, {"activo": "si"},
])
def test_alta_con_datos_invalidos_400(client, repo, admin, cambio):
    resp = client.post("/users", json={**NUEVO, **cambio}, headers=admin)
    assert resp.status_code == 400 and _error(resp) == "VALIDACION" and len(repo.filas) == 3


def test_cuerpo_que_no_es_json_400(client, admin):
    assert client.post("/users", data="hola", headers=admin).status_code == 400
    assert client.patch(f"/users/{ANA_ID}", json=["lista"], headers=admin).status_code == 400


# ------------------------------------------------------------------ PUT y PATCH
def test_usuario_edita_su_nombre_y_conserva_la_sesion(client, repo, ana, fake_redis):
    resp = client.patch(f"/users/{ANA_ID}", json={"nombre": "  Ana   María "}, headers=ana)
    assert resp.status_code == 200 and resp.get_json()["nombre"] == "Ana María"
    assert resp.get_json()["apellido_paterno"] == "Pérez"            # PATCH no toca lo que no se envia
    assert resp.get_json()["updated_at"] != "2026-09-01T10:00:00"
    assert client.get("/users/me", headers=ana).status_code == 200   # editar el nombre no cierra la sesion


def test_put_reemplaza_el_perfil(client, repo, ana):
    resp = client.put(f"/users/{ANA_ID}", json={"nombre": "Ana", "apellido_materno": "Ruiz"}, headers=ana)
    assert resp.status_code == 200
    assert resp.get_json()["apellido_paterno"] is None and resp.get_json()["apellido_materno"] == "Ruiz"
    assert client.put(f"/users/{ANA_ID}", json={"apellido_paterno": "Soto"}, headers=ana).status_code == 400


def test_patch_vacio_o_con_campos_de_otro_endpoint_400(client, repo, ana):
    assert client.patch(f"/users/{ANA_ID}", json={}, headers=ana).status_code == 400
    for cuerpo in ({"email": "otro@correo.com"}, {"password": "ClaveNueva123"}):
        resp = client.patch(f"/users/{ANA_ID}", json=cuerpo, headers=ana)
        assert resp.status_code == 400 and "PATCH /users/{id}/" in resp.get_json()["message"]
    assert repo.filas[ANA_ID]["correo"] == "ana@correo.com"


def test_admin_cambia_rol_y_estado_con_patch(client, repo, admin):
    resp = client.patch(f"/users/{ANA_ID}", json={"role_id": 1, "activo": True}, headers=admin)
    assert resp.status_code == 200 and resp.get_json()["role"] == "admin"
    assert repo.filas[ANA_ID]["es_admin"] is True                    # columna del monolito sincronizada


# ------------------------------------------------------------------ revocacion de sesiones
def test_cambiar_password_propia_revoca_el_token_anterior(client, repo, ana, sesion, fake_redis):
    otra_sesion = sesion(ANA_ID, 2)                                  # misma usuaria en otro dispositivo
    resp = client.patch(f"/users/{ANA_ID}/password", headers=ana,
                        json={"password_actual": PASSWORD, "password_nueva": "ClaveNueva123"})
    assert resp.status_code == 200
    assert passwords.verify_password("ClaveNueva123", repo.filas[ANA_ID]["password_hash"])

    for cabecera in (ana, otra_sesion):                              # el token anterior recibe 401
        rechazo = client.get("/users/me", headers=cabecera)
        assert rechazo.status_code == 401 and _error(rechazo) == "TOKEN_REVOCADO"
    assert _sesiones_de(fake_redis, ANA_ID) == set()
    assert list(fake_redis.scan_iter("session:*")) == [] and list(fake_redis.scan_iter("refresh:*")) == []
    assert len(list(fake_redis.scan_iter("jwt:revoked:*"))) == 2


def test_cambiar_password_propia_exige_la_actual(client, repo, ana):
    original = repo.filas[ANA_ID]["password_hash"]
    sin_actual = client.patch(f"/users/{ANA_ID}/password", json={"password_nueva": "ClaveNueva123"}, headers=ana)
    assert sin_actual.status_code == 400 and _error(sin_actual) == "VALIDACION"
    mala = client.patch(f"/users/{ANA_ID}/password", headers=ana,
                        json={"password_actual": "incorrecta", "password_nueva": "ClaveNueva123"})
    assert mala.status_code == 400 and _error(mala) == "PASSWORD_ACTUAL_INCORRECTA"
    corta = client.patch(f"/users/{ANA_ID}/password", headers=ana,
                         json={"password_actual": PASSWORD, "password_nueva": "corta"})
    assert corta.status_code == 400
    assert repo.filas[ANA_ID]["password_hash"] == original
    assert client.get("/users/me", headers=ana).status_code == 200   # la sesion sigue viva


def test_admin_restablece_password_sin_la_actual_y_cierra_las_sesiones(client, repo, admin, ana):
    resp = client.patch(f"/users/{ANA_ID}/password", json={"password_nueva": "Restablecida123"}, headers=admin)
    assert resp.status_code == 200
    assert passwords.verify_password("Restablecida123", repo.filas[ANA_ID]["password_hash"])
    assert client.get("/users/me", headers=ana).status_code == 401   # token anterior de la usuaria
    assert client.get("/users/me", headers=admin).status_code == 200 # el admin conserva la suya


def test_admin_necesita_su_password_actual_para_cambiar_la_propia(client, admin):
    resp = client.patch(f"/users/{ADMIN_ID}/password", json={"password_nueva": "Restablecida123"}, headers=admin)
    assert resp.status_code == 400


def test_cambiar_rol_revoca_las_sesiones_del_usuario(client, repo, admin, ana, fake_redis):
    resp = client.patch(f"/users/{ANA_ID}/role", json={"role_id": 1}, headers=admin)
    assert resp.status_code == 200 and resp.get_json()["role_id"] == 1
    assert repo.filas[ANA_ID]["es_admin"] is True
    rechazo = client.get("/users/me", headers=ana)                   # su JWT decia role_id = 2
    assert rechazo.status_code == 401 and _error(rechazo) == "TOKEN_REVOCADO"
    assert _sesiones_de(fake_redis, ANA_ID) == set()


def test_cambiar_al_mismo_rol_no_cierra_sesiones(client, admin, ana):
    assert client.patch(f"/users/{ANA_ID}/role", json={"role_id": 2}, headers=admin).status_code == 200
    assert client.get("/users/me", headers=ana).status_code == 200


def test_rol_invalido_400(client, repo, admin):
    for cuerpo in ({}, {"role_id": 99}, {"role_id": "admin"}):
        assert client.patch(f"/users/{ANA_ID}/role", json=cuerpo, headers=admin).status_code == 400
    assert repo.filas[ANA_ID]["role_id"] == 2


def test_delete_es_baja_logica_revoca_y_es_idempotente(client, repo, admin, ana):
    resp = client.delete(f"/users/{ANA_ID}", headers=admin)
    assert resp.status_code == 200 and resp.get_json()["activo"] is False
    assert ANA_ID in repo.filas and repo.filas[ANA_ID]["activo"] is False        # la fila no se borra
    assert client.get("/users/me", headers=ana).status_code == 401
    assert client.delete(f"/users/{ANA_ID}", headers=admin).status_code == 200
    assert client.delete("/users/9999", headers=admin).status_code == 404


def test_admin_reactiva_con_patch(client, repo, admin):
    repo.filas[LUIS_ID]["activo"] = False
    assert client.patch(f"/users/{LUIS_ID}", json={"activo": True}, headers=admin).get_json()["activo"] is True


# ------------------------------------------------------------------ ultimo admin
@pytest.mark.parametrize("metodo, ruta, cuerpo", [
    ("patch", f"/users/{ADMIN_ID}/role", {"role_id": 2}),
    ("patch", f"/users/{ADMIN_ID}", {"role_id": 2}),
    ("patch", f"/users/{ADMIN_ID}", {"activo": False}),
    ("put", f"/users/{ADMIN_ID}", {"nombre": "Admin", "activo": False}),
    ("delete", f"/users/{ADMIN_ID}", None),
])
def test_el_ultimo_admin_no_pierde_el_rol_ni_se_desactiva(client, repo, admin, metodo, ruta, cuerpo):
    resp = getattr(client, metodo)(ruta, json=cuerpo, headers=admin)
    assert resp.status_code == 409 and _error(resp) == "ULTIMO_ADMIN"
    assert repo.filas[ADMIN_ID]["role_id"] == 1 and repo.filas[ADMIN_ID]["activo"] is True
    assert client.get("/users/me", headers=admin).status_code == 200             # y conserva su sesion


def test_un_admin_inactivo_no_cuenta_como_otro_admin(client, repo, admin):
    repo.filas[ANA_ID].update(role_id=1, es_admin=True, activo=False)
    assert client.delete(f"/users/{ADMIN_ID}", headers=admin).status_code == 409


def test_con_dos_admins_uno_si_puede_dejar_de_serlo(client, repo, admin):
    repo.filas[ANA_ID].update(role_id=1, es_admin=True)
    resp = client.patch(f"/users/{ADMIN_ID}/role", json={"role_id": 2}, headers=admin)
    assert resp.status_code == 200 and repo.filas[ADMIN_ID]["es_admin"] is False
    assert client.get("/users/me", headers=admin).status_code == 401             # su token de admin ya no sirve


# ------------------------------------------------------------------ regla del monolito: un solo admin
def test_con_el_indice_un_solo_admin_no_se_nombra_un_segundo_admin(client, repo, admin, ana):
    repo.un_solo_admin = True
    for resp in (client.patch(f"/users/{ANA_ID}/role", json={"role_id": 1}, headers=admin),
                 client.patch(f"/users/{ANA_ID}", json={"role_id": 1}, headers=admin),
                 client.post("/users", json={**NUEVO, "role_id": 1}, headers=admin)):
        assert resp.status_code == 409 and _error(resp) == "UN_SOLO_ADMIN"
        assert "opcional_permitir_varios_admins.sql" in resp.get_json()["message"]
    assert repo.filas[ANA_ID]["role_id"] == 2 and len(repo.filas) == 3 and repo.commits == 0
    assert client.get("/users/me", headers=ana).status_code == 200               # y no se le cerro la sesion
    assert client.post("/users", json=NUEVO, headers=admin).status_code == 201   # los clientes si se crean


# ------------------------------------------------------------------ correo
def test_cambiar_email_deja_pendiente_y_pide_confirmacion_a_login(client, repo, ana, confirmaciones):
    resp = client.patch(f"/users/{ANA_ID}/email", json={"email": " Ana.Nueva@Correo.com "}, headers=ana)
    assert resp.status_code == 200
    assert resp.get_json()["user"]["email"] == "ana.nueva@correo.com"
    assert resp.get_json()["user"]["email_verificado"] is False
    assert repo.filas[ANA_ID]["estado_cuenta"] == "pendiente"
    assert confirmaciones == [(ANA_ID, "ana.nueva@correo.com", "Ana")]


def test_cambiar_email_invalido_duplicado_o_igual(client, repo, ana, confirmaciones):
    for email in ("no-es-correo", "ana@sin-mx.test", "ana@correo.com", ""):
        resp = client.patch(f"/users/{ANA_ID}/email", json={"email": email}, headers=ana)
        assert resp.status_code == 400 and _error(resp) == "VALIDACION"
    duplicado = client.patch(f"/users/{ANA_ID}/email", json={"email": "luis@correo.com"}, headers=ana)
    assert duplicado.status_code == 409 and _error(duplicado) == "EMAIL_DUPLICADO"
    assert repo.filas[ANA_ID]["correo"] == "ana@correo.com" and confirmaciones == []


def test_si_login_no_envia_el_correo_no_se_cambia_nada(client, repo, ana, monkeypatch):
    class Respuesta:
        status_code = 503

    monkeypatch.setattr(login_client.requests, "post", lambda *a, **k: Respuesta())
    resp = client.patch(f"/users/{ANA_ID}/email", json={"email": "ana.nueva@correo.com"}, headers=ana)
    assert resp.status_code == 503 and _error(resp) == "CORREO_NO_ENVIADO"
    assert repo.filas[ANA_ID]["correo"] == "ana@correo.com"                      # ROLLBACK
    assert repo.filas[ANA_ID]["estado_cuenta"] == "confirmado" and repo.commits == 0


def test_la_confirmacion_se_pide_a_login_con_la_clave_interna(client, repo, ana, monkeypatch):
    llamadas = []

    class Respuesta:
        status_code = 202

    monkeypatch.setattr(login_client.requests, "post", lambda url, **k: llamadas.append((url, k)) or Respuesta())
    assert client.patch(f"/users/{ANA_ID}/email", json={"email": "ana.nueva@correo.com"}, headers=ana).status_code == 200
    url, kwargs = llamadas[0]
    assert url == "http://127.0.0.1:5000/internal/confirmation" and kwargs["timeout"] == 3
    assert kwargs["headers"]["X-Internal-Key"] == "clave-interna-de-pruebas"
    assert kwargs["json"] == {"user_id": ANA_ID, "email": "ana.nueva@correo.com", "nombre": "Ana"}


# ------------------------------------------------------------------ Redis caido
@pytest.mark.parametrize("metodo, ruta, cuerpo", [
    ("patch", f"/users/{ANA_ID}/password", {"password_nueva": "Restablecida123"}),
    ("patch", f"/users/{ANA_ID}/role", {"role_id": 1}),
    ("patch", f"/users/{ANA_ID}", {"activo": False}),
    ("delete", f"/users/{ANA_ID}", None),
])
def test_si_redis_falla_al_revocar_503_y_no_se_aplica_el_cambio(client, repo, admin, fake_redis, metodo, ruta, cuerpo):
    antes = {k: dict(v) for k, v in repo.filas.items()}
    redis_client.set_client(RedisQueFallaAlRevocar(fake_redis))
    resp = getattr(client, metodo)(ruta, json=cuerpo, headers=admin)
    assert resp.status_code == 503 and _error(resp) == "REDIS_NO_DISPONIBLE"
    assert repo.filas == antes and repo.commits == 0                             # ROLLBACK: nada cambio


def test_redis_totalmente_caido_503_en_cualquier_ruta_protegida(client, repo, admin, fake_redis):
    class Caido:
        def __getattr__(self, nombre):
            def falla(*args, **kwargs):
                import redis
                raise redis.ConnectionError("caido")
            return falla

    redis_client.set_client(Caido())
    assert client.get("/users", headers=admin).status_code == 503
    assert client.delete(f"/users/{ANA_ID}", headers=admin).status_code == 503
    assert repo.filas[ANA_ID]["activo"] is True


# ------------------------------------------------------------------ interno
def test_endpoint_interno_exige_la_clave(client, repo, admin):
    assert client.get(f"/users/internal/{ANA_ID}").status_code == 401
    assert client.get(f"/users/internal/{ANA_ID}", headers=admin).status_code == 401      # un JWT no basta
    resp = client.get(f"/users/internal/{ANA_ID}", headers={"X-Internal-Key": "clave-interna-de-pruebas"})
    assert resp.status_code == 200
    assert resp.get_json() == {"id_usuario": ANA_ID, "nombre": "Ana Pérez", "email": "ana@correo.com",
                               "role_id": 2, "activo": True, "email_verificado": True}
    assert client.get("/users/internal/9999", headers={"X-Internal-Key": "clave-interna-de-pruebas"}).status_code == 404
