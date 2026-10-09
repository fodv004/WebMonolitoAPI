# VMComandos — Parte 1 (ambiente base)

Comandos para ejecutar **en la VM** (`maquina-01`, CentOS Stream 10) y dejar funcionando el ambiente base.
Córrelos en orden y pega la salida debajo de cada bloque **Resultado** para compartírmela.

> No pegues contraseñas ni tokens: en los comandos que podrían mostrarlos ya van ocultos.
> Sección 8 = lista de comprobación de la Parte 1. Sección 9 = problemas frecuentes.

## 0. Ubicación del repositorio y código nuevo

```bash
cd ~/WebMonolitoAPI            # ajusta a la ruta real del repo en la VM
export REPO="$(pwd)"
git pull
git log --oneline -3
python3 --version              # se espera 3.12
ls apps/services               # common login library_soap_service users authors pedidos pagos
```

**Resultado:**

```
```

## 1. Redis (ya instalado: solo verificar)

Detalle y qué cambiar si algo falta: `docs/REDIS.md`.

```bash
if command -v valkey-cli >/dev/null; then CLI=valkey-cli; CONF=/etc/valkey/valkey.conf; SVC=valkey
else CLI=redis-cli; CONF=/etc/redis/redis.conf; SVC=redis; fi
echo "$CLI  $CONF  $SVC"

sudo systemctl status "$SVC" --no-pager | head -5
sudo systemctl is-enabled "$SVC"

read -r -s -p "Contraseña de Redis: " REDISCLI_AUTH; export REDISCLI_AUTH; echo
$CLI -h 127.0.0.1 -p 6379 ping                          # esperado: PONG
env -u REDISCLI_AUTH $CLI -h 127.0.0.1 -p 6379 ping     # esperado: NOAUTH Authentication required.

sudo grep -E '^(bind|protected-mode|port)\b' "$CONF"    # bind 127.0.0.1 ... / protected-mode yes / port 6379
sudo grep -cE '^requirepass ' "$CONF"                   # 1
sudo ss -ltnp | grep 6379                               # solo 127.0.0.1:6379 (y opcionalmente [::1])
```

**Resultado:**

```
```

## 2. Datos de PostgreSQL

Los `.env.example` nuevos usan la base `library_db`; en instalaciones anteriores del proyecto se llama `library`.
Confirma el nombre real y úsalo en el paso 3.

```bash
psql -h localhost -U library_user -l | grep -i librar
grep -E '^DB_(NAME|USER|HOST|PORT)=' apps/services/login/.env apps/services/library_soap_service/.env
```

**Resultado:**

```
```

## 3. Archivos `.env` de los 6 servicios

`JWT_SECRET_KEY` e `INTERNAL_API_KEY` deben ser **idénticos en los 6**. Este bloque crea los `.env` que falten y
escribe los valores sin mostrarlos en pantalla. Ajusta `DB_NAME` si en el paso 2 salió otro nombre.

```bash
cd "$REPO"
DB_NAME=library_db                     # <- nombre real de la base (paso 2)

# poner ARCHIVO VARIABLE VALOR  (reemplaza la línea si existe; si no, la agrega)
poner() { if grep -q "^$2=" "$1"; then sed -i "s|^$2=.*|$2=$3|" "$1"; else printf '%s=%s\n' "$2" "$3" >> "$1"; fi; }

read -r -s -p "Contraseña de Redis: " REDIS_PASS; echo
read -r -s -p "Contraseña de library_user (PostgreSQL): " DB_PASS; echo

# Reutiliza el secreto JWT que ya usaban login y books (JWT_SECRET) para no invalidar nada; si no hay, genera uno.
JWT="$(grep -hE '^JWT_SECRET(_KEY)?=.+' apps/services/login/.env 2>/dev/null | tail -1 | cut -d= -f2-)"
[ -z "$JWT" ] && JWT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
INTERNA="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

for dir in login library_soap_service users authors pedidos pagos; do
    env="apps/services/$dir/.env"
    [ -f "$env" ] || cp "apps/services/$dir/.env.example" "$env"
    chmod 600 "$env"
    poner "$env" JWT_SECRET_KEY "$JWT"
    poner "$env" JWT_ALGORITHM HS256
    poner "$env" INTERNAL_API_KEY "$INTERNA"
    poner "$env" REDIS_URL "redis://:$REDIS_PASS@127.0.0.1:6379/0"
    grep -q '^CORS_ALLOWED_ORIGINS=' "$env" || echo 'CORS_ALLOWED_ORIGINS=' >> "$env"
done
for dir in users authors pedidos pagos; do
    poner "apps/services/$dir/.env" DATABASE_URL "postgresql://library_user:$DB_PASS@localhost:5432/$DB_NAME"
done
unset REDIS_PASS DB_PASS JWT INTERNA
```

Si alguna contraseña tiene `|`, `&`, `@`, `:` o `/`, edita ese `.env` a mano (en las URL van codificados: `@` → `%40`...).

Usuario administrador inicial (se crea o actualiza con `role_id = 1` en el paso 5):

```bash
read -r -p "Correo del admin: " ADMIN_EMAIL
read -r -s -p "Contraseña del admin (mínimo 8 caracteres): " ADMIN_PASS; echo
poner apps/services/users/.env ADMIN_EMAIL "$ADMIN_EMAIL"
poner apps/services/users/.env ADMIN_PASSWORD "$ADMIN_PASS"
unset ADMIN_PASS
```

Comprobación (solo nombres de variables, nunca valores):

```bash
for dir in login library_soap_service users authors pedidos pagos; do
    printf '%-22s ' "$dir"; grep -oE '^(JWT_SECRET_KEY|REDIS_URL|INTERNAL_API_KEY|DATABASE_URL|DB_NAME|ADMIN_EMAIL)=.' \
        "apps/services/$dir/.env" | cut -d= -f1 | tr '\n' ' '; echo
done
# Mismo secreto en los 6 (cuenta valores distintos sin mostrarlos): esperado 1
cat apps/services/*/.env | grep '^JWT_SECRET_KEY=' | sort -u | wc -l
```

**Resultado:**

```
```

## 4. Liberar los puertos 5000–5005

Si login o books estaban corriendo a mano (`python app.py`, `nohup`...), deténlos: ahora los maneja systemd.

```bash
sudo ss -ltnp | grep -E ':500[0-5]\b' || echo "puertos libres"
# Si aparece algún proceso que NO sea gunicorn de systemd:
#   kill <PID>
```

**Resultado:**

```
```

## 5. Levantar los 6 servicios

Instala dependencias (un `.venv` por servicio), ejecuta la migración `users/sql/001_roles.sql`, crea el admin
inicial e instala, activa y reinicia las 6 unidades systemd. Pide `sudo` solo para systemd.

```bash
cd "$REPO"
bash scripts/levantar_servicios.sh
```

Si se detiene diciendo que falta completar algún `.env`, corrígelo y vuelve a ejecutarlo (es idempotente).

**Resultado:**

```
```

Verificación de la migración:

```bash
DB_URL="$(grep '^DATABASE_URL=' apps/services/users/.env | cut -d= -f2-)"
psql "$DB_URL" -c "SELECT * FROM roles ORDER BY role_id;"
psql "$DB_URL" -c "SELECT role_id, COUNT(*) FROM usuarios GROUP BY role_id ORDER BY 1;"
psql "$DB_URL" -c "SELECT version, aplicada_en FROM schema_migraciones ORDER BY aplicada_en;"
psql "$DB_URL" -c "SELECT id_usuario, correo, es_admin, role_id, activo, estado_cuenta FROM usuarios WHERE role_id = 1;"
```

**Resultado:**

```
```

## 6. Firewall (para que la app Tk llegue desde tu máquina)

login (5000) y books (5001) ya estaban abiertos; faltan 5002–5005. **Nunca abras 6379.**

```bash
sudo firewall-cmd --state && sudo firewall-cmd --permanent --add-port=5000-5005/tcp && sudo firewall-cmd --reload
sudo firewall-cmd --list-ports
```

En GCP (desde tu máquina local con `gcloud`, o en la consola: *VPC network → Firewall*). Limita el origen a tu IP:

```bash
gcloud compute firewall-rules create library-microservicios \
    --allow tcp:5000-5005 --source-ranges <TU_IP_PUBLICA>/32 --description "Microservicios Library"
# Si la regla ya existe: gcloud compute firewall-rules update library-microservicios --allow tcp:5000-5005
```

**Resultado:**

```
```

## 7. (Opcional) HTTPS con nginx

La app Tk usa **HTTP por defecto**. Si en Configuración eliges HTTPS, llama a `https://<IP>/api/<servicio>/...`,
así que la VM necesita un proxy inverso que quite el prefijo. Con certificado autofirmado:

```bash
sudo dnf install -y nginx
IP_PUBLICA=<IP_PUBLICA_DE_LA_VM>
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout /etc/nginx/ssl/library.key -out /etc/nginx/ssl/library.crt \
    -subj "/CN=$IP_PUBLICA" -addext "subjectAltName=IP:$IP_PUBLICA"
sudo chmod 600 /etc/nginx/ssl/library.key

sudo tee /etc/nginx/conf.d/library_api.conf > /dev/null <<'EOF'
server {
    listen 443 ssl;
    server_name _;
    ssl_certificate     /etc/nginx/ssl/library.crt;
    ssl_certificate_key /etc/nginx/ssl/library.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    # /api/<servicio>/ruta  ->  http://127.0.0.1:<puerto>/ruta
    location /api/login/   { proxy_pass http://127.0.0.1:5000/; }
    location /api/books/   { proxy_pass http://127.0.0.1:5001/; }
    location /api/users/   { proxy_pass http://127.0.0.1:5002/; }
    location /api/authors/ { proxy_pass http://127.0.0.1:5003/; }
    location /api/pedidos/ { proxy_pass http://127.0.0.1:5004/; }
    location /api/pagos/   { proxy_pass http://127.0.0.1:5005/; }

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
}
EOF
sudo nginx -t
sudo setsebool -P httpd_can_network_connect 1      # SELinux: permite a nginx conectar con los puertos 500x
sudo systemctl enable --now nginx && sudo systemctl reload nginx
sudo firewall-cmd --permanent --add-service=https && sudo firewall-cmd --reload
curl -sk https://127.0.0.1/api/users/health
```

Copia `/etc/nginx/ssl/library.crt` (solo el `.crt`, nunca la `.key`) a tu máquina y selecciónalo en
*Configuración → Certificado (.crt)* con "Verificar certificado" activado. Abre también el 443 en el firewall de GCP.

**Resultado:**

```
```

---

## 8. Comprobación de la Parte 1

### 8.1 Redis responde PONG con contraseña

```bash
if command -v valkey-cli >/dev/null; then CLI=valkey-cli; else CLI=redis-cli; fi
read -r -s -p "Contraseña de Redis: " REDISCLI_AUTH; export REDISCLI_AUTH; echo
$CLI -h 127.0.0.1 ping
```

**Resultado (esperado `PONG`):**

```
```

### 8.2 Los 6 servicios activos y cada `/health` devuelve 200

```bash
cd "$REPO"
bash scripts/estado_servicios.sh
systemctl is-active login books users authors pedidos pagos
```

**Resultado (esperado: 6 × `health : 200 OK` y 6 × `active`):**

```
```

### 8.3 Login → JWT con `user_id` y `role_id`; `/refresh` lo renueva; tras `/logout` el token anterior da 401 en books

```bash
read -r -p "Correo del admin: " EMAIL
read -r -s -p "Contraseña: " PASS; echo
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)"; }
claims() { python3 -c "import sys,base64,json; p=sys.argv[1].split('.')[1]; print(json.dumps(json.loads(base64.urlsafe_b64decode(p+'='*(-len(p)%4))), indent=1))" "$1"; }

# 1) login
R="$(curl -s -X POST 'http://127.0.0.1:5000/login?format=json' -H 'Content-Type: application/json' \
      -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")"
TOKEN="$(echo "$R" | json '["data"]["token"]')"; REFRESH="$(echo "$R" | json '["data"]["refresh_token"]')"
echo "$R" | json '["code"]'; echo "expires_in: $(echo "$R" | json '["data"]["expires_in"]')"
claims "$TOKEN"                   # sub, user_id, role_id, role, jti, iat, exp, type=access  (exp - iat = 1200)

# 2) el token sirve para escribir en books (PATCH vacío: no cambia nada)
ISBN="$(curl -s 'http://127.0.0.1:5001/books?format=json' | json '[0]["isbn"]')"
curl -s -o /dev/null -w 'PATCH con token vigente -> %{http_code}\n' -X PATCH "http://127.0.0.1:5001/books/$ISBN?format=json" \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'

# 3) refresh: token nuevo y refresh token rotado (el viejo ya no sirve)
R2="$(curl -s -X POST 'http://127.0.0.1:5000/refresh?format=json' -H 'Content-Type: application/json' \
       -d "{\"refresh_token\":\"$REFRESH\"}")"
TOKEN2="$(echo "$R2" | json '["data"]["token"]')"; REFRESH2="$(echo "$R2" | json '["data"]["refresh_token"]')"
echo "$R2" | json '["code"]'
[ "$TOKEN" != "$TOKEN2" ] && [ "$REFRESH" != "$REFRESH2" ] && echo "token y refresh token cambiaron"
curl -s -o /dev/null -w 'refresh con el refresh token VIEJO -> %{http_code}\n' -X POST 'http://127.0.0.1:5000/refresh?format=json' \
     -H 'Content-Type: application/json' -d "{\"refresh_token\":\"$REFRESH\"}"

# 4) logout y el token anterior ya no sirve en books
curl -s -X POST 'http://127.0.0.1:5000/logout?format=json' -H "Authorization: Bearer $TOKEN2" | json '["code"]'
curl -s -w '\nPATCH con el token anterior -> %{http_code}\n' -X PATCH "http://127.0.0.1:5001/books/$ISBN?format=json" \
     -H "Authorization: Bearer $TOKEN2" -H 'Content-Type: application/json' -d '{}'
$CLI -h 127.0.0.1 --scan --pattern 'jwt:revoked:*'
unset PASS TOKEN TOKEN2 REFRESH REFRESH2 R R2
```

**Resultado (esperado: `LOGIN_EXITOSO`, claims con `user_id` y `role_id`, `200`, `TOKEN_RENOVADO`, `401`, `LOGOUT_EXITOSO`, `{"error":"TOKEN_REVOCADO",...}` y `401`):**

```
```

### 8.4 Books cachea (cache hit en `/metrics`) y las escrituras sin token dan 401

En la misma terminal de 8.1 y 8.3 (usa `$CLI` e `$ISBN`).

```bash
curl -s -o /dev/null -w 'GET /books (1) -> %{http_code} en %{time_total}s\n' 'http://127.0.0.1:5001/books?format=json'
curl -s -o /dev/null -w 'GET /books (2) -> %{http_code} en %{time_total}s\n' 'http://127.0.0.1:5001/books?format=json'
curl -s -o /dev/null 'http://127.0.0.1:5001/books/'"$ISBN"'?format=json'
curl -s -o /dev/null 'http://127.0.0.1:5001/books/'"$ISBN"'?format=json'
curl -s http://127.0.0.1:5001/metrics; echo                 # cache_hits >= 2
$CLI -h 127.0.0.1 --scan --pattern 'books:*'                # books:list:format=json y books:<isbn>
$CLI -h 127.0.0.1 ttl 'books:list:format=json'              # <= 60

for metodo in POST PUT PATCH DELETE; do
    ruta="/books/$ISBN"; [ "$metodo" = POST ] && ruta="/books"
    curl -s -o /dev/null -w "$metodo $ruta sin token -> %{http_code}\n" -X "$metodo" "http://127.0.0.1:5001$ruta" \
         -H 'Content-Type: application/json' -d '{}'
done
```

**Resultado (esperado: `cache_hits` ≥ 2, las claves `books:*` y cuatro `401`):**

```
```

### 8.5 App Tk: 6 semáforos en verde; al detener un servicio el suyo cambia a rojo

En tu máquina local: `cd apps/Python_app && pip install -r requirements.txt && python main.py`,
*Configuración* → IP de la VM → *Guardar*. Deben verse los 6 semáforos en verde. Después, en la VM:

```bash
sudo systemctl stop pagos          # en <= 10 s (o con "Revisar ahora") el semáforo de Pagos pasa a rojo
sleep 15
sudo systemctl start pagos         # vuelve a verde
```

Para ver un 503 real con Redis caído (todos los semáforos en rojo y login respondiendo 503):

```bash
sudo systemctl stop valkey         # o redis
curl -s -o /dev/null -w 'health login -> %{http_code}\n' http://127.0.0.1:5000/health
curl -s -o /dev/null -w 'GET /books (sin Redis, desde PostgreSQL) -> %{http_code}\n' 'http://127.0.0.1:5001/books?format=json'
sudo systemctl start valkey
```

**Resultado (qué viste en la app + salida de los comandos):**

```
```

### 8.6 Pytest completo

En la VM (cada servicio usa su `.venv`; instala `requirements-dev.txt` si falta):

```bash
cd "$REPO"
bash scripts/run_tests.sh
```

En tu máquina local (Windows), solo la app Tk:

```
cd apps\Python_app
pip install -r requirements.txt pytest
python -m pytest -q tests
```

**Resultado (esperado: `Todas las suites pasaron.`):**

```
```

---

## 9. Si algo falla

| Síntoma | Qué revisar |
|---|---|
| Un servicio no queda `active` | `sudo journalctl -u <servicio> -n 50 --no-pager` (muestra el error exacto de arranque) |
| `ERROR: la variable de entorno JWT_SECRET_KEY no esta definida` | Falta en el `.env` de ese servicio (paso 3) |
| `status=203/EXEC` o `Permission denied` al iniciar gunicorn | **SELinux** bloquea ejecutar binarios dentro de `/home`. Ver abajo |
| `/health` responde 503 con `"redis": "error"` | `REDIS_URL` de ese `.env` (contraseña) y `systemctl status valkey` |
| `/health` responde 503 con `"db": "error"` | `DATABASE_URL` / `DB_*` de ese `.env`; prueba `psql "$DATABASE_URL" -c 'select 1'` |
| Login responde 500 y en `journalctl -u login` aparece `column "role_id" does not exist` | No corrió la migración: `psql "$DB_URL" -v ON_ERROR_STOP=1 -f apps/services/users/sql/001_roles.sql` |
| La migración falla con `must be owner of table usuarios` | Córrela con el dueño: `MIGRATION_DATABASE_URL=postgresql://library_user:...@localhost:5432/<base> bash scripts/levantar_servicios.sh` |
| Books responde 401 `TOKEN_INVALIDO` con un token recién emitido | `JWT_SECRET_KEY` distinto entre login y books (comprobación del paso 3) |
| Books responde 403 `ROL_INSUFICIENTE` | El usuario no es admin (`role_id = 1`): las escrituras del catálogo son solo para admin |
| Desde tu máquina no responde pero en la VM sí | Firewall (paso 6): `firewalld` y regla de GCP |

SELinux (solo si aparece `203/EXEC`):

```bash
getenforce
sudo ausearch -m avc -ts recent | tail -5
# Etiqueta los ejecutables de los .venv como binarios y reinicia:
sudo chcon -R -t bin_t "$REPO"/apps/services/*/.venv/bin
sudo systemctl restart login books users authors pedidos pagos
```

Comandos del día a día:

```bash
bash scripts/estado_servicios.sh -v                      # status completo + /health
sudo systemctl restart users                             # reiniciar uno
sudo journalctl -u login -f                              # ver su log en vivo (sin tokens ni contraseñas)
curl -s http://127.0.0.1:5000/metrics                    # métricas de un servicio
```


---
---

# PARTE 2 — Microservicio users

Requisito: la Parte 1 funcionando (los 6 servicios en verde). Corre los bloques en orden y pega la salida en cada
**Resultado**.

## 10. Desplegar la Parte 2

### 10.1 Código nuevo y esquema actual de `usuarios`

```bash
cd ~/WebMonolitoAPI && export REPO="$(pwd)"       # ajusta la ruta
git pull && git log --oneline -3
DB_URL="$(grep '^DATABASE_URL=' apps/services/users/.env | cut -d= -f2-)"
psql "$DB_URL" -c '\d usuarios'                                   # columnas ANTES de la migración 002
psql "$DB_URL" -c '\di un_solo_admin'                             # ¿existe la regla "un solo administrador"?
psql "$DB_URL" -c "SELECT id_usuario, correo, es_admin, role_id, activo, estado_cuenta, left(password_hash, 4) AS hash FROM usuarios WHERE es_admin OR role_id = 1 OR correo IN ('admin@libreria.com', 'maruchanvalo@gmail.com') ORDER BY 1;"
```

**Resultado:**

```
```

### 10.2 Variables del administrador en el `.env` de users

```bash
poner() { if grep -q "^$2=" "$1"; then sed -i "s|^$2=.*|$2=$3|" "$1"; else printf '%s=%s\n' "$2" "$3" >> "$1"; fi; }
poner apps/services/users/.env ADMIN_EMAIL admin@libreria.com
read -r -s -p "Contraseña para admin@libreria.com (mínimo 8 caracteres): " ADMIN_PASS; echo
poner apps/services/users/.env ADMIN_PASSWORD "$ADMIN_PASS"; unset ADMIN_PASS
grep -q '^LOGIN_URL=' apps/services/users/.env || echo 'LOGIN_URL=http://127.0.0.1:5000' >> apps/services/users/.env
grep -oE '^(ADMIN_EMAIL=.*|ADMIN_PASSWORD|LOGIN_URL=.*|INTERNAL_API_KEY)' apps/services/users/.env   # sin mostrar secretos
```

`ADMIN_PASSWORD` solo se usa si el `password_hash` del admin sigue siendo el valor de ejemplo del monolito.
`INTERNAL_API_KEY` debe ser la misma en users y login (ya quedó así en la Parte 1).

**Resultado:**

```
```

### 10.3 Dependencias nuevas, migración `002_users.sql` y reinicio

```bash
cd "$REPO"
bash scripts/levantar_servicios.sh         # instala email-validator y dnspython en users, migra y reinicia los 6
psql "$DB_URL" -c '\d usuarios'            # ahora con updated_at y el trigger trg_usuarios_rol_y_fecha
psql "$DB_URL" -c "SELECT version, aplicada_en FROM schema_migraciones ORDER BY aplicada_en;"   # 003_roles y 004_users
psql "$DB_URL" -c "SELECT role_id, es_admin, COUNT(*) FROM usuarios GROUP BY 1, 2 ORDER BY 1;"  # 1|t y 2|f, nunca mezclados
```

**Resultado:**

```
```

### 10.4 Administrador inicial (una sola vez)

```bash
cd "$REPO/apps/services/users"
.venv/bin/python scripts/crear_admin.py
.venv/bin/python scripts/crear_admin.py     # segunda vez: debe decir "sin cambios" (es idempotente)
cd "$REPO"
```

Consulta de verificación (admin@libreria.com → `role_id = 1`; maruchanvalo@gmail.com → `role_id = 2`):

```bash
psql "$DB_URL" -c "SELECT id_usuario, correo, es_admin, role_id, activo, estado_cuenta, left(password_hash, 4) AS hash FROM usuarios WHERE correo IN ('admin@libreria.com', 'maruchanvalo@gmail.com') ORDER BY role_id;"
```

`hash` debe empezar con `$2b$` (bcrypt). Si el de maruchanvalo no empieza así, esa cuenta no puede iniciar sesión
hasta que el admin le restablezca la contraseña (11.5).

**Resultado:**

```
```

---

## 11. Comprobación de la Parte 2

Funciones de apoyo (misma terminal para todo el punto 11):

```bash
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)"; }
claims() { python3 -c "import sys,base64,json; p=sys.argv[1].split('.')[1]; print(json.dumps(json.loads(base64.urlsafe_b64decode(p+'='*(-len(p)%4))), indent=1))" "$1"; }
entrar() {   # entrar CORREO  -> deja el JWT en $TOKEN (pide la contraseña sin mostrarla)
    local pass r; read -r -s -p "Contraseña de $1: " pass; echo
    r="$(curl -s -X POST 'http://127.0.0.1:5000/login?format=json' -H 'Content-Type: application/json' \
          -d "{\"email\":\"$1\",\"password\":\"$pass\"}")"
    echo "$r" | json '["code"]'
    TOKEN="$(echo "$r" | json '["data"]["token"]' 2>/dev/null)"
}
U=http://127.0.0.1:5002
```

### 11.1 Login con admin@libreria.com → el JWT trae `role_id = 1`

```bash
entrar admin@libreria.com; ADMIN_TOKEN="$TOKEN"
claims "$ADMIN_TOKEN" | grep -E '"(user_id|role_id|role|type)"'
curl -s "$U/users/me" -H "Authorization: Bearer $ADMIN_TOKEN"; echo
curl -s "$U/roles" -H "Authorization: Bearer $ADMIN_TOKEN"; echo
curl -s "$U/users?per_page=3" -H "Authorization: Bearer $ADMIN_TOKEN" | json '["total"]'
```

**Resultado (esperado: `LOGIN_EXITOSO`, `"role_id": 1`, `"role": "admin"`):**

```
```

### 11.2 Login con maruchanvalo@gmail.com → `role_id = 2`; un cliente recibe 403 en `GET /users`

```bash
entrar maruchanvalo@gmail.com; CLIENTE_TOKEN="$TOKEN"
claims "$CLIENTE_TOKEN" | grep -E '"(user_id|role_id|role)"'
curl -s -w '\nGET /users como cliente -> %{http_code}\n' "$U/users" -H "Authorization: Bearer $CLIENTE_TOKEN"
curl -s -w '\nGET /users/me como cliente -> %{http_code}\n' "$U/users/me" -H "Authorization: Bearer $CLIENTE_TOKEN"
curl -s -o /dev/null -w 'GET /users sin token -> %{http_code}\n' "$U/users"
```

**Resultado (esperado: `"role_id": 2`, `{"error":"ROL_INSUFICIENTE",...}` con `403`, `200` y `401`):**

```
```

### 11.3 Crear un usuario como admin y hacer login con él

Usa un correo de un dominio real (se valida el registro MX), por ejemplo uno tuyo de Gmail con `+prueba`.

```bash
read -r -p "Correo del usuario nuevo: " NUEVO
read -r -s -p "Contraseña del usuario nuevo (mínimo 8): " NUEVO_PASS; echo
R="$(curl -s -X POST "$U/users" -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
      -d "{\"nombre\":\"Usuario\",\"apellido_paterno\":\"De Prueba\",\"email\":\"$NUEVO\",\"password\":\"$NUEVO_PASS\"}")"
echo "$R"; NUEVO_ID="$(echo "$R" | json '["id_usuario"]')"; unset NUEVO_PASS
curl -s -w '\nmismo correo otra vez -> %{http_code}\n' -X POST "$U/users" -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H 'Content-Type: application/json' -d "{\"nombre\":\"Otro\",\"email\":\"$NUEVO\",\"password\":\"OtraClave123\"}"

entrar "$NUEVO"; NUEVO_TOKEN="$TOKEN"            # la contraseña que acabas de ponerle
claims "$NUEVO_TOKEN" | grep -E '"(user_id|role_id)"'
```

**Resultado (esperado: usuario sin `password_hash`, `409 EMAIL_DUPLICADO`, `LOGIN_EXITOSO` y `"role_id": 2`):**

```
```

### 11.4 Después de cambiarle la contraseña a un usuario, su token anterior recibe 401

```bash
curl -s -o /dev/null -w 'antes: GET /users/me con su token -> %{http_code}\n' "$U/users/me" -H "Authorization: Bearer $NUEVO_TOKEN"
read -r -s -p "Contraseña nueva para $NUEVO: " P2; echo
curl -s -X PATCH "$U/users/$NUEVO_ID/password" -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
     -d "{\"password_nueva\":\"$P2\"}"; echo; unset P2
curl -s -w '\ndespués: GET /users/me con el token anterior -> %{http_code}\n' "$U/users/me" -H "Authorization: Bearer $NUEVO_TOKEN"
if command -v valkey-cli >/dev/null; then CLI=valkey-cli; else CLI=redis-cli; fi
read -r -s -p "Contraseña de Redis: " REDISCLI_AUTH; export REDISCLI_AUTH; echo
$CLI -h 127.0.0.1 --scan --pattern 'jwt:revoked:*'
$CLI -h 127.0.0.1 smembers "user:sessions:$NUEVO_ID"          # vacío: sus sesiones se cerraron
entrar "$NUEVO"                                               # con la contraseña NUEVA -> LOGIN_EXITOSO
```

**Resultado (esperado: `200`, mensaje de contraseña actualizada, `{"error":"TOKEN_REVOCADO",...}` con `401`, `LOGIN_EXITOSO`):**

```
```

### 11.5 Reglas: último admin, un solo admin, rol, baja lógica y endpoint interno

```bash
ADMIN_ID="$(curl -s "$U/users/me" -H "Authorization: Bearer $ADMIN_TOKEN" | json '["id_usuario"]')"
# El último admin no se desactiva ni pierde el rol -> 409 ULTIMO_ADMIN
curl -s -w ' -> %{http_code}\n' -X DELETE "$U/users/$ADMIN_ID" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -s -w ' -> %{http_code}\n' -X PATCH "$U/users/$ADMIN_ID/role" -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H 'Content-Type: application/json' -d '{"role_id":2}'
# Nombrar un segundo admin -> 409 UN_SOLO_ADMIN mientras exista el índice del monolito (200 si lo quitaste)
curl -s -w ' -> %{http_code}\n' -X PATCH "$U/users/$NUEVO_ID/role" -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H 'Content-Type: application/json' -d '{"role_id":1}'
# Un cliente no cambia su propio rol -> 403
curl -s -w ' -> %{http_code}\n' -X PATCH "$U/users/$NUEVO_ID" -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"role_id":1}'
# Baja lógica: el usuario sigue en la tabla con activo = false y ya no puede entrar
curl -s -w ' -> %{http_code}\n' -X DELETE "$U/users/$NUEVO_ID" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -s -o /dev/null -w 'su token tras la baja -> %{http_code}\n' "$U/users/me" -H "Authorization: Bearer $TOKEN"
psql "$DB_URL" -c "SELECT id_usuario, correo, activo, role_id, es_admin, updated_at FROM usuarios WHERE id_usuario = $NUEVO_ID;"
# Endpoint interno (para pedidos y pagos): sin clave 401, con clave 200
curl -s -o /dev/null -w 'interno sin clave -> %{http_code}\n' "$U/users/internal/$ADMIN_ID"
KEY="$(grep '^INTERNAL_API_KEY=' apps/services/users/.env | cut -d= -f2-)"
curl -s "$U/users/internal/$ADMIN_ID" -H "X-Internal-Key: $KEY"; echo; unset KEY
```

**Resultado (esperado: `409`, `409`, `409` (o `200`), `403`, `200`, `401`, fila con `activo = f`, `401` y los datos mínimos):**

```
```

### 11.6 (Opcional) Cambio de correo con confirmación

Requiere que el correo de login funcione (Mailpit o Gmail). Con una cuenta de prueba **activa**:

```bash
curl -s -w ' -> %{http_code}\n' -X PATCH "$U/users/<ID>/email" -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H 'Content-Type: application/json' -d '{"email":"<correo nuevo real>"}'
psql "$DB_URL" -c "SELECT correo, estado_cuenta FROM usuarios WHERE id_usuario = <ID>;"      # pendiente
sudo journalctl -u login -n 5 --no-pager | grep 'internal/confirmation'                     # POST ... 202
```

Al abrir el enlace del correo, `estado_cuenta` vuelve a `confirmado`.

**Resultado:**

```
```

### 11.7 App Tk

En tu máquina: `cd apps/Python_app && python main.py`.

1. **Admin:** inicia sesión con `admin@libreria.com`. La barra superior debe decir `(admin)`. Abre **Usuarios**:
   se ve *Administración de usuarios* con la tabla, los filtros y el panel de acciones a la derecha.
2. Escribe parte de un correo en *Buscar* y pulsa Enter; filtra por *Rol* y por *Estado*; usa *Anterior / Siguiente*.
3. **+ Nuevo usuario** → llena el formulario → *Crear*. Debe aparecer en la tabla y la barra inferior decir `201 Usuario creado`.
4. Selecciónalo y prueba **Editar datos**, **Restablecer contraseña**, **Cambiar rol** (pide confirmación; con el
   índice `un_solo_admin` debe explicar que solo se admite un administrador) y **Desactivar** (pide confirmación; el
   botón cambia a *Reactivar*).
5. Selecciona tu propia cuenta de admin y pulsa **Desactivar**: debe negarse (último administrador).
6. En la VM: `sudo systemctl stop users`. En ≤ 10 s el semáforo de Usuarios pasa a rojo y la pantalla se cubre con
   *Servicio de usuarios no disponible*. `sudo systemctl start users`: vuelve a verde y la pantalla se habilita sola.
7. **Cliente:** cierra sesión y entra con `maruchanvalo@gmail.com`. En **Usuarios** solo debe verse *Mi perfil*.
   Cambia el nombre y pulsa *Guardar mi nombre*; luego **Cambiar contraseña**: con la actual incorrecta muestra el
   error dentro del diálogo; con la correcta te regresa al login pidiéndote entrar con la nueva.

**Resultado (qué viste en cada paso):**

```
```

### 11.8 Pytest

```bash
cd "$REPO" && bash scripts/run_tests.sh
```

Opcional, migraciones y SQL contra PostgreSQL real en una base **desechable** (nunca `library_db`):

```bash
sudo -u postgres createdb -O library_user users_pruebas
cd "$REPO/apps/services/users"
TEST_DATABASE_URL="$(echo "$DB_URL" | sed 's|/[^/]*$|/users_pruebas|')" .venv/bin/python -m pytest -q tests/test_integracion_pg.py
sudo -u postgres dropdb users_pruebas; cd "$REPO"
```

**Resultado (esperado: `Todas las suites pasaron.`):**

```
```

## 12. Si algo falla en la Parte 2

| Síntoma | Qué revisar |
|---|---|
| `crear_admin.py`: `ya hay OTRO administrador y la base solo admite uno` | `ADMIN_EMAIL` no es la cuenta que hoy tiene `es_admin = TRUE` (ver consulta de 10.1). Corrige `ADMIN_EMAIL` |
| Login del admin responde 401 después de `crear_admin.py` | Su `password_hash` ya era un hash real (no se tocó): usa su contraseña anterior. Si no la recuerdas, pon temporalmente `UPDATE usuarios SET password_hash = 'hash_de_ejemplo' WHERE correo = 'admin@libreria.com';` y vuelve a correr el script |
| `PATCH .../role` responde `409 UN_SOLO_ADMIN` | Es la regla del monolito. Solo si decides permitir varios admins: `psql "$DB_URL" -f apps/services/users/sql/opcional_permitir_varios_admins.sql` |
| `POST /users` o `PATCH .../email` responde `400 ... sin registro MX` | El dominio del correo no existe o no recibe correo; usa uno real |
| `PATCH .../email` responde `503 CORREO_NO_ENVIADO` | login no pudo enviar el correo: `journalctl -u login -n 30`, SMTP/Mailpit, y que `INTERNAL_API_KEY` sea igual en users y login |
| users no arranca: `ModuleNotFoundError: email_validator` | Faltó reinstalar dependencias: `bash scripts/levantar_servicios.sh` |
| `500` con `column "updated_at" does not exist` en `journalctl -u users` | No corrió `002_users.sql`: `psql "$DB_URL" -v ON_ERROR_STOP=1 -f apps/services/users/sql/002_users.sql` |


---
---

# PARTE 3 — Microservicio authors

Requisito: Partes 1 y 2 funcionando. Corre los bloques en orden y pega la salida en cada **Resultado**.

## 13. Desplegar la Parte 3

```bash
cd ~/WebMonolitoAPI && export REPO="$(pwd)"       # ajusta la ruta
git pull && git log --oneline -3
DB_URL="$(grep '^DATABASE_URL=' apps/services/authors/.env | cut -d= -f2-)"

# Lo que hay hoy en las tablas del monolito (se copiará una sola vez a las tablas nuevas)
psql "$DB_URL" -c "SELECT COUNT(*) AS autores FROM autores;" -c "SELECT COUNT(*) AS relaciones FROM libro_autor;"

# authors valida los ISBN contra books: confirma que BOOKS_URL apunta al servicio local
grep -q '^BOOKS_URL=' apps/services/authors/.env || echo 'BOOKS_URL=http://127.0.0.1:5001' >> apps/services/authors/.env
grep '^BOOKS_URL=' apps/services/authors/.env

bash scripts/levantar_servicios.sh                # corre sql/001_authors.sql y reinicia los 6 servicios

psql "$DB_URL" -c '\d authors' -c '\d author_books'
psql "$DB_URL" -c "SELECT COUNT(*) AS authors FROM authors;" -c "SELECT COUNT(*) AS author_books FROM author_books;"
psql "$DB_URL" -c "SELECT id, nombre, apellido, nacionalidad FROM authors ORDER BY id LIMIT 5;"
psql "$DB_URL" -c "SELECT version, aplicada_en FROM schema_migraciones ORDER BY aplicada_en;"     # incluye 005_authors
```

Esperado: `authors` y `author_books` con los mismos conteos que `autores` y `libro_autor`; `author_books` con
PK `(author_id, isbn)` y una sola llave foránea (a `authors`, ninguna a `libros`).

**Resultado:**

```
```

---

## 14. Comprobación de la Parte 3

Funciones de apoyo (misma terminal para todo el punto 14):

```bash
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)"; }
A=http://127.0.0.1:5003; B=http://127.0.0.1:5001
read -r -s -p "Contraseña de admin@libreria.com: " P; echo
ADMIN_TOKEN="$(curl -s -X POST 'http://127.0.0.1:5000/login?format=json' -H 'Content-Type: application/json' \
      -d "{\"email\":\"admin@libreria.com\",\"password\":\"$P\"}" | json '["data"]["token"]')"; unset P
AUTH=(-H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json')
ISBN="$(curl -s "$B/books?format=json" | json '[0]["isbn"]')"; echo "ISBN de prueba: $ISBN"
```

### 14.1 Lecturas públicas y carga inicial

```bash
curl -s "$A/authors?per_page=3"; echo
curl -s "$A/authors/by-book/$ISBN"; echo
```

**Resultado (esperado: autores copiados del monolito, sin enviar token):**

```
```

### 14.2 Crear un autor y relacionarlo con un libro existente

```bash
R="$(curl -s -X POST "$A/authors" "${AUTH[@]}" \
      -d '{"nombre":"Autor","apellido":"De Prueba","nacionalidad":"Mexicana","fecha_nacimiento":"1980-01-15"}')"
echo "$R"; AID="$(echo "$R" | json '["id"]')"
curl -s -w ' -> %{http_code}\n' -X POST "$A/authors/$AID/books" "${AUTH[@]}" -d "{\"isbn\":\"$ISBN\"}"
curl -s "$A/authors/$AID/books"; echo                       # con "titulo" (viene de books) y "enriquecido": true
curl -s "$A/authors/by-book/$ISBN" | json '["authors"]' | tr ',' '\n' | grep nombre_completo
```

**Resultado (esperado: `201` con `titulo`, y el autor nuevo entre los autores del libro):**

```
```

### 14.3 Cache hit en `/metrics` en la segunda consulta

```bash
antes="$(curl -s "$A/metrics" | json '["cache_hits"]')"
curl -s -o /dev/null -w 'consulta 1 -> %{time_total}s\n' "$A/authors?q=prueba"
curl -s -o /dev/null -w 'consulta 2 -> %{time_total}s\n' "$A/authors?q=prueba"
echo "cache_hits: $antes -> $(curl -s "$A/metrics" | json '["cache_hits"]')"        # debe subir en 1
if command -v valkey-cli >/dev/null; then CLI=valkey-cli; else CLI=redis-cli; fi
read -r -s -p "Contraseña de Redis: " REDISCLI_AUTH; export REDISCLI_AUTH; echo
$CLI -h 127.0.0.1 --scan --pattern 'authors:*'
$CLI -h 127.0.0.1 ttl 'authors:list:q=prueba&page=1&per_page=20'                    # <= 60

# Una escritura invalida toda la caché del servicio
curl -s -o /dev/null -w 'PATCH -> %{http_code}\n' -X PATCH "$A/authors/$AID" "${AUTH[@]}" -d '{"biografia":"Cuenta de prueba"}'
echo "claves authors:* tras escribir: $($CLI -h 127.0.0.1 --scan --pattern 'authors:*' | wc -l)"   # 0
```

**Resultado:**

```
```

### 14.4 ISBN inexistente, books caído y permisos

```bash
# ISBN que no existe en books -> 404 LIBRO_NO_ENCONTRADO
curl -s -w ' -> %{http_code}\n' -X POST "$A/authors/$AID/books" "${AUTH[@]}" -d '{"isbn":"9789999999999"}'
# Relación repetida -> 409 RELACION_DUPLICADA
curl -s -w ' -> %{http_code}\n' -X POST "$A/authors/$AID/books" "${AUTH[@]}" -d "{\"isbn\":\"$ISBN\"}"
# Sin token -> 401
curl -s -o /dev/null -w 'POST /authors sin token -> %{http_code}\n' -X POST "$A/authors" -H 'Content-Type: application/json' -d '{"nombre":"X"}'

# books caído: no se puede validar el ISBN -> 503; las lecturas siguen, solo con los ISBN
OTRO="$(curl -s "$B/books?format=json" | json '[1]["isbn"]')"
sudo systemctl stop books
curl -s -w ' -> %{http_code}\n' -X POST "$A/authors/$AID/books" "${AUTH[@]}" -d "{\"isbn\":\"$OTRO\"}"
$CLI -h 127.0.0.1 del "authors:$AID:books" > /dev/null
curl -s "$A/authors/$AID/books"; echo                       # "enriquecido": false, "titulo": null
sudo systemctl start books; sleep 3
curl -s "$A/authors/$AID/books"; echo                       # vuelve el título

# Eliminar un autor con libros -> 409; con ?force=true -> 200 (deja limpio el autor de prueba)
curl -s -w ' -> %{http_code}\n' -X DELETE "$A/authors/$AID" "${AUTH[@]}"
curl -s -w ' -> %{http_code}\n' -X DELETE "$A/authors/$AID?force=true" "${AUTH[@]}"
```

Con el token de un cliente (por ejemplo maruchanvalo), cualquier escritura debe responder `403 ROL_INSUFICIENTE`.

**Resultado (esperado: `404`, `409`, `401`, `503 BOOKS_NO_DISPONIBLE`, lista sin títulos, lista con título, `409`, `200`):**

```
```

### 14.5 App Tk

En tu máquina: `cd apps/Python_app && python main.py`.

1. Entra como **admin** y abre **Autores**: tabla con los autores, y a la derecha *Libros del autor*.
2. **+ Nuevo autor** → llena nombre y apellido → *Crear*. Selecciónalo en la tabla.
3. En *Relacionar un libro* escribe parte de un título (o un ISBN) → *Buscar* → elige el libro en la lista →
   **Relacionar**. Debe aparecer en *Libros del autor* con su título, y la columna *Libros* de la tabla pasa a 1.
4. Abre **Libros** y selecciona ese libro: la franja *Detalle* bajo la tabla debe mostrar en *Autores* al autor recién
   relacionado.
5. De vuelta en **Autores**: selecciona el libro en el panel → **Quitar relación** (pide confirmación). Después
   **Eliminar** al autor de prueba.
6. Cierra sesión y entra como **cliente**: en Autores se ve la tabla y los libros de cada autor, pero **no** aparecen
   *+ Nuevo autor*, *Editar*, *Eliminar*, *Quitar relación* ni el buscador para relacionar.

**Resultado (qué viste en cada paso):**

```
```

### 14.6 Pytest

```bash
cd "$REPO" && bash scripts/run_tests.sh
```

**Resultado (esperado: `Todas las suites pasaron.`):**

```
```

## 15. Si algo falla en la Parte 3

| Síntoma | Qué revisar |
|---|---|
| `500` y en `journalctl -u authors` aparece `relation "authors" does not exist` | No corrió la migración: `psql "$DB_URL" -v ON_ERROR_STOP=1 -f apps/services/authors/sql/001_authors.sql` |
| Relacionar siempre responde `503 BOOKS_NO_DISPONIBLE` | `BOOKS_URL` en `apps/services/authors/.env` y `curl -s http://127.0.0.1:5001/health` |
| `/authors/{id}/books` devuelve `"enriquecido": false` con books arriba | Igual que arriba; tras corregir, espera 60 s o reinicia authors |
| En Libros (app Tk) *Autores* dice "No disponible" | El semáforo de Autores: `sudo systemctl status authors` |
| Un autor aparece en books (columna Autor) pero no en el servicio de autores, o al revés | Es esperado: books conserva su propio campo de texto `autor` (tablas del monolito); la fuente de verdad es authors |


---
---

# PARTE 4 — Microservicio pedidos

Requisito: Partes 1 a 3 funcionando. Corre los bloques en orden y pega la salida en cada **Resultado**.

## 16. Desplegar la Parte 4

```bash
cd ~/WebMonolitoAPI && export REPO="$(pwd)"       # ajusta la ruta
git pull && git log --oneline -3
DB_URL="$(grep '^DATABASE_URL=' apps/services/pedidos/.env | cut -d= -f2-)"

# pedidos valida libros en books y usuarios en users, con la clave interna
for v in BOOKS_URL=http://127.0.0.1:5001 USERS_URL=http://127.0.0.1:5002; do
    grep -q "^${v%%=*}=" apps/services/pedidos/.env || echo "$v" >> apps/services/pedidos/.env
done
grep -q '^RESERVA_MINUTOS=' apps/services/pedidos/.env || echo 'RESERVA_MINUTOS=15' >> apps/services/pedidos/.env
grep -E '^(BOOKS_URL|USERS_URL|RESERVA_MINUTOS)=' apps/services/pedidos/.env
# La clave interna debe ser la misma en pedidos y users (cuenta valores distintos: esperado 1)
cat apps/services/pedidos/.env apps/services/users/.env | grep '^INTERNAL_API_KEY=' | sort -u | wc -l

bash scripts/levantar_servicios.sh                # corre sql/001_pedidos.sql y reinicia los 6 servicios

psql "$DB_URL" -c '\dt inventario|pedido*'
psql "$DB_URL" -c "SELECT COUNT(*) AS filas, SUM(stock_disponible) AS disponible FROM inventario;"
psql "$DB_URL" -c "SELECT COUNT(*) AS libros, SUM(stock) AS stock FROM libros;"       # deben coincidir (carga inicial)
sudo journalctl -u pedidos -n 20 --no-pager | grep -i 'expiracion'                    # "Tarea de expiracion de pedidos iniciada"
```

**Resultado:**

```
```

---

## 17. Comprobación de la Parte 4

Funciones de apoyo (misma terminal para todo el punto 17). Necesitas la contraseña del admin y la de un cliente.

```bash
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)"; }
entrar() {   # entrar CORREO -> deja el JWT en $TOKEN
    local pass; read -r -s -p "Contraseña de $1: " pass; echo
    TOKEN="$(curl -s -X POST 'http://127.0.0.1:5000/login?format=json' -H 'Content-Type: application/json' \
              -d "{\"email\":\"$1\",\"password\":\"$pass\"}" | json '["data"]["token"]')"
}
P=http://127.0.0.1:5004
stock() { curl -s "$P/inventario/$1" | json '["stock_disponible"], "disponible /", d["stock_reservado"], "reservado"'; }
entrar admin@libreria.com;      ADMIN=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
entrar maruchanvalo@gmail.com;  CLI=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
ISBN="$(curl -s 'http://127.0.0.1:5001/books?format=json' | json '[0]["isbn"]')"; echo "ISBN de prueba: $ISBN"
```

### 17.1 Cargar stock como admin, crear un pedido como cliente y ver que el stock disponible baja

```bash
curl -s -w ' -> %{http_code}\n' -X PUT "$P/inventario/$ISBN" "${ADMIN[@]}" -d '{"stock_disponible": 10}'
stock "$ISBN"                                               # 10 disponible / 0 reservado

R="$(curl -s -X POST "$P/pedidos" "${CLI[@]}" -d "{\"lineas\":[{\"isbn\":\"$ISBN\",\"cantidad\":3}]}")"
echo "$R"; PID="$(echo "$R" | json '["id"]')"
stock "$ISBN"                                               # 7 disponible / 3 reservado
curl -s "$P/pedidos" "${CLI[@]}" | json '["items"]'
```

**Resultado (esperado: `201` con `estado: PENDIENTE_PAGO`, título y precio copiados, `expira_en`; stock 7 / 3):**

```
```

### 17.2 Falta de stock, edición y cancelación (el stock regresa)

```bash
# Más de lo disponible -> 409 STOCK_INSUFICIENTE indicando el ISBN
curl -s -w ' -> %{http_code}\n' -X POST "$P/pedidos" "${CLI[@]}" -d "{\"lineas\":[{\"isbn\":\"$ISBN\",\"cantidad\":50}]}"
# ISBN inexistente -> 404
curl -s -w ' -> %{http_code}\n' -X POST "$P/pedidos" "${CLI[@]}" -d '{"lineas":[{"isbn":"9789999999999","cantidad":1}]}'

# Editar el pedido: de 3 a 5 unidades -> la reserva se reajusta
curl -s -o /dev/null -w 'PATCH lineas -> %{http_code}\n' -X PATCH "$P/pedidos/$PID/lineas" "${CLI[@]}" \
     -d "{\"lineas\":[{\"isbn\":\"$ISBN\",\"cantidad\":5}]}"
stock "$ISBN"                                               # 5 disponible / 5 reservado

# Cancelar -> el stock regresa
curl -s "$P/pedidos/$PID/cancelar" -X PATCH "${CLI[@]}" | json '["estado"], d["historial"]'
stock "$ISBN"                                               # 10 disponible / 0 reservado
```

**Resultado:**

```
```

### 17.3 Transiciones de estado y permisos

```bash
R="$(curl -s -X POST "$P/pedidos" "${CLI[@]}" -d "{\"lineas\":[{\"isbn\":\"$ISBN\",\"cantidad\":1}]}")"; PID2="$(echo "$R" | json '["id"]')"
KEY="$(grep '^INTERNAL_API_KEY=' apps/services/pedidos/.env | cut -d= -f2-)"

# El cliente no puede cambiar estados (403) y el admin no puede saltarse el pago (409)
curl -s -o /dev/null -w 'cliente marca ENVIADO -> %{http_code}\n' -X PATCH "$P/pedidos/$PID2/estado" "${CLI[@]}" -d '{"estado":"ENVIADO"}'
curl -s -w ' -> %{http_code}\n' -X PATCH "$P/pedidos/$PID2/estado" "${ADMIN[@]}" -d '{"estado":"ENVIADO"}'

# Lo que hará el servicio pagos (Parte 5): marcar PAGADO con la clave interna
curl -s -o /dev/null -w 'interno PAGADO -> %{http_code}\n' -X PATCH "$P/pedidos/internal/$PID2/estado" \
     -H "X-Internal-Key: $KEY" -H 'Content-Type: application/json' -d '{"estado":"PAGADO"}'
stock "$ISBN"                                               # 9 disponible / 0 reservado (venta confirmada)
curl -s -o /dev/null -w 'admin ENVIADO -> %{http_code}\n'   -X PATCH "$P/pedidos/$PID2/estado" "${ADMIN[@]}" -d '{"estado":"ENVIADO"}'
curl -s -o /dev/null -w 'admin ENTREGADO -> %{http_code}\n' -X PATCH "$P/pedidos/$PID2/estado" "${ADMIN[@]}" -d '{"estado":"ENTREGADO"}'
curl -s "$P/pedidos/$PID2" "${CLI[@]}" | json '["historial"]'
curl -s -o /dev/null -w 'cancelar un ENTREGADO -> %{http_code}\n' -X PATCH "$P/pedidos/$PID2/cancelar" "${ADMIN[@]}"
curl -s -o /dev/null -w 'eliminar un ENTREGADO -> %{http_code}\n' -X DELETE "$P/pedidos/$PID2" "${ADMIN[@]}"
curl -s -o /dev/null -w 'eliminar el CANCELADO -> %{http_code}\n' -X DELETE "$P/pedidos/$PID" "${ADMIN[@]}"
curl -s -o /dev/null -w 'GET /pedidos sin token -> %{http_code}\n' "$P/pedidos"
unset KEY
```

**Resultado (esperado: `403`, `409 TRANSICION_INVALIDA`, `200`, stock 9 / 0, `200`, `200`, historial de 4 pasos, `409`, `409`, `200`, `401`):**

```
```

### 17.4 Expiración con la reserva en 1 minuto

```bash
sed -i 's/^RESERVA_MINUTOS=.*/RESERVA_MINUTOS=1/' apps/services/pedidos/.env
sudo systemctl restart pedidos; sleep 3
sudo journalctl -u pedidos -n 5 --no-pager | grep 'reserva de 1 min'

R="$(curl -s -X POST "$P/pedidos" "${CLI[@]}" -d "{\"lineas\":[{\"isbn\":\"$ISBN\",\"cantidad\":2}]}")"; PID3="$(echo "$R" | json '["id"]')"
echo "$R" | json '["estado"], "expira", d["expira_en"]'
stock "$ISBN"                                               # 7 disponible / 2 reservado
if command -v valkey-cli >/dev/null; then RC=valkey-cli; else RC=redis-cli; fi
read -r -s -p "Contraseña de Redis: " REDISCLI_AUTH; export REDISCLI_AUTH; echo
$RC -h 127.0.0.1 ttl "pedido:reserva:$PID3"                 # <= 60

echo "Esperando 2 minutos y medio (la tarea revisa cada minuto)..."; sleep 150
curl -s "$P/pedidos/$PID3" "${CLI[@]}" | json '["estado"], d["historial"][-1]'      # EXPIRADO, actor sistema:expiracion
stock "$ISBN"                                               # 9 disponible / 0 reservado
sudo journalctl -u pedidos --since '4 minutes ago' --no-pager | grep 'Pedidos expirados'

# Regresa la reserva a 15 minutos
sed -i 's/^RESERVA_MINUTOS=.*/RESERVA_MINUTOS=15/' apps/services/pedidos/.env
sudo systemctl restart pedidos
```

**Resultado:**

```
```

### 17.5 App Tk

En tu máquina: `cd apps/Python_app && python main.py`.

1. Entra como **admin** y abre **Pedidos**: hay tres pestañas (*Comprar*, *Gestión*, *Inventario*).
2. **Inventario:** selecciona un libro, escribe un stock y pulsa *Guardar stock*. La columna *Disponible* cambia.
3. Cierra sesión y entra como **cliente**: en Pedidos solo aparece *Comprar*.
4. En el catálogo (izquierda) selecciona un libro y pulsa **Agregar al carrito →** dos veces. En el carrito (centro)
   cambia la cantidad con el selector; el total se actualiza. Pulsa **Crear pedido**.
5. El pedido aparece en **Mis pedidos** (derecha) en amarillo, *PENDIENTE PAGO*, y el *Disp.* del catálogo baja.
   Selecciónalo: se ven sus líneas, cuándo vence la reserva y el historial. **Ir a pagar** está deshabilitado.
6. Pulsa **Editar**: el carrito dice *Editando pedido #N*. Cambia una cantidad y pulsa **Guardar cambios**.
7. Pulsa **Cancelar** (pide confirmación): el pedido queda en rojo, *CANCELADO*, y el *Disp.* del catálogo regresa.
8. Vuelve a entrar como **admin** → **Gestión**: filtra por estado; selecciona un pedido *PAGADO* (el de 17.3 ya está
   entregado; puedes marcar otro como pagado con el curl interno) y usa *Marcar ENVIADO* y *Marcar ENTREGADO*.

**Resultado (qué viste en cada paso):**

```
```

### 17.6 Pytest

```bash
cd "$REPO" && bash scripts/run_tests.sh
```

**Resultado (esperado: `Todas las suites pasaron.`):**

```
```

## 18. Si algo falla en la Parte 4

| Síntoma | Qué revisar |
|---|---|
| `500` y `relation "inventario" does not exist` en `journalctl -u pedidos` | No corrió la migración: `psql "$DB_URL" -v ON_ERROR_STOP=1 -f apps/services/pedidos/sql/001_pedidos.sql` |
| Crear un pedido responde `503 USERS_NO_DISPONIBLE` | `USERS_URL` en el `.env` de pedidos; que `INTERNAL_API_KEY` sea igual en pedidos y users; `systemctl status users` |
| Crear un pedido responde `503 BOOKS_NO_DISPONIBLE` | `BOOKS_URL` en el `.env` de pedidos; `curl -s http://127.0.0.1:5001/health` |
| `409 STOCK_INSUFICIENTE` con stock en la pantalla Libros | El stock vendible es el de **Inventario** (pedidos), no la columna Stock de Libros: cárgalo en Pedidos → Inventario |
| Los pedidos vencidos no pasan a `EXPIRADO` | `journalctl -u pedidos | grep -i expiracion`: debe decir que la tarea inició; si dice "Redis no disponible", revisa `REDIS_URL`. Espera al menos 1 minuto tras el vencimiento |
| `403 USUARIO_NO_VALIDO` | La cuenta está desactivada en users |


---
---

# PARTE 5 — Microservicio pagos (pago simulado)

Requisito: Partes 1 a 4 funcionando. Datos de esta VM: base **`library`**, usuario `library_user`, IP pública
**34.51.0.253**. Corre los bloques en orden y pega la salida en cada **Resultado**.

> Las pruebas de esta parte **no se ejecutaron** al escribirlas: la sección 19 es para correrlas en tu computadora.

## 19. Pruebas en tu computadora (Windows, PowerShell)

No necesitan PostgreSQL, Redis ni ningún servicio levantado.

```powershell
cd C:\Users\<tu usuario>\Desktop\EG4\apps\services\pagos      # ajusta la ruta del repositorio
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 1) Microservicio pagos
.\.venv\Scripts\python.exe -m pytest -q tests

# 2) Módulo común (cambió el filtro de logs: ahora también oculta "cvv")
cd ..\common
..\pagos\.venv\Scripts\python.exe -m pytest -q tests

# 3) App Tk (cliente de pagos, Idempotency-Key, comprobante); no abre ninguna ventana
cd ..\..\Python_app
..\services\pagos\.venv\Scripts\python.exe -m pytest -q tests
```

Para ver el detalle de un fallo: agrega `-x -vv` (se detiene en el primero y muestra el porqué).

**Resultado (pega la última línea de cada corrida, y el detalle si algo falla):**

```
```

## 20. Desplegar en la VM

```bash
cd ~/WebMonolitoAPI && export REPO="$(pwd)"       # ajusta la ruta
DB_URL="$(grep '^DATABASE_URL=' apps/services/pagos/.env | cut -d= -f2-)"
echo "$DB_URL" | sed -E 's#://([^:]+):[^@]*@#://\1:***@#'       # debe terminar en /library

# 1) Respaldo de la base antes de migrar
mkdir -p ~/respaldos
pg_dump "$DB_URL" -Fc -f ~/respaldos/library_antes_parte5_$(date +%F_%H%M).dump
ls -lh ~/respaldos | tail -2

# 2) Código nuevo
git pull && git log --oneline -3

# 3) pagos habla con pedidos por sus endpoints internos, con la clave interna
grep -q '^PEDIDOS_URL=' apps/services/pagos/.env || echo 'PEDIDOS_URL=http://127.0.0.1:5004' >> apps/services/pagos/.env
grep '^PEDIDOS_URL=' apps/services/pagos/.env
cat apps/services/pagos/.env apps/services/pedidos/.env | grep '^INTERNAL_API_KEY=' | sort -u | wc -l     # esperado: 1

# 4) Dependencias, migración 001_pagos.sql y reinicio de los 6 servicios
bash scripts/levantar_servicios.sh

# 5) Verificación
psql "$DB_URL" -c '\d pagos'
psql "$DB_URL" -c "SELECT version, aplicada_en FROM schema_migraciones ORDER BY aplicada_en;"     # incluye 007_pagos
sudo journalctl -u pagos -n 20 --no-pager | grep -i 'sincronizacion'       # "Tarea de sincronizacion de pagos iniciada"
bash scripts/estado_servicios.sh
```

Si el `.env` de pagos no apunta a la base `library`:
`sed -i 's#/library_db$#/library#' apps/services/pagos/.env && sudo systemctl restart pagos`.

Si necesitaras restaurar el respaldo: `pg_restore --clean --if-exists -d "$DB_URL" ~/respaldos/<archivo>.dump`.

**Resultado:**

```
```

---

## 21. Comprobación de la Parte 5 (curl)

Desde tu computadora (Git Bash) con la IP pública, o dentro de la VM cambiando `H=127.0.0.1`.
Usa la misma terminal para todo el punto 21.

```bash
H=34.51.0.253                                   # dentro de la VM: H=127.0.0.1
PEDIDOS=http://$H:5004; PAGOS=http://$H:5005
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)"; }     # en Windows: usa python en vez de python3
llave() { python3 -c "import uuid; print(uuid.uuid4())"; }
entrar() {   # entrar CORREO -> deja el JWT en $TOKEN
    local pass; read -r -s -p "Contraseña de $1: " pass; echo
    TOKEN="$(curl -s -X POST "http://$H:5000/login?format=json" -H 'Content-Type: application/json' \
              -d "{\"email\":\"$1\",\"password\":\"$pass\"}" | json '["data"]["token"]')"
}
stock() { curl -s "$PEDIDOS/inventario/$1" | json '["stock_disponible"], "disponible /", d["stock_reservado"], "reservado"'; }
entrar admin@libreria.com;      ADMIN=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
entrar maruchanvalo@gmail.com;  CLI=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
ISBN="$(curl -s "http://$H:5001/books?format=json" | json '[0]["isbn"]')"; echo "ISBN de prueba: $ISBN"
curl -s -o /dev/null -w 'stock de prueba -> %{http_code}\n' -X PUT "$PEDIDOS/inventario/$ISBN" "${ADMIN[@]}" -d '{"stock_disponible": 10}'
stock "$ISBN"                                   # 10 disponible / 0 reservado
```

### 21.1 Crear un pedido, pagarlo y verlo en PAGADO

```bash
PID="$(curl -s -X POST "$PEDIDOS/pedidos" "${CLI[@]}" -d "{\"lineas\":[{\"isbn\":\"$ISBN\",\"cantidad\":2}]}" | json '["id"]')"
curl -s "$PEDIDOS/pedidos/$PID" "${CLI[@]}" | json '["estado"], "total", d["total"]'       # PENDIENTE_PAGO
stock "$ISBN"                                   # 8 disponible / 2 reservado

K1="$(llave)"
# El "monto": 1 va a propósito: el servidor debe IGNORARLO y cobrar el total del pedido
R="$(curl -s -w '\n%{http_code}' -X POST "$PAGOS/pagos" "${CLI[@]}" -H "Idempotency-Key: $K1" \
      -d "{\"pedido_id\":$PID,\"metodo\":\"TARJETA_SIMULADA\",\"tarjeta\":\"4111111111111111\",\"cvv\":\"123\",\"monto\":1}")"
echo "$R"; PAGO="$(echo "$R" | head -1 | json '["id"]')"
curl -s "$PEDIDOS/pedidos/$PID" "${CLI[@]}" | json '["estado"], d["historial"][-1]'        # PAGADO, actor servicio:pagos
stock "$ISBN"                                   # 8 disponible / 0 reservado (venta confirmada)
```

**Resultado (esperado: `201`, `estado: APROBADO`, `monto` = total del pedido (no 1), `ultimos4: 1111`,
`sincronizado: true`; pedido en `PAGADO`):**

```
```

### 21.2 Reenviar el mismo pago sin que se duplique

```bash
curl -s -w '\n%{http_code}\n' -X POST "$PAGOS/pagos" "${CLI[@]}" -H "Idempotency-Key: $K1" \
     -d "{\"pedido_id\":$PID,\"metodo\":\"TARJETA_SIMULADA\",\"tarjeta\":\"4111111111111111\",\"cvv\":\"123\"}"
curl -s "$PAGOS/pagos/pedido/$PID" "${CLI[@]}" | json '["items"].__len__(), "pago(s) para el pedido"'
# Con una llave NUEVA tampoco se cobra otra vez: el pedido ya no está pendiente
curl -s -w ' -> %{http_code}\n' -X POST "$PAGOS/pagos" "${CLI[@]}" -H "Idempotency-Key: $(llave)" \
     -d "{\"pedido_id\":$PID,\"metodo\":\"EFECTIVO\"}"
# Sin Idempotency-Key -> 400
curl -s -o /dev/null -w 'sin Idempotency-Key -> %{http_code}\n' -X POST "$PAGOS/pagos" "${CLI[@]}" -d "{\"pedido_id\":$PID,\"metodo\":\"EFECTIVO\"}"
```

**Resultado (esperado: `200` con el MISMO `id` y `"repetido": true`; `1 pago(s)`; `409 PEDIDO_NO_PAGABLE`; `400`):**

```
```

### 21.3 Pagar con una tarjeta terminada en 0000 y ver el rechazo

```bash
PID2="$(curl -s -X POST "$PEDIDOS/pedidos" "${CLI[@]}" -d "{\"lineas\":[{\"isbn\":\"$ISBN\",\"cantidad\":1}]}" | json '["id"]')"
curl -s -w '\n%{http_code}\n' -X POST "$PAGOS/pagos" "${CLI[@]}" -H "Idempotency-Key: $(llave)" \
     -d "{\"pedido_id\":$PID2,\"metodo\":\"TARJETA_SIMULADA\",\"tarjeta\":\"4000000000000000\",\"cvv\":\"123\"}"
curl -s "$PEDIDOS/pedidos/$PID2" "${CLI[@]}" | json '["estado"]'                           # sigue en PENDIENTE_PAGO
# Con otra tarjeta y otra llave sí se paga
curl -s -X POST "$PAGOS/pagos" "${CLI[@]}" -H "Idempotency-Key: $(llave)" \
     -d "{\"pedido_id\":$PID2,\"metodo\":\"TARJETA_SIMULADA\",\"tarjeta\":\"4242424242424242\",\"cvv\":\"123\"}" | json '["estado"]'
curl -s "$PAGOS/pagos/pedido/$PID2" "${CLI[@]}" | json '["items"]' | tr ',' '\n' | grep "'estado'"
```

**Resultado (esperado: `201` con `estado: RECHAZADO` y `ultimos4: 0000`; pedido `PENDIENTE_PAGO`; después `APROBADO`):**

```
```

### 21.4 Reembolsar como admin y ver el pedido en CANCELADO con el stock liberado

```bash
stock "$ISBN"                                   # antes del reembolso: 7 disponible / 0 reservado
# Un cliente no puede reembolsar -> 403
curl -s -o /dev/null -w 'reembolso como cliente -> %{http_code}\n' -X POST "$PAGOS/pagos/$PAGO/reembolso" "${CLI[@]}"
curl -s -w '\n%{http_code}\n' -X POST "$PAGOS/pagos/$PAGO/reembolso" "${ADMIN[@]}" -d '{"notas":"Prueba de reembolso"}'
curl -s "$PEDIDOS/pedidos/$PID" "${CLI[@]}" | json '["estado"], d["historial"][-1]'        # CANCELADO, actor servicio:pagos
stock "$ISBN"                                   # 9 disponible: regresaron las 2 unidades del pedido
curl -s -o /dev/null -w 'reembolsar dos veces -> %{http_code}\n' -X POST "$PAGOS/pagos/$PAGO/reembolso" "${ADMIN[@]}"
```

**Resultado (esperado: `403`; `200` con `estado: REEMBOLSADO`; pedido `CANCELADO`; stock +2; `409`):**

```
```

### 21.5 Permisos, corrección, borrado y datos de tarjeta

```bash
# Permisos
curl -s -o /dev/null -w 'GET /pagos sin token -> %{http_code}\n' "$PAGOS/pagos"
curl -s "$PAGOS/pagos" "${CLI[@]}" | json '["total"], "pago(s) propios"'
curl -s "$PAGOS/pagos?estado=RECHAZADO" "${ADMIN[@]}" | json '["total"], "rechazado(s) en total"'

# El admin corrige referencia y notas, pero nunca el monto (400)
curl -s -w ' -> %{http_code}\n' -X PATCH "$PAGOS/pagos/$PAGO" "${ADMIN[@]}" -d '{"referencia":"REF-MANUAL-1","notas":"Conciliado"}' | tail -c 120
curl -s -w ' -> %{http_code}\n' -X PATCH "$PAGOS/pagos/$PAGO" "${ADMIN[@]}" -d '{"monto": 1}'

# Borrado lógico: solo los rechazados
RECH="$(curl -s "$PAGOS/pagos?estado=RECHAZADO" "${ADMIN[@]}" | json '["items"][0]["id"]')"
curl -s -o /dev/null -w 'eliminar un pago no rechazado -> %{http_code}\n' -X DELETE "$PAGOS/pagos/$PAGO" "${ADMIN[@]}"
curl -s -o /dev/null -w 'eliminar el rechazado -> %{http_code}\n' -X DELETE "$PAGOS/pagos/$RECH" "${ADMIN[@]}"
```

En la VM: ni la base ni los logs deben contener números de tarjeta completos ni CVV.

```bash
psql "$DB_URL" -c "SELECT id, pedido_id, monto, metodo, estado, referencia, ultimos4, sincronizado, activo FROM pagos ORDER BY id;"
sudo journalctl -u pagos --since '1 hour ago' --no-pager | grep -cE '4111111111111111|4000000000000000|4242424242424242'   # esperado: 0
sudo journalctl -u pagos -n 8 --no-pager                                                  # solo método, ruta, status y tiempo
if command -v valkey-cli >/dev/null; then RC=valkey-cli; else RC=redis-cli; fi
read -r -s -p "Contraseña de Redis: " REDISCLI_AUTH; export REDISCLI_AUTH; echo
$RC -h 127.0.0.1 --scan --pattern 'pago:*'                                                # pago:idem:<llave>
$RC -h 127.0.0.1 ttl "pago:idem:$K1"                                                      # cerca de 86400
```

**Resultado (esperado: `401`; totales; `200`; `400`; `409`; `200`; tabla con `ultimos4` y sin tarjetas; `0`):**

```
```

### 21.6 App Tk

En tu máquina: `cd apps\Python_app`, `python main.py`, y en **Configuración** pon la IP `34.51.0.253`.

1. Entra como **cliente**, abre **Pedidos**, crea un pedido y selecciónalo en *Mis pedidos*. El botón **Ir a pagar**
   ya está activo: púlsalo. Se abre **Pagos** con ese pedido elegido y su total en grande.
2. Elige *Tarjeta (simulada)*: aparecen *Número* y *CVV*, enmascarados. Escribe `4111 1111 1111 1111` y `123` y pulsa
   **Pagar**. Debe mostrarse el comprobante (referencia y `•••• 1111`), el pedido desaparece del selector y el pago
   aparece en verde en el historial. En **Pedidos** ese pedido queda en verde, *PAGADO*.
3. Crea otro pedido y págalo con una tarjeta terminada en `0000`: comprobante *RECHAZADO* y fila en rojo; el pedido
   sigue en el selector. Cambia a *Efectivo* (los campos de tarjeta desaparecen) y paga: *APROBADO*.
4. Usa los filtros de *Estado* y *Método* del historial.
5. Revisa la terminal desde la que lanzaste la app: en el log de `POST .../pagos` deben verse `"tarjeta": "********"`
   y `"cvv": "********"`, y el header `Idempotency-Key`.
6. Entra como **admin** → **Pagos**: selecciona un pago aprobado → **Reembolsar** (pide confirmación); queda en gris,
   *REEMBOLSADO*, y el pedido en *CANCELADO*. Prueba **Corregir referencia / notas** y **Eliminar rechazado**.
7. En la VM: `sudo systemctl stop pagos`. En ≤ 10 s el semáforo de Pagos pasa a rojo y la pantalla se cubre con
   *Servicio de pagos no disponible*. `sudo systemctl start pagos`: vuelve sola.

**Resultado (qué viste en cada paso):**

```
```

## 22. Si algo falla en la Parte 5

| Síntoma | Qué revisar |
|---|---|
| `500` y `relation "pagos" does not exist` en `journalctl -u pagos` | No corrió la migración: `psql "$DB_URL" -v ON_ERROR_STOP=1 -f apps/services/pagos/sql/001_pagos.sql` |
| `/health` de pagos con `"db": "error"` | `DATABASE_URL` del `.env` de pagos: debe terminar en `/library` |
| Pagar responde `503 PEDIDOS_NO_DISPONIBLE` | `PEDIDOS_URL` en el `.env` de pagos; `INTERNAL_API_KEY` igual en pagos y pedidos; `systemctl status pedidos` |
| Pagar responde `409 PAGO_EN_PROCESO` | Hay otro pago del mismo pedido en curso; el lock caduca solo en 30 s |
| Un pago queda `APROBADO` con `sincronizado: false` | pedidos no respondió al confirmarlo. La tarea lo reintenta cada minuto: `journalctl -u pagos | grep -i sincroniz` |
| Un pago aparece `REEMBOLSADO` con la nota "Reembolso automático" | El pedido expiró o se canceló antes de poder confirmarle el pago |
| Reembolsar responde `409 PEDIDO_NO_CANCELABLE` | El pedido ya está `ENVIADO` o `ENTREGADO` |
| Pagar responde `403` | El pedido no es del usuario del token (ni el admin paga pedidos ajenos) |
