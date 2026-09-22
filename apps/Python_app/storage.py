"""
storage.py
Persistencia local de la configuracion de la app (URLs de los
microservicios). Es el equivalente de escritorio al localStorage del
navegador: un archivo JSON junto al programa que sobrevive entre
ejecuciones.
"""
import json
from pathlib import Path

_ARCHIVO = Path(__file__).resolve().parent / "local_storage.json"

VALORES_POR_DEFECTO = {
    "login_base_url": "http://localhost:5000",
    "books_base_url": "http://localhost:5001",
}


def cargar():
    if not _ARCHIVO.exists():
        return dict(VALORES_POR_DEFECTO)
    try:
        datos = json.loads(_ARCHIVO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(VALORES_POR_DEFECTO)
    salida = dict(VALORES_POR_DEFECTO)
    salida.update({k: v for k, v in datos.items() if isinstance(v, str) and v.strip()})
    return salida


def guardar(config):
    _ARCHIVO.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
