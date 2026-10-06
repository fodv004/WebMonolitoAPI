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
