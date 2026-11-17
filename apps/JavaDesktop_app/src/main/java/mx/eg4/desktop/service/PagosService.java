package mx.eg4.desktop.service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import mx.eg4.desktop.config.AppConfig.Service;
import mx.eg4.desktop.http.ApiClient;
import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.http.Json;
import mx.eg4.desktop.model.Pago;

/** pagos (gateway /pagos): POST /pagos (con Idempotency-Key) y GET /pagos/pedido/&lt;id&gt;. */
public final class PagosService {

    public static final String TARJETA = "TARJETA_SIMULADA";
    public static final String TRANSFERENCIA = "TRANSFERENCIA";
    public static final String EFECTIVO = "EFECTIVO";

    private final ApiClient api;

    PagosService(ApiClient api) {
        this.api = api;
    }

    public Pago pagar(int pedidoId, String metodo, String tarjeta, String cvv, String idempotencyKey)
            throws ApiException {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("pedido_id", pedidoId);
        body.put("metodo", metodo);
        if (TARJETA.equals(metodo)) {
            body.put("tarjeta", tarjeta);
            body.put("cvv", cvv);
        }
        return Json.convert(api.post(Service.PAGOS, "/pagos", body, true, Map.of("Idempotency-Key", idempotencyKey)),
                Pago.class);
    }

    /** Pagos del pedido, el mas reciente primero. */
    public List<Pago> porPedido(int pedidoId) throws ApiException {
        List<Pago> out = new ArrayList<>();
        api.get(Service.PAGOS, "/pagos/pedido/" + pedidoId, true).path("items")
                .forEach(n -> out.add(Json.convert(n, Pago.class)));
        return out;
    }
}
