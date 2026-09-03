"""
soap/service.py
Logica de negocio y acceso a datos de las 3 operaciones del
contrato. Consultas parametrizadas, transacciones con rollback
automatico ante error (Parte 6, punto 12 del PDF).

Este modulo NO conoce nada de XML/SOAP: solo recibe/devuelve
datos simples de Python. envelope.py y app.py se encargan de la
traduccion hacia/desde XML.
"""
import psycopg2
from db.connection import get_connection
from soap.faults import ConceptoInexistente, ModeloInvalido, ClasificacionDuplicada

MODELOS_VALIDOS = {"IaaS", "PaaS", "SaaS", "FaaS"}


# ============================================================
# 1. ObtenerConceptosPendientes
# "Pendiente" es relativo a cada clasificador (correo), no global.
# ============================================================
def obtener_conceptos_pendientes(correo_clasificador):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT l.isbn, l.titulo, c.id_concepto, c.nombre,
                       lc.definicion,
                       string_agg(DISTINCT g.nombre, ', ') AS nombre_genero
                FROM libro_concepto lc
                JOIN libros l ON l.isbn = lc.isbn
                JOIN conceptos c ON c.id_concepto = lc.id_concepto
                LEFT JOIN libro_genero lg ON lg.isbn = l.isbn
                LEFT JOIN generos g ON g.id_genero = lg.id_genero
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM clasificaciones_cloud cc
                    JOIN clasificadores cl ON cl.id_clasificador = cc.id_clasificador
                    WHERE cc.isbn = l.isbn
                      AND cc.id_concepto = c.id_concepto
                      AND cl.correo = %s
                )
                GROUP BY l.isbn, l.titulo, c.id_concepto, c.nombre, lc.definicion
                ORDER BY l.isbn, c.id_concepto;
                """,
                (correo_clasificador,),
            )
            rows = cur.fetchall()

        return [
            {
                "isbn": isbn,
                "tituloLibro": titulo,
                "idConcepto": id_concepto,
                "nombreConcepto": nombre_concepto,
                "definicion": definicion,
                "nombreGenero": nombre_genero,
            }
            for isbn, titulo, id_concepto, nombre_concepto, definicion, nombre_genero in rows
        ]
    finally:
        conn.close()


# ============================================================
# 2. RegistrarClasificacion
# Transaccion: busca/crea clasificador -> valida concepto ->
# inserta clasificacion (UNIQUE detecta duplicado) -> actualiza
# clientes_servidos. Todo o nada (rollback automatico con "with conn").
# ============================================================
def registrar_clasificacion(nombre, apellidos, correo, isbn, id_concepto,
                             modelo_cloud, tipo_cliente, identificador_cliente):
    if modelo_cloud not in MODELOS_VALIDOS:
        raise ModeloInvalido(
            f"Modelo '{modelo_cloud}' invalido. Debe ser uno de: {', '.join(sorted(MODELOS_VALIDOS))}."
        )

    conn = get_connection()
    try:
        with conn:  # commit automatico al salir sin error; rollback si hay excepcion
            with conn.cursor() as cur:
                # a) Validar que el concepto exista para ese libro (solo lectura)
                cur.execute(
                    "SELECT 1 FROM libro_concepto WHERE isbn = %s AND id_concepto = %s",
                    (isbn, id_concepto),
                )
                if cur.fetchone() is None:
                    raise ConceptoInexistente(
                        f"El concepto {id_concepto} no existe para el libro {isbn}."
                    )

                # b) Buscar o crear al clasificador (Paso 1: no se usa 'usuarios' del monolito)
                cur.execute(
                    "SELECT id_clasificador FROM clasificadores WHERE correo = %s",
                    (correo,),
                )
                row = cur.fetchone()
                if row:
                    id_clasificador = row[0]
                else:
                    cur.execute(
                        """INSERT INTO clasificadores (nombre, apellidos, correo)
                           VALUES (%s, %s, %s) RETURNING id_clasificador""",
                        (nombre, apellidos, correo),
                    )
                    id_clasificador = cur.fetchone()[0]

                # c) Insertar clasificacion. La restriccion UNIQUE
                #    (id_clasificador, id_concepto) del Paso 7 detecta duplicados.
                try:
                    cur.execute(
                        """INSERT INTO clasificaciones_cloud
                               (isbn, id_concepto, id_clasificador, modelo_cloud)
                           VALUES (%s, %s, %s, %s)
                           RETURNING id_clasificacion, fecha_clasificacion""",
                        (isbn, id_concepto, id_clasificador, modelo_cloud),
                    )
                except psycopg2.errors.UniqueViolation:
                    raise ClasificacionDuplicada(
                        "Este clasificador ya registro una clasificacion para este concepto."
                    )
                id_clasificacion, fecha_clasificacion = cur.fetchone()

                # d) Registrar/contabilizar al cliente de escritorio que hizo la peticion
                cur.execute(
                    """INSERT INTO clientes_servidos
                           (tipo_cliente, identificador, peticiones_atendidas, ultima_peticion)
                       VALUES (%s, %s, 1, NOW())
                       ON CONFLICT (tipo_cliente, identificador)
                       DO UPDATE SET
                           peticiones_atendidas = clientes_servidos.peticiones_atendidas + 1,
                           ultima_peticion = NOW();""",
                    (tipo_cliente, identificador_cliente),
                )

        return {
            "idClasificacion": id_clasificacion,
            "fechaClasificacion": fecha_clasificacion.isoformat(),
            "mensaje": "Clasificacion registrada correctamente.",
        }
    finally:
        conn.close()


# ============================================================
# 3. ObtenerProgresoUsuario
# ============================================================
def obtener_progreso_usuario(correo_clasificador):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id_clasificador FROM clasificadores WHERE correo = %s",
                (correo_clasificador,),
            )
            row = cur.fetchone()

            if row is None:
                total_clasificados = 0
            else:
                id_clasificador = row[0]
                cur.execute(
                    "SELECT COUNT(*) FROM clasificaciones_cloud WHERE id_clasificador = %s",
                    (id_clasificador,),
                )
                total_clasificados = cur.fetchone()[0]
    finally:
        conn.close()

    total_pendientes = len(obtener_conceptos_pendientes(correo_clasificador))

    return {
        "correo": correo_clasificador,
        "totalClasificados": total_clasificados,
        "totalPendientes": total_pendientes,
    }