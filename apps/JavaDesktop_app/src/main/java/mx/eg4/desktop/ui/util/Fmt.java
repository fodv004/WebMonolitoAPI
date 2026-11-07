package mx.eg4.desktop.ui.util;

import java.text.NumberFormat;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

import javafx.scene.control.Label;

/** Formatos de dinero, fechas y etiquetas de estado. */
public final class Fmt {

    private static final Locale MX = Locale.forLanguageTag("es-MX");
    private static final DateTimeFormatter FECHA = DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm");
    private static final DateTimeFormatter HORA = DateTimeFormatter.ofPattern("HH:mm:ss");

    private Fmt() {
    }

    public static String money(Double v) {
        return v == null ? "—" : NumberFormat.getCurrencyInstance(MX).format(v);
    }

    public static String money(double v) {
        return NumberFormat.getCurrencyInstance(MX).format(v);
    }

    /** "2026-11-06T10:00:00" o con zona -> "06/11/2026 10:00" (hora local). */
    public static String date(String iso) {
        if (iso == null || iso.isBlank()) {
            return "—";
        }
        try {
            return OffsetDateTime.parse(iso).atZoneSameInstant(ZoneId.systemDefault()).format(FECHA);
        } catch (Exception ignored) {
            // sin zona
        }
        try {
            return LocalDateTime.parse(iso).format(FECHA);
        } catch (Exception ignored) {
            return iso;
        }
    }

    /** Hora local de un instante ISO con zona (received_at del tracking). */
    public static String time(String iso) {
        if (iso == null || iso.isBlank()) {
            return "—";
        }
        try {
            return OffsetDateTime.parse(iso).atZoneSameInstant(ZoneId.systemDefault()).format(HORA);
        } catch (Exception ignored) {
            return date(iso);
        }
    }

    public static String text(Object o) {
        return o == null ? "—" : String.valueOf(o);
    }

    /** Etiqueta de estado tal cual la regresa el servicio, con color por valor. */
    public static Label badge(String estado) {
        Label l = new Label(estado == null ? "—" : estado);
        l.getStyleClass().add("badge");
        if (estado != null) {
            l.getStyleClass().add("badge-" + estado.toLowerCase(Locale.ROOT).replace('_', '-'));
        }
        return l;
    }
}
