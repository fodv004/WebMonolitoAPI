"""
common
Modulo compartido por todos los microservicios (login, books, users,
authors, pedidos, pagos): configuracion, Redis, validacion del JWT,
/health, /metrics, formato de errores, logging y CORS.

Cada servicio agrega apps/services al sys.path al inicio de su app.py:

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

y despues importa `from common import ...`. Ver docs/ARQUITECTURA.md.
"""
