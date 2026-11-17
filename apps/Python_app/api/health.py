"""
api/health.py
Revision de un microservicio A TRAVES DEL API GATEWAY para el semaforo y
para "Probar conexion". Nunca lanza: siempre devuelve un dict con el resultado.

El gateway solo publica las rutas de negocio (/login, /books, ...), no el
/health interno de cada servicio. Por eso se consulta una ruta GET ligera de
cada servicio (RUTAS_SONDEO) por el gateway:

  Verde (ok=True) -> el gateway respondio y el servicio contesto: cualquier
                     status 2xx-4xx salvo 404 (p. ej. 401 sin token = el
                     servicio esta vivo y validando).
  Rojo            -> sin respuesta, timeout, 404 (ruta no publicada en el
                     gateway) o 5xx (502/503/504 = el gateway no alcanza al
                     servicio).
Si la respuesta trae "db"/"redis" (como /health) tambien se muestran.
"""
import time
from datetime import datetime

import requests

# El semaforo sondea el gateway cada pocos segundos en 6 servicios; registrar esas
# llamadas llenaria la consola. Poner en True para verlas tambien.
LOG_HEALTH_CHECKS = False


# Ruta GET publicada en el gateway para sondear cada servicio.
RUTAS_SONDEO = {
    "login": "/session",
    "books": "/formats",
    "users": "/roles",
    "authors": "/authors",
    "pedidos": "/pedidos",
    "pagos": "/pagos",
}


def revisar(config, servicio, timeout):
    url = f"{config.base_url(servicio)}{RUTAS_SONDEO[servicio]}"
    resultado = {"servicio": servicio, "url": url, "ok": False, "status": None, "db": None, "redis": None,
                 "ms": None, "hora": datetime.now(), "error": None}
    inicio = time.perf_counter()
    try:
        resp = requests.get(url, timeout=timeout, verify=config.verify(), headers={"Accept": "application/json"})
    except requests.exceptions.SSLError:
        resultado["error"] = "certificado HTTPS no válido"
    except requests.exceptions.Timeout:
        resultado["error"] = f"sin respuesta en {timeout} s"
    except requests.RequestException:
        resultado["error"] = "no se pudo conectar"
    else:
        resultado["status"] = resp.status_code
        try:
            datos = resp.json()
        except ValueError:
            datos = {}
        if isinstance(datos, dict):
            resultado["db"] = datos.get("db")
            resultado["redis"] = datos.get("redis")
        resultado["ok"] = 200 <= resp.status_code < 500 and resp.status_code != 404
    resultado["ms"] = round((time.perf_counter() - inicio) * 1000)
    resultado["hora"] = datetime.now()

    if LOG_HEALTH_CHECKS:
        print(f"[health] {servicio}: {'OK' if resultado['ok'] else 'FALLA'} "
              f"status={resultado['status']} {resultado['ms']} ms {resultado['error'] or ''}", flush=True)
    return resultado
