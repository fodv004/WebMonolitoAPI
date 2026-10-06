"""
common/redis_keys.py
Nombres de las claves de Redis y sus TTL (segundos). Unica fuente de
verdad: ningun servicio escribe una clave "a mano".
"""
SESSION_TTL = 7 * 24 * 3600          # session:<session_id> y refresh:<token_hash>
CACHE_TTL = 60                       # cache del catalogo
STOCK_RESERVATION_TTL = 15 * 60      # reserva de stock (pedidos)
PAYMENT_IDEMPOTENCY_TTL = 24 * 3600  # idempotencia de pagos
LOCK_TTL = 30                        # locks


def session(session_id):
    return f"session:{session_id}"


def refresh(token_hash):
    return f"refresh:{token_hash}"


def user_sessions(user_id):
    return f"user:sessions:{user_id}"


def jwt_revoked(jti):
    """TTL = vida restante del JWT."""
    return f"jwt:revoked:{jti}"


def books_list(filtros):
    return f"books:list:{filtros}"


BOOKS_LIST_PATTERN = "books:list:*"


def book(isbn):
    return f"books:{isbn}"
