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


# --- microservicio authors (cache de 60 s; cualquier escritura invalida AUTHORS_PATTERN con SCAN)
AUTHORS_PATTERN = "authors:*"


def authors_list(filtros):
    return f"authors:list:{filtros}"


def author(author_id):
    return f"authors:{author_id}"


def author_books(author_id):
    return f"authors:{author_id}:books"


def authors_by_book(isbn):
    return f"authors:by-book:{isbn}"


# --- microservicio pedidos
LOCK_EXPIRAR_PEDIDOS = "lock:pedidos:expirar"     # SET NX EX LOCK_TTL antes de cada vuelta de la tarea


def pedido_reserva(pedido_id):
    """Espejo de la reserva de stock de un pedido PENDIENTE_PAGO (TTL = minutos de reserva)."""
    return f"pedido:reserva:{pedido_id}"


# --- microservicio pagos
LOCK_SYNC_PAGOS = "lock:pagos:sync"               # SET NX EX LOCK_TTL antes de cada vuelta de la sincronizacion


def pago_idem(idempotency_key):
    """Id del pago ya registrado con esa Idempotency-Key (TTL = PAYMENT_IDEMPOTENCY_TTL, 24 h)."""
    return f"pago:idem:{idempotency_key}"


def pago_lock(pedido_id):
    """Lock (SET NX EX LOCK_TTL) mientras se paga o se reembolsa un pedido."""
    return f"pago:lock:{pedido_id}"
