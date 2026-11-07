package mx.eg4.desktop.service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;

import mx.eg4.desktop.config.AppConfig.Service;
import mx.eg4.desktop.http.ApiClient;
import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.http.Json;
import mx.eg4.desktop.model.Envio;

/** tracking (5900): POST /envios, GET /envios (paginado) y GET /envios/&lt;codigo&gt;. */
public final class EnviosService {

    private static final int POR_PAGINA = 100;
    private final ApiClient api;

    EnviosService(ApiClient api) {
        this.api = api;
    }

    /** 201 si se creo, 200 si el pedido ya tenia envio: en ambos casos devuelve el envio completo. */
    public Envio crear(int pedidoId) throws ApiException {
        return Json.convert(api.post(Service.TRACKING, "/envios", Map.of("pedido_id", pedidoId), true), Envio.class);
    }

    public List<Envio> listarTodos() throws ApiException {
        List<Envio> out = new ArrayList<>();
        int page = 1;
        int pages;
        do {
            JsonNode r = api.get(Service.TRACKING, "/envios?page=" + page + "&per_page=" + POR_PAGINA, true);
            r.path("items").forEach(n -> out.add(Json.convert(n, Envio.class)));
            pages = r.path("pages").asInt(1);
            page++;
        } while (page <= pages);
        return out;
    }

    public Envio obtener(String codigo) throws ApiException {
        return Json.convert(api.get(Service.TRACKING, "/envios/" + Paths.seg(codigo.toUpperCase()), true),
                Envio.class);
    }
}
