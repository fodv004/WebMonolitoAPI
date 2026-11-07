package mx.eg4.desktop.service;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

final class Paths {

    private Paths() {
    }

    /** Codifica un segmento de ruta (ISBN, codigo de rastreo). */
    static String seg(String value) {
        return URLEncoder.encode(value.trim(), StandardCharsets.UTF_8).replace("+", "%20");
    }
}
