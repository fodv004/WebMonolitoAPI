# Redis en el proyecto Library

Redis es una **capa compartida** por los 6 microservicios. PostgreSQL sigue siendo la fuente principal de datos:
en Redis solo vive información temporal que se puede reconstruir o que caduca sola.

- Corre en la VM (`maquina-01`, CentOS Stream 10), puerto **6379**, **solo en 127.0.0.1**.
- Todos los servicios se conectan con la misma URL protegida con contraseña: `REDIS_URL`.
- Este documento **no contiene contraseñas reales**. La contraseña vive únicamente en la configuración de Redis de la VM y en los `.env` (que no se versionan).

> En CentOS Stream 10 el paquete es **Valkey** (el fork de Redis que distribuye Red Hat). Es compatible con el
> protocolo y con `redis-py`; solo cambian los nombres: servicio `valkey`, cliente `valkey-cli`, configuración
> `/etc/valkey/valkey.conf`. Si tu VM tiene Redis "clásico" son `redis`, `redis-cli` y `/etc/redis/redis.conf`.
> Los comandos de abajo detectan cuál tienes.

## 1. Verificar que Redis está activo

```bash
# ¿Cuál de los dos está instalado?
systemctl list-unit-files | grep -E '^(redis|valkey)\.service'

# Estado del servicio (usa el nombre que salió arriba)
sudo systemctl status valkey --no-pager     # o: sudo systemctl status redis --no-pager
sudo systemctl is-enabled valkey            # debe decir "enabled" (arranca con la VM)

# Variables para el resto de los comandos
if command -v valkey-cli >/dev/null; then CLI=valkey-cli; CONF=/etc/valkey/valkey.conf; SVC=valkey
else CLI=redis-cli; CONF=/etc/redis/redis.conf; SVC=redis; fi
echo "$CLI  $CONF  $SVC"
```

## 2. Verificar que responde PONG con la contraseña

La contraseña se pasa por la variable `REDISCLI_AUTH` para que no quede en el historial ni en la lista de procesos:

```bash
read -r -s -p "Contraseña de Redis: " REDISCLI_AUTH; export REDISCLI_AUTH; echo
$CLI -h 127.0.0.1 -p 6379 ping          # esperado: PONG

# Sin contraseña debe RECHAZAR (así se comprueba que requirepass está activo)
env -u REDISCLI_AUTH $CLI -h 127.0.0.1 -p 6379 ping     # esperado: NOAUTH Authentication required.
```

Si tu cliente no reconoce `REDISCLI_AUTH`: `$CLI -h 127.0.0.1 -a 'LA_CONTRASEÑA' --no-auth-warning ping`.

## 3. Revisar la configuración

Debe tener `bind 127.0.0.1`, `protected-mode yes` y `requirepass`:

```bash
sudo grep -E '^(bind|protected-mode|port)\b' "$CONF"
sudo grep -cE '^requirepass ' "$CONF"     # 1 = definido (no imprime la contraseña)

# Comprobación real: solo debe escuchar en 127.0.0.1 (y opcionalmente ::1)
sudo ss -ltnp | grep 6379
```

Esperado:

```
bind 127.0.0.1 -::1
protected-mode yes
port 6379
1
LISTEN 0 511 127.0.0.1:6379 ...
```

### Qué cambiar si falta algo

Edita el archivo (`sudo vi "$CONF"`) y deja estas líneas (sin `#` al inicio):

| Problema | Línea correcta |
|---|---|
| `bind 0.0.0.0` o `bind` comentado | `bind 127.0.0.1 -::1` |
| `protected-mode no` | `protected-mode yes` |
| `requirepass` comentado o ausente | `requirepass <contraseña larga y aleatoria>` |

Genera la contraseña con `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` (solo letras, números, `-` y `_`:
así no hay que codificarla en la URL). Después:

```bash
sudo systemctl restart "$SVC"
sudo systemctl status "$SVC" --no-pager
$CLI -h 127.0.0.1 ping      # con REDISCLI_AUTH exportada -> PONG
```

Nunca abras el puerto 6379 en `firewalld` ni en el firewall de GCP: ningún cliente externo debe llegar a Redis.

## 4. `REDIS_URL` en cada servicio

En el `.env.example` de los 6 servicios está la plantilla:

```
REDIS_URL=redis://:password@127.0.0.1:6379/0
```

En el `.env` real de **cada** servicio (login, books, users, authors, pedidos, pagos) sustituye `password` por la
contraseña de `requirepass`. Formato: `redis://:<contraseña>@<host>:<puerto>/<base>` (usuario vacío, base `0`).
Si la contraseña tuviera caracteres especiales (`@ : / ? #`) hay que codificarlos (`%40`, `%3A`...).

El cliente común (`apps/services/common/redis_client.py`) usa `socket_timeout` y `socket_connect_timeout` de **2 segundos**.

## 5. Qué se guarda en Redis

| Clave | Contenido | TTL | Quién la escribe |
|---|---|---|---|
| `session:<session_id>` | JSON de la sesión (`user_id`, `email`, `role_id`, `jti` vigente, `exp`, `refresh_hash`) | 7 días | login |
| `refresh:<sha256 del refresh token>` | `{session_id, user_id}` (el token nunca se guarda en claro) | 7 días | login |
| `user:sessions:<user_id>` | SET con los `session_id` del usuario | 7 días | login |
| `jwt:revoked:<jti>` | `"1"`: el JWT fue revocado (logout) | vida restante del JWT (≤ 20 min) | login |
| `books:list:<filtros>` | Catálogo cacheado (`books:list:format=json`, `books:list:format=xml`) | 60 s | books |
| `books:<isbn>` | Detalle cacheado de un libro | 60 s | books |
| `authors:list:<filtros>`, `authors:<id>`, `authors:<id>:books`, `authors:by-book:<isbn>` | Caché del servicio de autores | 60 s | authors |
| `pedido:reserva:<pedido_id>` | Espejo de la reserva de stock de un pedido sin pagar | 15 min (`RESERVA_MINUTOS`) | pedidos |
| `lock:pedidos:expirar` | Lock (`SET NX EX`) de la tarea que expira pedidos | 30 s | pedidos |
| `pago:idem:<idempotency_key>` | Id del pago ya registrado con esa llave (evita cobrar dos veces) | 24 h | pagos |
| `pago:lock:<pedido_id>` | Lock (`SET NX EX`) mientras se paga o reembolsa un pedido | 30 s | pagos |
| `lock:pagos:sync` | Lock (`SET NX EX`) de la tarea que sincroniza pagos con pedidos | 30 s | pagos |

Los nombres y TTL están centralizados en `apps/services/common/redis_keys.py`.

## 6. Qué pasa si Redis se cae

| Operación | Comportamiento |
|---|---|
| Lecturas cacheadas (`GET /books`, `GET /books/<isbn>`) | **Redis es opcional**: se registra el error, se cuenta en `/metrics` (`redis_errors`) y se responde desde PostgreSQL |
| `POST /login`, `/refresh`, `/logout` | **503** `REDIS_NO_DISPONIBLE` (no se puede crear ni revocar la sesión) |
| Cualquier ruta protegida con JWT | **503**: no se puede comprobar si el token fue revocado, así que no se acepta (fallo seguro) |
| `GET /health` de cualquier servicio | **503** con `"redis": "error"` → semáforo rojo en la app Tk |

## 7. Comandos útiles de diagnóstico

Siempre con `--scan` (iterativo); **nunca `KEYS`**, que bloquea el servidor:

```bash
$CLI -h 127.0.0.1 --scan --pattern 'session:*' | head
$CLI -h 127.0.0.1 --scan --pattern 'jwt:revoked:*'
$CLI -h 127.0.0.1 --scan --pattern 'books:*'
$CLI -h 127.0.0.1 ttl books:list:format=json      # segundos restantes (<= 60)
$CLI -h 127.0.0.1 dbsize
$CLI -h 127.0.0.1 info memory | grep used_memory_human
```
