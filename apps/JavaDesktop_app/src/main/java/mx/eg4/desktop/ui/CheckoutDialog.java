package mx.eg4.desktop.ui;

import java.util.List;
import java.util.UUID;

import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.Node;
import javafx.scene.Scene;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.PasswordField;
import javafx.scene.control.RadioButton;
import javafx.scene.control.ScrollPane;
import javafx.scene.control.TextField;
import javafx.scene.control.ToggleGroup;
import javafx.scene.input.Clipboard;
import javafx.scene.input.ClipboardContent;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;
import javafx.stage.Modality;
import javafx.stage.Stage;

import mx.eg4.desktop.cart.Cart;
import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.model.Envio;
import mx.eg4.desktop.model.LineaPedido;
import mx.eg4.desktop.model.Pago;
import mx.eg4.desktop.model.Pedido;
import mx.eg4.desktop.service.PagosService;
import mx.eg4.desktop.ui.util.Alerts;
import mx.eg4.desktop.ui.util.Fmt;
import mx.eg4.desktop.ui.util.LoadingPane;
import mx.eg4.desktop.util.Log;

/**
 * Compra: POST /pedidos -> POST /pagos (Idempotency-Key) -> POST /envios.
 * Tambien se abre desde Mis compras para pagar un pedido PENDIENTE_PAGO.
 */
public final class CheckoutDialog {

    private final Ctx ctx;
    private final Stage stage = new Stage();
    private final VBox body = new VBox(16);
    private final LoadingPane loading;
    private boolean fromCart;
    private Pedido pedido;
    /** Llave del intento en curso. Se conserva SOLO si el intento fallo por red (para reintentar igual). */
    private String pendingKey;
    private Runnable onClose = () -> { };

    public CheckoutDialog(Ctx ctx) {
        this.ctx = ctx;
        body.setPadding(new Insets(24));
        ScrollPane scroll = new ScrollPane(body);
        scroll.setFitToWidth(true);
        scroll.getStyleClass().add("plain-scroll");
        loading = new LoadingPane(scroll);
        loading.getStyleClass().add("dialog-root");
        loading.setId("checkout");
        Scene scene = new Scene(loading, 640, 640);
        scene.getStylesheets().add(getClass().getResource("/css/app.css").toExternalForm());
        stage.setScene(scene);
        stage.setTitle("Compra");
        stage.initOwner(ctx.stage);
        stage.initModality(Modality.WINDOW_MODAL);
        stage.setOnHidden(e -> onClose.run());
    }

    public CheckoutDialog onClose(Runnable r) {
        this.onClose = r;
        return this;
    }

    /** Desde la cesta: resumen y crear el pedido. */
    public void showForCart() {
        fromCart = true;
        renderSummary();
        stage.show();
    }

    /** Desde Mis compras: pagar un pedido existente. */
    public void showForPedido(Pedido p) {
        pedido = p;
        renderPayment(null);
        stage.show();
    }

    // ------------------------------------------------------------------ paso 1: pedido

    private void renderSummary() {
        Label t = title("Confirmar pedido");
        VBox lines = new VBox(6);
        for (Cart.Item i : ctx.cart.items()) {
            lines.getChildren().add(lineRow(i.titulo(), i.cantidadProperty().get(), i.precioProperty().get(),
                    i.precioProperty().get() * i.cantidadProperty().get()));
        }
        Label total = new Label("Total estimado: " + Fmt.money(ctx.cart.totalBinding().get()));
        total.getStyleClass().add("total");
        Label note = muted("El total definitivo lo calcula el servicio de pedidos. Al crear el pedido se apartan "
                + "las existencias por un tiempo limitado.");
        Button create = new Button("Crear pedido");
        create.setId("checkout-create");
        create.getStyleClass().add("primary");
        create.setOnAction(e -> createPedido());
        Button cancel = new Button("Volver");
        cancel.setOnAction(e -> stage.close());
        body.getChildren().setAll(t, card(lines), total, note, actions(cancel, create));
    }

    private void createPedido() {
        List<java.util.Map<String, Object>> lineas = ctx.cart.lineasParaPedido();
        loading.run("Creando pedido…", () -> ctx.services.pedidos.crear(lineas), p -> {
            pedido = p;
            Log.info("Pedido creado #" + p.id() + " total " + p.total() + " estado " + p.estado());
            renderPayment(null);
        });
    }

    // ------------------------------------------------------------------ paso 2: pago

    private void renderPayment(String aviso) {
        Label t = title("Pagar pedido #" + pedido.id());
        VBox resumen = pedidoResumen();

        ToggleGroup g = new ToggleGroup();
        RadioButton rTarjeta = radio("Tarjeta simulada", PagosService.TARJETA, g);
        RadioButton rTransf = radio("Transferencia", PagosService.TRANSFERENCIA, g);
        RadioButton rEfectivo = radio("Efectivo", PagosService.EFECTIVO, g);
        rTarjeta.setSelected(true);
        HBox metodos = new HBox(18, rTarjeta, rTransf, rEfectivo);

        TextField numero = new TextField("4111111111111111");
        numero.setId("checkout-card");
        numero.setPromptText("Numero de tarjeta de prueba");
        PasswordField cvv = new PasswordField();
        cvv.setText("123");
        cvv.setPromptText("CVV");
        cvv.setPrefWidth(90);
        GridPane cardForm = new GridPane();
        cardForm.setHgap(10);
        cardForm.setVgap(8);
        cardForm.addRow(0, fieldLabel("Numero"), numero);
        cardForm.addRow(1, fieldLabel("CVV"), cvv);
        GridPane.setHgrow(numero, Priority.ALWAYS);
        Label nota = new Label("⚠ Pago simulado: NO es una tarjeta real y no se cobra nada. Usa un numero de prueba "
                + "(13 a 19 digitos) y un CVV de 3 o 4 digitos. Una tarjeta que termina en 0000 se rechaza.");
        nota.setWrapText(true);
        nota.getStyleClass().add("note");
        VBox tarjetaBox = new VBox(10, cardForm, nota);
        tarjetaBox.managedProperty().bind(rTarjeta.selectedProperty());
        tarjetaBox.visibleProperty().bind(rTarjeta.selectedProperty());

        Label status = new Label(aviso == null ? "" : aviso);
        status.setWrapText(true);
        status.getStyleClass().add(aviso == null ? "muted" : "error-text");

        Button pay = new Button("Pagar " + Fmt.money(pedido.total()));
        pay.setId("checkout-pay");
        status.setId("checkout-status");
        pay.getStyleClass().add("primary");
        Button cancelPedido = new Button("Cancelar pedido");
        cancelPedido.getStyleClass().add("danger");
        cancelPedido.setOnAction(e -> cancelPedido());
        Button later = new Button("Pagar despues");
        later.setOnAction(e -> stage.close());

        pay.setOnAction(e -> {
            String metodo = (String) g.getSelectedToggle().getUserData();
            String num = numero.getText() == null ? "" : numero.getText().replaceAll("[\\s-]", "");
            String c = cvv.getText() == null ? "" : cvv.getText().trim();
            if (PagosService.TARJETA.equals(metodo) && (!num.matches("\\d{13,19}") || !c.matches("\\d{3,4}"))) {
                status.getStyleClass().setAll("error-text");
                status.setText("Revisa la tarjeta (13 a 19 digitos) y el CVV (3 o 4 digitos).");
                return;
            }
            pay(metodo, num, c, status);
        });

        body.getChildren().setAll(t, resumen, section("Metodo de pago"), metodos, tarjetaBox, status,
                actions(later, cancelPedido, pay));
    }

    private void pay(String metodo, String tarjeta, String cvv, Label status) {
        boolean reintento = pendingKey != null;
        String key = reintento ? pendingKey : UUID.randomUUID().toString();
        pendingKey = key;
        Log.info("POST /pagos pedido #" + pedido.id() + " metodo " + metodo + " Idempotency-Key " + key
                + (reintento ? " (reintento con la misma llave)" : ""));
        int id = pedido.id();
        loading.run("Procesando pago…", () -> ctx.services.pagos.pagar(id, metodo, tarjeta, cvv, key), pago -> {
            pendingKey = null;
            showPaymentResult(pago);
        }, err -> {
            ApiException api = Alerts.unwrap(err);
            if (api != null && api.isSessionEnded()) {
                stage.close();
                return;
            }
            status.getStyleClass().setAll("error-text");
            if (api != null && api.isNetwork()) {
                // Puede que el pago si se haya registrado: se reintenta con la MISMA llave.
                status.setText(api.userMessage() + "\nPulsa Pagar de nuevo: se reintentara con la misma "
                        + "Idempotency-Key, asi no se cobra dos veces.");
            } else {
                pendingKey = null;
                status.setText(Alerts.message(err) + (api != null ? "  (" + api.code() + ")" : ""));
            }
        });
    }

    // ------------------------------------------------------------------ paso 3: resultado

    private void showPaymentResult(Pago pago) {
        Label t = title("Resultado del pago");
        Label estado = Fmt.badge(pago.estado());
        estado.setId("checkout-pago-estado");
        GridPane g = grid();
        int r = 0;
        r = kv(g, r, "Pedido", "#" + pago.pedidoId());
        r = kv(g, r, "Monto", Fmt.money(pago.monto()));
        r = kv(g, r, "Metodo", pago.metodo() + (pago.ultimos4() != null ? " ···· " + pago.ultimos4() : ""));
        r = kv(g, r, "Referencia", pago.referencia());
        r = kv(g, r, "Fecha", Fmt.date(pago.createdAt()));
        if (Boolean.TRUE.equals(pago.repetido())) {
            kv(g, r, "Nota", "Respuesta de un intento anterior con la misma Idempotency-Key.");
        }
        HBox head = new HBox(10, t, estado);
        head.setAlignment(Pos.CENTER_LEFT);

        if ("APROBADO".equals(pago.estado())) {
            if (fromCart) {
                ctx.cart.clear();
            }
            VBox envioBox = new VBox(10, muted("Generando el envio…"));
            body.getChildren().setAll(head, card(g), section("Envio"), envioBox);
            createEnvio(envioBox);
        } else if ("RECHAZADO".equals(pago.estado())) {
            Label msg = new Label("El pago fue rechazado. Puedes intentar con otro metodo o tarjeta, o cancelar el "
                    + "pedido para liberar los libros.");
            msg.setWrapText(true);
            msg.getStyleClass().add("error-text");
            Button retry = new Button("Intentar de nuevo");
            retry.getStyleClass().add("primary");
            retry.setOnAction(e -> renderPayment(null));
            Button cancel = new Button("Cancelar pedido");
            cancel.setId("checkout-cancel");
            cancel.getStyleClass().add("danger");
            cancel.setOnAction(e -> cancelPedido());
            body.getChildren().setAll(head, card(g), msg, actions(cancel, retry));
        } else {
            Button close = new Button("Cerrar");
            close.setOnAction(e -> stage.close());
            body.getChildren().setAll(head, card(g), muted("Estado reportado por pagos: " + pago.estado()),
                    actions(close));
        }
    }

    private void createEnvio(VBox box) {
        int id = pedido.id();
        loading.run("Generando envio…", () -> ctx.services.envios.crear(id), envio -> renderEnvio(box, envio), err -> {
            Label l = new Label("El pago se aprobo, pero no se pudo generar el envio: " + Alerts.message(err)
                    + "\nPuedes generarlo despues desde Mis compras.");
            l.setWrapText(true);
            l.getStyleClass().add("error-text");
            Button retry = new Button("Reintentar envio");
            retry.setOnAction(e -> createEnvio(box));
            Button compras = new Button("Ir a Mis compras");
            compras.setOnAction(e -> {
                stage.close();
                ctx.nav().goPurchases(id);
            });
            box.getChildren().setAll(l, actions(compras, retry));
        });
    }

    private void renderEnvio(VBox box, Envio envio) {
        Label ok = new Label("✔ ¡Compra confirmada!");
        ok.getStyleClass().add("success-title");
        Label code = new Label(envio.codigo());
        code.setId("checkout-code");
        code.getStyleClass().add("tracking-code");
        Button copy = new Button("Copiar");
        copy.setOnAction(e -> {
            ClipboardContent cc = new ClipboardContent();
            cc.putString(envio.codigo());
            Clipboard.getSystemClipboard().setContent(cc);
            copy.setText("Copiado ✔");
        });
        HBox codeRow = new HBox(10, fieldLabel("Codigo de rastreo"), code, copy);
        codeRow.setAlignment(Pos.CENTER_LEFT);
        Label estado = new Label("Estado del envio: " + envio.estado());
        estado.getStyleClass().add("muted");
        Button track = new Button("Rastrear pedido");
        track.getStyleClass().add("primary");
        track.setOnAction(e -> {
            stage.close();
            ctx.nav().goTracking(envio.codigo());
        });
        Button compras = new Button("Ver mis compras");
        compras.setOnAction(e -> {
            stage.close();
            ctx.nav().goPurchases(envio.pedidoId());
        });
        box.getChildren().setAll(ok, codeRow, estado, actions(compras, track));
    }

    private void cancelPedido() {
        if (!Alerts.confirm("Cancelar pedido #" + pedido.id(),
                "Se cancelara el pedido y se liberaran los libros apartados. ¿Continuar?")) {
            return;
        }
        int id = pedido.id();
        loading.run("Cancelando pedido…", () -> ctx.services.pedidos.cancelar(id), p -> {
            pedido = p;
            Label t = title("Pedido #" + p.id());
            Label estado = Fmt.badge(p.estado());
            estado.setId("checkout-pedido-estado");
            HBox head = new HBox(10, t, estado);
            head.setAlignment(Pos.CENTER_LEFT);
            Button close = new Button("Cerrar");
            close.setOnAction(e -> stage.close());
            body.getChildren().setAll(head, muted("El servicio de pedidos reporta el estado " + p.estado() + "."),
                    actions(close));
        });
    }

    // ------------------------------------------------------------------ piezas

    private VBox pedidoResumen() {
        VBox lines = new VBox(6);
        if (pedido.lineas() != null) {
            for (LineaPedido l : pedido.lineas()) {
                lines.getChildren().add(lineRow(l.titulo() != null ? l.titulo() : l.isbn(),
                        l.cantidad() == null ? 0 : l.cantidad(), l.precioUnitario(), l.subtotal()));
            }
        }
        GridPane g = grid();
        int r = 0;
        r = kv(g, r, "Estado", pedido.estado());
        r = kv(g, r, "Articulos", Fmt.text(pedido.articulos()));
        r = kv(g, r, "Total (servicio)", Fmt.money(pedido.total()));
        if (pedido.expiraEn() != null) {
            kv(g, r, "Apartado hasta", Fmt.date(pedido.expiraEn()));
        }
        return card(new VBox(12, lines, g));
    }

    private static Node lineRow(String titulo, int cantidad, Double precio, Double subtotal) {
        Label t = new Label(titulo);
        t.setWrapText(true);
        Label q = new Label(cantidad + " × " + Fmt.money(precio));
        q.getStyleClass().add("muted");
        Label s = new Label(Fmt.money(subtotal));
        s.getStyleClass().add("strong");
        Region sp = new Region();
        HBox.setHgrow(sp, Priority.ALWAYS);
        HBox row = new HBox(10, t, sp, q, s);
        row.setAlignment(Pos.CENTER_LEFT);
        return row;
    }

    private static RadioButton radio(String text, String value, ToggleGroup g) {
        RadioButton r = new RadioButton(text);
        r.setUserData(value);
        r.setToggleGroup(g);
        return r;
    }

    private static Label title(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("dialog-title");
        return l;
    }

    private static Label section(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("section-title");
        return l;
    }

    private static Label muted(String s) {
        Label l = new Label(s);
        l.setWrapText(true);
        l.getStyleClass().add("muted");
        return l;
    }

    private static Label fieldLabel(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("field-label");
        return l;
    }

    private static VBox card(Node n) {
        VBox v = new VBox(n);
        v.getStyleClass().add("panel");
        return v;
    }

    private static GridPane grid() {
        GridPane g = new GridPane();
        g.setHgap(14);
        g.setVgap(6);
        return g;
    }

    private static int kv(GridPane g, int r, String k, String v) {
        Label lv = new Label(v == null ? "—" : v);
        lv.setWrapText(true);
        g.addRow(r, fieldLabel(k), lv);
        return r + 1;
    }

    private static HBox actions(Node... nodes) {
        Region sp = new Region();
        HBox.setHgrow(sp, Priority.ALWAYS);
        HBox h = new HBox(10);
        h.getChildren().add(sp);
        h.getChildren().addAll(nodes);
        h.setAlignment(Pos.CENTER_RIGHT);
        return h;
    }
}
