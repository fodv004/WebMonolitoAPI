def test_health_503_si_la_base_no_responde(client, monkeypatch):
    from db import connection

    def caida():
        raise RuntimeError("PostgreSQL caido (prueba)")

    monkeypatch.setattr(connection, "ping", caida)
    resp = client.get("/health")
    assert resp.status_code == 503 and resp.get_json()["db"] == "error"


def test_metrics(client):
    datos = client.get("/metrics").get_json()
    assert datos["service"] == "pagos"
    assert {"requests_total", "errors_4xx", "errors_5xx", "responses_401", "responses_403",
            "cache_hits", "cache_misses", "redis_errors"} <= set(datos)


def test_ruta_inexistente_404_con_formato_uniforme(client):
    resp = client.get("/no-existe")
    assert resp.status_code == 404 and set(resp.get_json()) == {"error", "message"}
