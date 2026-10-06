"""
api/health.py
Revision de GET /health de un microservicio para el semaforo y para
"Probar conexion". Nunca lanza: siempre devuelve un dict con el resultado.

Verde (ok=True) solo si /health responde 200 y su JSON trae status "ok".
"""
import time
from datetime import datetime

import requests

# El semaforo consulta /health cada pocos segundos en 6 servicios; registrar esas
# llamadas llenaria la consola. Poner en True para verlas tambien.
LOG_HEALTH_CHECKS = False


def revisar(config, servicio, timeout):
    url = f"{config.base_url(servicio)}/health"
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
            resultado["ok"] = resp.status_code == 200 and datos.get("status") == "ok"
    resultado["ms"] = round((time.perf_counter() - inicio) * 1000)
    resultado["hora"] = datetime.now()

    if LOG_HEALTH_CHECKS:
        print(f"[health] {servicio}: {'OK' if resultado['ok'] else 'FALLA'} "
              f"status={resultado['status']} {resultado['ms']} ms {resultado['error'] or ''}", flush=True)
    return resultado
