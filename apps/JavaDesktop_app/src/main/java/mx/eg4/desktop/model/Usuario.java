package mx.eg4.desktop.model;

/** Usuario de login (data.user) o de users (GET /users/me). */
public record Usuario(Integer idUsuario, String nombre, String apellidoPaterno, String apellidoMaterno, String email,
                      Integer roleId, String role, Boolean activo, Boolean emailVerificado, Boolean esAdmin,
                      String estadoCuenta, String createdAt, String updatedAt) {

    public String nombreCompleto() {
        StringBuilder sb = new StringBuilder(nombre == null ? "" : nombre);
        if (apellidoPaterno != null && !apellidoPaterno.isBlank()) {
            sb.append(" ").append(apellidoPaterno);
        }
        if (apellidoMaterno != null && !apellidoMaterno.isBlank()) {
            sb.append(" ").append(apellidoMaterno);
        }
        return sb.toString().trim();
    }
}
