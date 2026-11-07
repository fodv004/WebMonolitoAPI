package mx.eg4.desktop.service;

import java.util.HashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;

import mx.eg4.desktop.config.AppConfig.Service;
import mx.eg4.desktop.http.ApiClient;
import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.http.Json;
import mx.eg4.desktop.model.LoginResult;
import mx.eg4.desktop.util.Log;

/** login (5000): POST /login y POST /logout. POST /refresh lo hace ApiClient. */
public final class LoginService {

    private final ApiClient api;

    LoginService(ApiClient api) {
        this.api = api;
    }

    public LoginResult login(String email, String password) throws ApiException {
        JsonNode resp = api.post(Service.LOGIN, "/login", Map.of("email", email, "password", password), false);
        LoginResult r = Json.convert(resp.path("data"), LoginResult.class);
        if (r == null || r.token() == null || r.user() == null) {
            throw new ApiException("login", 200, "RESPUESTA_INVALIDA", "login no devolvio token ni usuario.");
        }
        api.session().start(r.token(), r.refreshToken(), r.user());
        Log.info("Sesion iniciada: user_id " + r.user().idUsuario() + " (" + api.session().role() + "), token "
                + Log.mask(r.token()));
        return r;
    }

    /** POST /logout con el refresh_token. Nunca lanza: el cierre local se hace siempre. */
    public void logout() {
        String token = api.session().token();
        String refresh = api.session().refreshToken();
        Map<String, String> headers = new HashMap<>();
        if (token != null) {
            headers.put("Authorization", "Bearer " + token);
        }
        try {
            api.post(Service.LOGIN, "/logout", refresh == null ? Map.of() : Map.of("refresh_token", refresh),
                    false, headers);
            Log.info("Sesion cerrada en login");
        } catch (ApiException e) {
            Log.warn("POST /logout fallo (la sesion local se cierra de todos modos): " + e);
        }
    }
}
