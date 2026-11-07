package mx.eg4.desktop.service;

import mx.eg4.desktop.config.AppConfig.Service;
import mx.eg4.desktop.http.ApiClient;
import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.http.Json;
import mx.eg4.desktop.model.Usuario;

/** users (5002): GET /users/me. */
public final class UsersService {

    private final ApiClient api;

    UsersService(ApiClient api) {
        this.api = api;
    }

    public Usuario me() throws ApiException {
        return Json.convert(api.get(Service.USERS, "/users/me", true), Usuario.class);
    }
}
