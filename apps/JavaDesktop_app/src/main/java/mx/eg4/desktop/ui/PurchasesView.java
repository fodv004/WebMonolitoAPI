package mx.eg4.desktop.ui;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import javafx.beans.property.ReadOnlyObjectWrapper;
import javafx.geometry.Pos;
import javafx.scene.Node;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.ScrollPane;
import javafx.scene.control.SplitPane;
import javafx.scene.control.TableCell;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;
import javafx.scene.input.Clipboard;
import javafx.scene.input.ClipboardContent;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;

import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.model.Envio;
import mx.eg4.desktop.model.HistorialPedido;
import mx.eg4.desktop.model.LineaPedido;
import mx.eg4.desktop.model.Pago;
import mx.eg4.desktop.model.Pedido;
import mx.eg4.desktop.ui.util.Alerts;
import mx.eg4.desktop.ui.util.Fmt;
import mx.eg4.desktop.ui.util.LoadingPane;

/**
 * Mis compras: GET /pedidos cruzado con GET /envios (codigo de rastreo).
 * Detalle: GET /pedidos/&lt;id&gt; + GET /pagos/pedido/&lt;id&gt;.
 */
public final class PurchasesView implements View {

    /** Fila de la tabla: pedido + su codigo de rastreo (o null). */
    private record Row(Pedido pedido, String codigo) {
    }

    /** Resultado de cargar la lista. */
    private record ListResult(List<Row> rows, Map<Integer, String> codigos, String warning) {
    }

    /** Detalle de un pedido: pedido completo, pagos (o error de pagos). */
    private record Detail(Pedido pedido, List<Pago> pagos, ApiException pagosError) {
    }

    private final Ctx ctx;
    private final BorderPane root = new BorderPane();
    private final TableView<Row> table = new TableView<>();
    private final VBox detail = new VBox(14);
    private final Label envioWarning = new Label();
    private final LoadingPane listLoading;
    private final LoadingPane detailLoading;
    private Map<Integer, String> codigos = new HashMap<>();
    private Integer pendingSelect;

    public PurchasesView(Ctx ctx) {
        this.ctx = ctx;
        Label title = new Label("Mis compras");
        title.getStyleClass().add("view-title");
        Button refresh = new Button("Actualizar");
        refresh.setOnAction(e -> reload());
        envioWarning.getStyleClass().add("warn-text");
        envioWarning.setWrapText(true);
        Region sp = new Region();
        HBox.setHgrow(sp, Priority.ALWAYS);
        HBox header = new HBox(12, title, sp, envioWarning, refresh);
        header.setAlignment(Pos.CENTER_LEFT);
        header.getStyleClass().add("view-header");

        buildTable();
        table.setId("purchases-table");
        listLoading = new LoadingPane(table);
        detail.getStyleClass().add("detail-pane");
        ScrollPane ds = new ScrollPane(detail);
        ds.setFitToWidth(true);
        ds.getStyleClass().add("plain-scroll");
        detailLoading = new LoadingPane(ds);
        showEmptyDetail();

        SplitPane split = new SplitPane(listLoading, detailLoading);
        split.setDividerPositions(0.52);
        root.getStyleClass().add("view");
        root.setTop(header);
        root.setCenter(split);
    }

    private void buildTable() {
        table.setPlaceholder(new Label("Aun no tienes pedidos."));
        table.setColumnResizePolicy(TableView.CONSTRAINED_RESIZE_POLICY_FLEX_LAST_COLUMN);
        TableColumn<Row, String> cId = col("Pedido", r -> "#" + r.pedido().id(), 80);
        TableColumn<Row, String> cFecha = col("Fecha", r -> Fmt.date(r.pedido().createdAt()), 140);
        TableColumn<Row, String> cArt = col("Articulos", r -> Fmt.text(r.pedido().articulos()), 80);
        TableColumn<Row, String> cTotal = col("Total", r -> Fmt.money(r.pedido().total()), 110);
        TableColumn<Row, String> cEstado = col("Estado", r -> r.pedido().estado(), 140);
        cEstado.setCellFactory(c -> new TableCell<>() {
            @Override
            protected void updateItem(String v, boolean empty) {
                super.updateItem(v, empty);
                setText(null);
                setGraphic(empty ? null : Fmt.badge(v));
            }
        });
        TableColumn<Row, String> cCod = col("Rastreo", r -> r.codigo() == null ? "—" : r.codigo(), 170);
        table.getColumns().setAll(List.of(cId, cFecha, cArt, cTotal, cEstado, cCod));
        table.getSelectionModel().selectedItemProperty().addListener((o, a, r) -> {
            if (r != null) {
                loadDetail(r.pedido().id());
            }
        });
    }

    private static TableColumn<Row, String> col(String name, java.util.function.Function<Row, String> f, double w) {
        TableColumn<Row, String> c = new TableColumn<>(name);
        c.setCellValueFactory(d -> new ReadOnlyObjectWrapper<>(f.apply(d.getValue())));
        c.setPrefWidth(w);
        return c;
    }

    @Override
    public void onShow() {
        reload();
    }

    public void selectOnNextLoad(Integer pedidoId) {
        pendingSelect = pedidoId;
    }

    public void reload() {
        Integer keep = pendingSelect != null ? pendingSelect
                : table.getSelectionModel().getSelectedItem() == null ? null
                : table.getSelectionModel().getSelectedItem().pedido().id();
        pendingSelect = null;
        listLoading.run("Cargando pedidos…", () -> {
            List<Pedido> pedidos = ctx.services.pedidos.listarTodos();
            Map<Integer, String> cods = new HashMap<>();
            String warning = "";
            try {
                for (Envio e : ctx.services.envios.listarTodos()) {
                    cods.put(e.pedidoId(), e.codigo());
                }
            } catch (ApiException e) {
                if (e.isSessionEnded()) {
                    throw e;
                }
                warning = "No se pudieron consultar los envios: " + e.userMessage();
            }
            List<Row> rows = new ArrayList<>();
            pedidos.stream().sorted(Comparator.comparing(Pedido::id).reversed())
                    .forEach(p -> rows.add(new Row(p, cods.get(p.id()))));
            return new ListResult(rows, cods, warning);
        }, res -> {
            List<Row> rows = res.rows();
            codigos = res.codigos();
            envioWarning.setText(res.warning());
            table.getItems().setAll(rows);
            if (keep != null) {
                rows.stream().filter(r -> r.pedido().id().equals(keep)).findFirst().ifPresentOrElse(r -> {
                    table.getSelectionModel().select(r);
                    table.scrollTo(r);
                }, this::showEmptyDetail);
            } else {
                showEmptyDetail();
            }
        });
    }

    private void showEmptyDetail() {
        Label l = new Label("Selecciona un pedido para ver su detalle.");
        l.getStyleClass().add("muted");
        detail.getChildren().setAll(l);
    }

    private void loadDetail(int id) {
        detailLoading.run("Cargando pedido #" + id + "…", () -> {
            Pedido p = ctx.services.pedidos.obtener(id);
            try {
                return new Detail(p, ctx.services.pagos.porPedido(id), null);
            } catch (ApiException e) {
                if (e.isSessionEnded()) {
                    throw e;
                }
                return new Detail(p, List.of(), e);
            }
        }, this::renderDetail, err -> {
            Label l = new Label("No se pudo cargar el pedido: " + Alerts.message(err));
            l.getStyleClass().add("error-text");
            l.setWrapText(true);
            detail.getChildren().setAll(l);
            Alerts.error(err);
        });
    }

    private void renderDetail(Detail d) {
        Pedido p = d.pedido();
        String codigo = codigos.get(p.id());
        Label t = new Label("Pedido #" + p.id());
        t.getStyleClass().add("dialog-title");
        HBox head = new HBox(10, t, Fmt.badge(p.estado()));
        head.setAlignment(Pos.CENTER_LEFT);

        GridPane g = new GridPane();
        g.setHgap(14);
        g.setVgap(6);
        int r = 0;
        r = kv(g, r, "Creado", Fmt.date(p.createdAt()));
        r = kv(g, r, "Actualizado", Fmt.date(p.updatedAt()));
        r = kv(g, r, "Articulos", Fmt.text(p.articulos()));
        r = kv(g, r, "Total", Fmt.money(p.total()));
        if ("PENDIENTE_PAGO".equals(p.estado()) && p.expiraEn() != null) {
            kv(g, r, "Apartado hasta", Fmt.date(p.expiraEn()));
        }

        // Lineas
        GridPane lineas = new GridPane();
        lineas.setHgap(16);
        lineas.setVgap(6);
        lineas.getStyleClass().add("lines-grid");
        lineas.addRow(0, hdr("Titulo"), hdr("Cant."), hdr("Precio"), hdr("Subtotal"));
        int i = 1;
        if (p.lineas() != null) {
            for (LineaPedido l : p.lineas()) {
                Label lt = new Label(l.titulo() != null ? l.titulo() : l.isbn());
                lt.setWrapText(true);
                lt.setMaxWidth(260);
                lineas.addRow(i++, lt, new Label(Fmt.text(l.cantidad())), new Label(Fmt.money(l.precioUnitario())),
                        new Label(Fmt.money(l.subtotal())));
            }
        }

        // Historial
        VBox hist = new VBox(4);
        if (p.historial() == null || p.historial().isEmpty()) {
            hist.getChildren().add(muted("Sin historial."));
        } else {
            for (HistorialPedido h : p.historial()) {
                hist.getChildren().add(new Label(Fmt.date(h.fecha()) + "   "
                        + (h.estadoAnterior() == null ? "—" : h.estadoAnterior()) + " → " + h.estadoNuevo()
                        + (h.actor() == null ? "" : "   (" + h.actor() + ")")));
            }
        }

        // Pagos
        VBox pagos = new VBox(8);
        if (d.pagosError() != null) {
            pagos.getChildren().add(errorLabel("No se pudieron consultar los pagos: " + d.pagosError().userMessage()));
        } else if (d.pagos().isEmpty()) {
            pagos.getChildren().add(muted("Este pedido no tiene pagos registrados."));
        } else {
            for (Pago pg : d.pagos()) {
                HBox row = new HBox(10, Fmt.badge(pg.estado()), new Label(pg.metodo()
                        + (pg.ultimos4() != null ? " ···· " + pg.ultimos4() : "")),
                        new Label(Fmt.money(pg.monto())), muted("Ref. " + Fmt.text(pg.referencia())),
                        muted(Fmt.date(pg.createdAt())));
                row.setAlignment(Pos.CENTER_LEFT);
                pagos.getChildren().add(row);
            }
        }

        // Envio y acciones
        VBox envio = new VBox(10);
        HBox acciones = new HBox(10);
        acciones.setAlignment(Pos.CENTER_LEFT);
        if (codigo != null) {
            Label c = new Label(codigo);
            c.getStyleClass().add("tracking-code");
            Button copy = new Button("Copiar");
            copy.setOnAction(e -> {
                ClipboardContent cc = new ClipboardContent();
                cc.putString(codigo);
                Clipboard.getSystemClipboard().setContent(cc);
                copy.setText("Copiado ✔");
            });
            Button track = new Button("Rastrear");
            track.setId("purchases-track");
            track.getStyleClass().add("primary");
            track.setOnAction(e -> ctx.nav().goTracking(codigo));
            HBox cr = new HBox(10, c, copy, track);
            cr.setAlignment(Pos.CENTER_LEFT);
            envio.getChildren().add(cr);
        } else if ("PAGADO".equals(p.estado())) {
            envio.getChildren().add(muted("El pedido esta pagado pero aun no tiene envio."));
            Button gen = new Button("Generar envio");
            gen.getStyleClass().add("primary");
            gen.setOnAction(e -> generarEnvio(p.id()));
            acciones.getChildren().add(gen);
        } else {
            envio.getChildren().add(muted("Sin envio."));
        }
        if ("PENDIENTE_PAGO".equals(p.estado())) {
            Button pay = new Button("Pagar");
            pay.getStyleClass().add("primary");
            pay.setOnAction(e -> new CheckoutDialog(ctx).onClose(this::reload).showForPedido(p));
            Button cancel = new Button("Cancelar pedido");
            cancel.getStyleClass().add("danger");
            cancel.setOnAction(e -> cancelar(p.id()));
            acciones.getChildren().addAll(pay, cancel);
        }

        detail.getChildren().setAll(head, panel(g), section("Libros"), panel(lineas), section("Historial"),
                panel(hist), section("Pagos"), panel(pagos), section("Envio"), panel(envio), acciones);
    }

    private void generarEnvio(int pedidoId) {
        detailLoading.run("Generando envio…", () -> ctx.services.envios.crear(pedidoId), e -> {
            Alerts.info("Envio generado", "Codigo de rastreo: " + e.codigo() + "\nEstado: " + e.estado());
            pendingSelect = pedidoId;
            reload();
        });
    }

    private void cancelar(int pedidoId) {
        if (!Alerts.confirm("Cancelar pedido #" + pedidoId, "Se liberaran los libros apartados. ¿Continuar?")) {
            return;
        }
        detailLoading.run("Cancelando…", () -> ctx.services.pedidos.cancelar(pedidoId), p -> {
            pendingSelect = pedidoId;
            reload();
        });
    }

    private static int kv(GridPane g, int r, String k, String v) {
        Label lk = new Label(k);
        lk.getStyleClass().add("field-label");
        g.addRow(r, lk, new Label(v == null ? "—" : v));
        return r + 1;
    }

    private static Label hdr(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("field-label");
        return l;
    }

    private static Label section(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("section-title");
        return l;
    }

    private static Label muted(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("muted");
        l.setWrapText(true);
        return l;
    }

    private static Label errorLabel(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("error-text");
        l.setWrapText(true);
        return l;
    }

    private static VBox panel(Node n) {
        VBox v = new VBox(n);
        v.getStyleClass().add("panel");
        return v;
    }

    @Override
    public Node node() {
        return root;
    }
}
