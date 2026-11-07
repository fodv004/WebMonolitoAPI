package mx.eg4.desktop.service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;

import mx.eg4.desktop.config.AppConfig.Service;
import mx.eg4.desktop.http.ApiClient;
import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.http.Json;
import mx.eg4.desktop.model.Pedido;

/** pedidos (5004). GET /pedidos es paginado (maximo 100 por pagina): se recorren todas las paginas. */
public final class PedidosService {

    private static final int POR_PAGINA = 100;
    private final ApiClient api;

    PedidosService(ApiClient api) {
        this.api = api;
    }

    /** POST /pedidos con {"lineas":[{"isbn","cantidad"}]}. */
    public Pedido crear(List<Map<String, Object>> lineas) throws ApiException {
        return Json.convert(api.post(Service.PEDIDOS, "/pedidos", Map.of("lineas", lineas), true), Pedido.class);
    }

    /** GET /pedidos sin filtro: un cliente recibe los suyos; un admin, todos. */
    public List<Pedido> listarTodos() throws ApiException {
        List<Pedido> out = new ArrayList<>();
        int page = 1;
        int pages;
        do {
            JsonNode r = api.get(Service.PEDIDOS, "/pedidos?page=" + page + "&per_page=" + POR_PAGINA, true);
            r.path("items").forEach(n -> out.add(Json.convert(n, Pedido.class)));
            pages = r.path("pages").asInt(1);
            page++;
        } while (page <= pages);
        return out;
    }

    public Pedido obtener(int id) throws ApiException {
        return Json.convert(api.get(Service.PEDIDOS, "/pedidos/" + id, true), Pedido.class);
    }

    public Pedido cancelar(int id) throws ApiException {
        return Json.convert(api.patch(Service.PEDIDOS, "/pedidos/" + id + "/cancelar", null, true), Pedido.class);
    }
}
