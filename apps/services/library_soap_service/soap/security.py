"""
soap/security.py
Validacion de WS-Security (UsernameToken) para operaciones sensibles
(Tarea 1 del trabajo en casa). Lee el token del soap:Header, nunca
del soap:Body -- separa credenciales de los datos de negocio.

La contrasena esperada NUNCA se guarda en texto plano: se guarda su
hash (werkzeug.security.generate_password_hash, dependencia que ya
trae Flask) en la variable de entorno WS_SECURITY_PASSWORD_HASH.
"""
import os
from werkzeug.security import check_password_hash

from soap.faults import AutenticacionInvalida

NS_WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"


def validar_ws_security(header_element):
    """
    Recibe el elemento <soap:Header> (o None si no vino) y valida
    el UsernameToken contra las credenciales configuradas en el
    servidor. Lanza AutenticacionInvalida si algo no coincide.
    Devuelve el username validado si todo esta correcto.
    """
    if header_element is None:
        raise AutenticacionInvalida("Falta el soap:Header con credenciales WS-Security.")

    security_el = header_element.find(f"{{{NS_WSSE}}}Security")
    if security_el is None:
        raise AutenticacionInvalida("Falta el elemento wsse:Security en el Header.")

    token_el = security_el.find(f"{{{NS_WSSE}}}UsernameToken")
    if token_el is None:
        raise AutenticacionInvalida("Falta el elemento wsse:UsernameToken.")

    username_el = token_el.find(f"{{{NS_WSSE}}}Username")
    password_el = token_el.find(f"{{{NS_WSSE}}}Password")

    if username_el is None or password_el is None or not (username_el.text or "").strip():
        raise AutenticacionInvalida("UsernameToken incompleto (falta Username o Password).")

    username = username_el.text.strip()
    password = (password_el.text or "").strip()

    expected_user = os.getenv("WS_SECURITY_USER")
    expected_hash = os.getenv("WS_SECURITY_PASSWORD_HASH")

    if not expected_user or not expected_hash:
        raise AutenticacionInvalida("Credenciales invalidas.")

    if username != expected_user:
        raise AutenticacionInvalida("Credenciales invalidas.")

    if not check_password_hash(expected_hash, password):
        raise AutenticacionInvalida("Credenciales invalidas.")

    return username