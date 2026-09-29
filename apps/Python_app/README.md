# Python_app

App de escritorio en Python (Tkinter + ttk) para la librería en línea. Permite iniciar sesión, registrar cuentas y gestionar el catálogo de libros (CRUD) contra los microservicios del proyecto.

## Características

- Login y registro contra el microservicio de **auth** (puerto 5000). El JWT que devuelve `POST /login` se guarda solo en memoria.
- Catálogo de libros en tabla (`Treeview`) con semáforo (verde/rojo) del estado de los servicios, contra el microservicio de **libros** (puerto 5001).
- CRUD completo de libros: crear (POST), editar (PUT), editar parcial (PATCH), eliminar (DELETE) y buscar (ISBN/título/autor/género). Las escrituras envían `Authorization: Bearer <token>`.
- Si el servicio de libros responde 401/403 se avisa que la sesión no es válida o expiró y se vuelve al login.
- Todo el tráfico HTTP (petición y respuesta) se imprime en la consola desde `api_client.py`.
- Pantalla de **Configuración** para cambiar las URLs de ambos servicios, guardadas en `local_storage.json`.
- Dependencia externa: `requests` (`pip install -r requirements.txt`).

## Estructura

```
Python_app/
├── main.py              # Punto de entrada
├── api_client.py        # Cliente HTTP (requests) hacia auth y libros + log en consola
├── requirements.txt
├── storage.py            # Persistencia de configuración (local_storage.json)
├── utils.py              # Utilidades varias
└── ui/
    ├── theme.py          # Paleta, tipografía y estilos ttk
    ├── login_screen.py
    ├── register_screen.py
    ├── config_screen.py
    ├── catalog_screen.py
    └── book_form.py
```

## Requisitos previos

- Base de datos PostgreSQL (`library`) creada y con datos.
- Microservicio de auth corriendo en `http://localhost:5000`.
- Microservicio de libros corriendo en `http://localhost:5001`.

## Ejecutar

```
cd apps/Python_app
pip install -r requirements.txt
python main.py
```

Lánzala desde una terminal para ver el log de peticiones y respuestas.

Si los servicios no corren en `localhost`, ábrelos desde la pantalla de **Configuración** (accesible desde el login) y ajusta las URLs; se guardan automáticamente para la próxima vez.

Para la guía completa (levantar los microservicios, configurar correo, probar el flujo end-to-end y solución de problemas), ver [instrucciones.txt](instrucciones.txt). Para JWT, PATCH y logging ver `instrucciones.txt` y `pruebas.txt` en la raíz del proyecto.
