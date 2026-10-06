"""scripts/crear_admin.py: asigna el rol, repara el hash de ejemplo y es idempotente."""
import importlib.util
from pathlib import Path

import pytest

from conftest import ADMIN_ID, ANA_ID, FakeRepo
from services import passwords

_RUTA = Path(__file__).resolve().parents[1] / "scripts" / "crear_admin.py"
_spec = importlib.util.spec_from_file_location("crear_admin", _RUTA)
crear_admin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crear_admin)

EMAIL, CLAVE = "admin@libreria.com", "ClaveDelAdmin123"


@pytest.fixture
def repo():
    """El admin tal como lo dejo el monolito: marcado con es_admin pero con el hash de ejemplo."""
    fake = FakeRepo()
    fake.filas[ADMIN_ID].update(role_id=2, es_admin=True, password_hash="hash_de_ejemplo")
    return fake


@pytest.mark.parametrize("ejemplo", ["hash_de_ejemplo", "CAMBIAR_POR_HASH_BCRYPT_REAL"])
def test_asigna_rol_y_reemplaza_el_hash_de_ejemplo(repo, ejemplo):
    repo.filas[ADMIN_ID].update(password_hash=ejemplo, activo=False)
    usuario, acciones = crear_admin.asegurar_admin(repo, EMAIL, CLAVE)

    fila = repo.filas[ADMIN_ID]
    assert usuario["role_id"] == 1 and fila["es_admin"] is True and fila["activo"] is True
    assert passwords.es_hash_bcrypt(fila["password_hash"])
    assert passwords.verify_password(CLAVE, fila["password_hash"])       # login la aceptara
    assert len(acciones) == 3


def test_es_idempotente(repo):
    crear_admin.asegurar_admin(repo, EMAIL, CLAVE)
    despues_de_la_primera = {k: dict(v) for k, v in repo.filas.items()}

    usuario, acciones = crear_admin.asegurar_admin(repo, EMAIL, "OtraClaveDistinta456")
    assert acciones == [] and usuario["role_id"] == 1
    assert repo.filas == despues_de_la_primera                           # ni el hash cambia en la segunda corrida
    assert passwords.verify_password(CLAVE, repo.filas[ADMIN_ID]["password_hash"])


def test_no_toca_un_hash_real(repo):
    real = passwords.hash_password("LaQueYaTenia123")
    repo.filas[ADMIN_ID]["password_hash"] = real
    _, acciones = crear_admin.asegurar_admin(repo, EMAIL, CLAVE)
    assert repo.filas[ADMIN_ID]["password_hash"] == real
    assert acciones == ["role_id = 1 (admin)"]


def test_no_toca_a_los_demas_usuarios(repo):
    antes = dict(repo.filas[ANA_ID])
    crear_admin.asegurar_admin(repo, EMAIL, CLAVE)
    assert repo.filas[ANA_ID] == antes and repo.filas[ANA_ID]["role_id"] == 2


def test_crea_la_cuenta_si_no_existe(repo):
    usuario, acciones = crear_admin.asegurar_admin(repo, "nuevo.admin@libreria.com", CLAVE)
    fila = repo.filas[usuario["id_usuario"]]
    assert fila["role_id"] == 1 and fila["es_admin"] and fila["activo"] and fila["estado_cuenta"] == "confirmado"
    assert passwords.verify_password(CLAVE, fila["password_hash"]) and len(acciones) == 1
    assert crear_admin.asegurar_admin(repo, "nuevo.admin@libreria.com", CLAVE)[1] == []


@pytest.mark.parametrize("clave", ["", "corta"])
def test_sin_admin_password_valida_no_reemplaza_el_hash(repo, clave):
    with pytest.raises(SystemExit) as error:
        crear_admin.asegurar_admin(repo, EMAIL, clave)
    assert "ADMIN_PASSWORD" in str(error.value)
    assert repo.filas[ADMIN_ID]["password_hash"] == "hash_de_ejemplo"


def test_si_ya_hay_otro_admin_y_la_base_solo_admite_uno_lo_explica(repo, monkeypatch):
    repo.un_solo_admin = True
    repo.filas[ADMIN_ID].update(role_id=1)
    monkeypatch.setenv("ADMIN_EMAIL", "ana@correo.com")
    monkeypatch.setenv("ADMIN_PASSWORD", CLAVE)
    monkeypatch.setattr(crear_admin.repository, "unit_of_work", repo.unit_of_work)
    with pytest.raises(SystemExit) as error:
        crear_admin.main()
    assert "un_solo_admin" in str(error.value) and repo.filas[ANA_ID]["role_id"] == 2


def test_no_imprime_la_password_ni_el_hash(repo, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_EMAIL", EMAIL)
    monkeypatch.setenv("ADMIN_PASSWORD", CLAVE)
    monkeypatch.setattr(crear_admin.repository, "unit_of_work", repo.unit_of_work)
    crear_admin.main()
    crear_admin.main()                                                   # segunda corrida: sin cambios

    salida = capsys.readouterr()
    texto = salida.out + salida.err
    assert CLAVE not in texto and "$2b$" not in texto and repo.filas[ADMIN_ID]["password_hash"] not in texto
    assert "role_id=1" in texto and "sin cambios" in texto
