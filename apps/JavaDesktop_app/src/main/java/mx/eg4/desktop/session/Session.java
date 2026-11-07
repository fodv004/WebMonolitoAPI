package mx.eg4.desktop.session;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import mx.eg4.desktop.model.Usuario;
import mx.eg4.desktop.util.Log;

/** Datos de la sesion actual: token, refresh_token, usuario y rol. Accesible desde cualquier hilo. */
public final class Session {

    private volatile String token;
    private volatile String refreshToken;
    private volatile Usuario user;
    private volatile String role;
    private final List<AutoCloseable> closeables = new CopyOnWriteArrayList<>();

    public synchronized void start(String token, String refreshToken, Usuario user) {
        this.token = token;
        this.refreshToken = refreshToken;
        this.user = user;
        this.role = user != null && user.role() != null ? user.role()
                : (user != null && Integer.valueOf(1).equals(user.roleId()) ? "admin" : "cliente");
    }

    public synchronized void updateTokens(String token, String refreshToken) {
        this.token = token;
        if (refreshToken != null) {
            this.refreshToken = refreshToken;
        }
    }

    /** Cierra los WebSocket registrados y borra todo. */
    public synchronized void clear() {
        List<AutoCloseable> copia = new ArrayList<>(closeables);
        closeables.clear();
        for (AutoCloseable c : copia) {
            try {
                c.close();
            } catch (Exception e) {
                Log.warn("No se pudo cerrar un recurso de la sesion: " + e.getMessage());
            }
        }
        token = null;
        refreshToken = null;
        user = null;
        role = null;
    }

    public boolean isActive() {
        return token != null;
    }

    public String token() {
        return token;
    }

    public String refreshToken() {
        return refreshToken;
    }

    public Usuario user() {
        return user;
    }

    public String role() {
        return role;
    }

    public boolean isAdmin() {
        return "admin".equalsIgnoreCase(role);
    }

    public String email() {
        return user == null ? null : user.email();
    }

    /** Recursos (WebSocket) que deben cerrarse al cerrar sesion. */
    public void register(AutoCloseable c) {
        closeables.add(c);
    }

    public void unregister(AutoCloseable c) {
        closeables.remove(c);
    }
}
