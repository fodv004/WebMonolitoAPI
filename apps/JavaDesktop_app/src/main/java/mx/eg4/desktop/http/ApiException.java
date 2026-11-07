package mx.eg4.desktop.http;

/**
 * Error de un servicio, ya normalizado de cualquiera de los 3 formatos:
 * login {"status","code","message"}, books {"error","mensaje"}, resto {"error","message"}.
 */
public class ApiException extends Exception {

    /** Codigo propio para errores de red (no hubo respuesta del servidor). */
    public static final String RED = "SIN_CONEXION";
    /** Codigo propio cuando la sesion ya no es valida y la app regreso al login. */
    public static final String SESION_TERMINADA = "SESION_TERMINADA";

    private final String service;
    private final int status;
    private final String code;

    public ApiException(String service, int status, String code, String message) {
        super(message);
        this.service = service;
        this.status = status;
        this.code = code == null ? "ERROR" : code;
    }

    public String service() {
        return service;
    }

    public int status() {
        return status;
    }

    public String code() {
        return code;
    }

    public boolean isNetwork() {
        return RED.equals(code);
    }

    public boolean isSessionEnded() {
        return SESION_TERMINADA.equals(code);
    }

    /** Texto para mostrar al usuario. */
    public String userMessage() {
        String base = getMessage() == null || getMessage().isBlank() ? "Error sin detalle" : getMessage();
        if ("ROL_INSUFICIENTE".equals(code)) {
            return "Permiso insuficiente: " + base;
        }
        return base;
    }

    @Override
    public String toString() {
        return "[" + service + (status > 0 ? " " + status : "") + " " + code + "] " + getMessage();
    }
}
