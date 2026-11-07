package mx.eg4.desktop.model;

/** Respuesta de ObtenerProgresoUsuario (SOAP). */
public record ProgresoSoap(String correo, int totalClasificados, int totalPendientes) {
}
