package mx.eg4.desktop.model;

/** data de POST /login y POST /refresh. */
public record LoginResult(Usuario user, String token, String tokenType, Integer expiresIn, String refreshToken,
                          Integer refreshExpiresIn) {
}
