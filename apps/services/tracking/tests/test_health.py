"""/health y /metrics del modulo comun, y formato uniforme de errores."""


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"service": "tracking", "status": "ok", "db": "ok", "redis": "ok", "version": "2.0.0"}


def test_health_503_si_la_base_no_responde(client, monkeypatch):
    from db import connection

    def caida():
        raise RuntimeError("PostgreSQL caido (prueba)")

    monkeypatch.setattr(connection, "ping", caida)
    resp = client.get("/health")
    assert resp.status_code == 503 and resp.get_json()["db"] == "error"


def test_metrics(client):
    datos = client.get("/metrics").get_json()
    assert datos["service"] == "tracking" and "requests_total" in datos


def test_ruta_inexistente_404_con_formato_uniforme(client):
    resp = client.get("/no-existe")
    assert resp.status_code == 404 and set(resp.get_json()) == {"error", "message"}
