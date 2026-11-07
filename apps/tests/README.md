# Prueba de estrés del microservicio books con Locust

Prueba de carga con **20 usuarios simultáneos** contra el microservicio
`books` (`http://34.51.8.25:5001`). Cada usuario inicia sesión en el
microservicio de login (`http://34.51.8.25:5000/login`), obtiene un JWT
y lo envía en `Authorization: Bearer <token>` en cada petición a books.

Archivos de esta carpeta:

| Archivo | Contenido |
|---|---|
| `locustfile.py` | Escenario de Locust documentado (no se llama `locust.py` porque ese nombre choca con la librería). |
| `Locust_Test_Books.md` | Enunciado de la práctica. |
| `README.md` | Este archivo. |

## Endpoints que se prueban

| Método | Ruta | Notas |
|---|---|---|
| GET | `/books`, `/books?format=json`, `/books?format=xml` | Catálogo completo. |
| GET | `/books/<isbn>?format=json` / `xml` | ISBN reales tomados del catálogo. |
| GET | `/books/0000000000000` | Debe responder **404** (se cuenta como éxito). |
| GET | `/books/gallery?format=json` / `xml` | Libros con sus imágenes. |
| GET | `/cloud-concepts?format=json` / `xml` | Conceptos IaaS/PaaS/SaaS/FaaS. |
| GET | `/formats?format=json` / `xml` | Formatos existentes. |
| GET | `/health`, `/metrics` | Salud y contadores del servicio. |
| POST | `/soap` | Solo operaciones de lectura: `ObtenerConceptosPendientes` y `ObtenerProgresoUsuario`. |
| POST / PUT / PATCH / DELETE | `/books`, `/books/<isbn>` | Requieren cuenta **admin**. Con una cuenta sin admin solo se verifica que `POST /books` responda **403**. |
| POST | `/books/internal/stock/reservar` y `/liberar` | Con `LOCUST_INTERNAL_KEY` se reserva y libera 1 unidad del libro de prueba; sin ella se verifica que respondan **401**. |

### Limpieza de la base de datos

El flujo CRUD crea un libro temporal (ISBN `999` + 10 dígitos al azar,
sin autor, género ni portada y con un formato que ya existe), lo
consulta, lo edita con PUT y PATCH y **siempre lo borra** con DELETE.
Si detienes la prueba a mitad de un flujo, Locust borra al terminar los
libros de prueba que hayan quedado.

## 1. Instalación en Windows 11

Requisitos: Python 3.10 o superior (`python --version` en PowerShell).

```powershell
cd "C:\Users\Fernando Olivares\Desktop\EG4\apps\tests"

# Entorno virtual (recomendado)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Si PowerShell bloquea el script de activación:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

pip install locust
locust --version
```

## 2. Credenciales (variables de entorno)

Las credenciales **no** están en el código. Defínelas en la misma
ventana de PowerShell donde vas a ejecutar Locust:

```powershell
$env:LOCUST_EMAIL    = "tu_correo@dominio.com"
$env:LOCUST_PASSWORD = "tu_password"

# Opcionales
# $env:LOCUST_LOGIN_URL    = "http://34.51.8.25:5000/login"
# $env:LOCUST_INTERNAL_KEY = "<INTERNAL_API_KEY de los servicios>"
```

- La cuenta debe estar **confirmada**. Si su rol es **admin**
  (`role_id = 1`), se prueban también POST/PUT/PATCH/DELETE.
- Las variables solo duran mientras la ventana está abierta. Para
  guardarlas de forma permanente usa `setx LOCUST_EMAIL "..."` y abre
  una ventana nueva.
- En CMD la sintaxis es `set LOCUST_EMAIL=tu_correo@dominio.com`.

## 3. Ejecutar Locust con la interfaz web (GUI)

```powershell
cd "C:\Users\Fernando Olivares\Desktop\EG4\apps\tests"
locust -f locustfile.py --host http://34.51.8.25:5001
```

Abre en el navegador: <http://localhost:8089>

En el formulario **Start new load test** escribe:

| Campo | Valor |
|---|---|
| Number of users (peak concurrency) | `20` |
| Ramp up (users started/second) — *spawn rate* | `2` |
| Host | `http://34.51.8.25:5001` |
| Run time (en *Advanced options*, opcional) | p. ej. `5m` |

Pulsa **START**. Con spawn rate 2 los 20 usuarios están activos a los
10 segundos. Si quieres que arranquen todos a la vez, usa spawn rate `20`.

También puedes dejar los valores precargados en el formulario:

```powershell
locust -f locustfile.py --host http://34.51.8.25:5001 -u 20 -r 2
```

## 4. Leer los resultados

| Pestaña | Qué muestra |
|---|---|
| **Statistics** | Peticiones, fallos, tiempos (mediana, p95, p99) y RPS por endpoint. |
| **Charts** | RPS total, tiempos de respuesta y número de usuarios en el tiempo. |
| **Failures** | Errores agrupados por endpoint y mensaje. |
| **Exceptions** | Excepciones del locustfile (p. ej. login fallido). |
| **Download Data** | Reporte HTML y CSV de la ejecución. |

Los endpoints con `[isbn]` se agrupan en una sola fila para que las
estadísticas no se dividan por cada ISBN.

Para detener la prueba pulsa **STOP** en la GUI y luego `Ctrl+C` en
PowerShell.

## 5. Problemas comunes

| Síntoma | Causa / solución |
|---|---|
| `Faltan LOCUST_EMAIL / LOCUST_PASSWORD` | No definiste las variables en esa ventana de PowerShell. |
| `[login] POST /login` falla con 401 | Email o password incorrectos. |
| `[login] POST /login` falla con 403 | La cuenta no está confirmada o está inactiva. |
| `POST /books` falla con 401 | El token expiró o fue revocado (cerraste sesión desde otra app). |
| `POST /books (403 esperado, sin admin)` | Normal con una cuenta sin rol admin: no se crean datos. |
| `/health` responde 503 | PostgreSQL o Redis de la VM no responden. |
| `ImportError` al iniciar Locust | El archivo se llama `locust.py`; debe llamarse `locustfile.py`. |
| No abre `localhost:8089` | Otro proceso usa el puerto: `locust -f locustfile.py --web-port 8090`. |
