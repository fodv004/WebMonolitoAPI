package mx.eg4.desktop.ui;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;

import javafx.beans.property.ReadOnlyObjectWrapper;
import javafx.geometry.Pos;
import javafx.scene.Node;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.TableCell;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.FlowPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;

import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.model.Pedido;
import mx.eg4.desktop.ui.util.Alerts;
import mx.eg4.desktop.ui.util.Fmt;
import mx.eg4.desktop.ui.util.LoadingPane;

/** Administracion (solo admin): todos los pedidos con GET /pedidos sin filtro. */
public final class AdminView implements View {

    private final Ctx ctx;
    private final BorderPane root = new BorderPane();
    private final TableView<Pedido> table = new TableView<>();
    private final FlowPane summary = new FlowPane(10, 8);
    private final Label error = new Label();
    private final LoadingPane loading;

    public AdminView(Ctx ctx) {
        this.ctx = ctx;
        Label title = new Label("Administracion · Todos los pedidos");
        title.getStyleClass().add("view-title");
        Button refresh = new Button("Actualizar");
        refresh.setOnAction(e -> load());
        Region sp = new Region();
        HBox.setHgrow(sp, Priority.ALWAYS);
        HBox header = new HBox(12, title, sp, refresh);
        header.setAlignment(Pos.CENTER_LEFT);
        header.getStyleClass().add("view-header");

        table.setPlaceholder(new Label("No hay pedidos."));
        table.setColumnResizePolicy(TableView.CONSTRAINED_RESIZE_POLICY_FLEX_LAST_COLUMN);
        TableColumn<Pedido, String> cEstado = col("Estado", Pedido::estado, 150);
        cEstado.setCellFactory(c -> new TableCell<>() {
            @Override
            protected void updateItem(String v, boolean empty) {
                super.updateItem(v, empty);
                setText(null);
                setGraphic(empty ? null : Fmt.badge(v));
            }
        });
        table.getColumns().setAll(List.of(
                col("Pedido", p -> "#" + p.id(), 90),
                col("Usuario (user_id)", p -> Fmt.text(p.userId()), 130),
                col("Creado", p -> Fmt.date(p.createdAt()), 150),
                col("Actualizado", p -> Fmt.date(p.updatedAt()), 150),
                col("Articulos", p -> Fmt.text(p.articulos()), 90),
                col("Total", p -> Fmt.money(p.total()), 120),
                cEstado));
        loading = new LoadingPane(table);
        error.getStyleClass().add("error-text");
        error.setWrapText(true);

        VBox center = new VBox(12, summary, error, loading);
        VBox.setVgrow(loading, Priority.ALWAYS);
        root.getStyleClass().add("view");
        root.setTop(header);
        root.setCenter(center);
    }

    private static TableColumn<Pedido, String> col(String name, Function<Pedido, String> f, double w) {
        TableColumn<Pedido, String> c = new TableColumn<>(name);
        c.setCellValueFactory(d -> new ReadOnlyObjectWrapper<>(f.apply(d.getValue())));
        c.setPrefWidth(w);
        return c;
    }

    @Override
    public void onShow() {
        load();
    }

    private void load() {
        error.setText("");
        loading.run("Cargando todos los pedidos…", ctx.services.pedidos::listarTodos, list -> {
            list.sort(Comparator.comparing(Pedido::id).reversed());
            table.getItems().setAll(list);
            Map<String, Integer> porEstado = new TreeMap<>();
            list.forEach(p -> porEstado.merge(p.estado() == null ? "—" : p.estado(), 1, Integer::sum));
            summary.getChildren().clear();
            Label total = new Label(list.size() + " pedidos");
            total.getStyleClass().add("strong");
            summary.getChildren().add(total);
            porEstado.forEach((estado, n) -> {
                Label b = Fmt.badge(estado);
                b.setText(estado + ": " + n);
                summary.getChildren().add(b);
            });
        }, err -> {
            ApiException api = Alerts.unwrap(err);
            if (api != null && api.isSessionEnded()) {
                return;
            }
            error.setText(Alerts.message(err) + (api != null ? " (" + api.code() + ")" : ""));
        });
    }

    @Override
    public Node node() {
        return root;
    }
}
