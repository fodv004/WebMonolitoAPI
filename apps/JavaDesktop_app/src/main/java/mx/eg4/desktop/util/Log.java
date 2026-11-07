package mx.eg4.desktop.util;

import java.time.LocalTime;
import java.time.format.DateTimeFormatter;

/** Log sencillo en consola. Nunca recibe tokens completos ni contrasenas: usa mask(). */
public final class Log {

    private static final DateTimeFormatter HORA = DateTimeFormatter.ofPattern("HH:mm:ss.SSS");

    private Log() {
    }

    private static synchronized void print(String tag, String msg) {
        System.out.println(LocalTime.now().format(HORA) + " [" + tag + "] " + msg);
    }

    public static void http(String method, String url, int status, long ms) {
        print("HTTP", String.format("%-6s %s -> %s (%d ms)", method, url, status > 0 ? status : "SIN RESPUESTA", ms));
    }

    public static void ws(String msg) {
        print("WS", msg);
    }

    public static void info(String msg) {
        print("INFO", msg);
    }

    public static void warn(String msg) {
        print("WARN", msg);
    }

    /** Primeros 6 caracteres de un token, para poder distinguirlos sin exponerlos. */
    public static String mask(String token) {
        if (token == null || token.isEmpty()) {
            return "(vacio)";
        }
        return token.substring(0, Math.min(6, token.length())) + "…(" + token.length() + ")";
    }
}
