package mx.eg4.desktop.ui;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import javafx.beans.property.ReadOnlyObjectWrapper;
import javafx.geometry.Pos;
import javafx.scene.Node;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.Spinner;
import javafx.scene.control.SpinnerValueFactory;
import javafx.scene.control.TableCell;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;

import mx.eg4.desktop.cart.Cart;
import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.model.Book;
import mx.eg4.desktop.ui.util.Alerts;
import mx.eg4.desktop.ui.util.Fmt;
import mx.eg4.desktop.ui.util.LoadingPane;

/** Cesta en memoria. Al confirmar se revalida cada libro con GET /books/&lt;isbn&gt;. */
public final class CartView implements View {

    private final Ctx ctx;
    private final BorderPane root = new BorderPane();
    private final TableView<Cart.Item> table = new TableView<>();
    private final LoadingPane loading;

    public CartView(Ctx ctx) {
        this.ctx = ctx;
        Label title = new Label("Cesta");
        title.getStyleClass().add("view-title");
        HBox header = new HBox(title);
        header.getStyleClass().add("view-header");

        buildTable();
        loading = new LoadingPane(table);

        Label total = new Label();
        total.getStyleClass().add("total");
        total.textProperty().bind(ctx.cart.totalBinding().asString(java.util.Locale.forLanguageTag("es-MX"),
                "Total:  $%,.2f"));
        Button clear = new Button("Vaciar cesta");
        clear.getStyleClass().add("ghost");
        clear.setOnAction(e -> {
            if (Alerts.confirm("Vaciar la cesta", "¿Quitar todos los libros de la cesta?")) {
                ctx.cart.clear();
            }
        });
        Button seguir = new Button("Seguir comprando");
        seguir.setOnAction(e -> ctx.nav().goCatalog());
        Button confirm = new Button("Confirmar compra");
        confirm.getStyleClass().add("primary");
        confirm.setId("cart-confirm");
        table.setId("cart-table");
        confirm.setOnAction(e -> confirm());
        clear.disableProperty().bind(javafx.beans.binding.Bindings.isEmpty(ctx.cart.items()));
        confirm.disableProperty().bind(javafx.beans.binding.Bindings.isEmpty(ctx.cart.items()));
        Region sp = new Region();
        HBox.setHgrow(sp, Priority.ALWAYS);
        HBox footer = new HBox(12, clear, seguir, sp, total, confirm);
        footer.setAlignment(Pos.CENTER_LEFT);
        footer.getStyleClass().add("view-footer");

        root.getStyleClass().add("view");
        root.setTop(header);
        root.setCenter(loading);
        root.setBottom(footer);
    }

    private void buildTable() {
        table.setItems(ctx.cart.items());
        table.setPlaceholder(new Label("Tu cesta esta vacia. Agrega libros desde el catalogo."));
        table.setColumnResizePolicy(TableView.CONSTRAINED_RESIZE_POLICY_FLEX_LAST_COLUMN);

        TableColumn<Cart.Item, String> cTitle = new TableColumn<>("Titulo");
        cTitle.setCellValueFactory(c -> new ReadOnlyObjectWrapper<>(c.getValue().titulo()));
        cTitle.setPrefWidth(380);

        TableColumn<Cart.Item, Number> cPrice = new TableColumn<>("Precio unitario");
        cPrice.setCellValueFactory(c -> c.getValue().precioProperty());
        cPrice.setCellFactory(col -> moneyCell());
        cPrice.setPrefWidth(140);

        TableColumn<Cart.Item, Cart.Item> cQty = new TableColumn<>("Cantidad");
        cQty.setCellValueFactory(c -> new ReadOnlyObjectWrapper<>(c.getValue()));
        cQty.setCellFactory(col -> new TableCell<>() {
            private final Spinner<Integer> spinner = new Spinner<>();

            {
                spinner.setEditable(true);
                spinner.setPrefWidth(100);
            }

            @Override
            protected void updateItem(Cart.Item item, boolean empty) {
                super.updateItem(item, empty);
                if (empty || item == null) {
                    setGraphic(null);
                    return;
                }
                int max = Math.max(item.stockProperty().get(), item.cantidadProperty().get());
                SpinnerValueFactory.IntegerSpinnerValueFactory f =
                        new SpinnerValueFactory.IntegerSpinnerValueFactory(1, Math.max(1, max),
                                item.cantidadProperty().get());
                f.valueProperty().addListener((o, a, b) -> {
                    if (b != null) {
                        item.cantidadProperty().set(b);
                    }
                });
                spinner.setValueFactory(f);
                setGraphic(spinner);
            }
        });
        cQty.setPrefWidth(130);

        TableColumn<Cart.Item, Number> cSub = new TableColumn<>("Subtotal");
        cSub.setCellValueFactory(c -> c.getValue().subtotalBinding());
        cSub.setCellFactory(col -> moneyCell());
        cSub.setPrefWidth(140);

        TableColumn<Cart.Item, Cart.Item> cDel = new TableColumn<>("");
        cDel.setCellValueFactory(c -> new ReadOnlyObjectWrapper<>(c.getValue()));
        cDel.setCellFactory(col -> new TableCell<>() {
            private final Button b = new Button("Eliminar");

            {
                b.getStyleClass().add("danger-link");
            }

            @Override
            protected void updateItem(Cart.Item item, boolean empty) {
                super.updateItem(item, empty);
                if (empty || item == null) {
                    setGraphic(null);
                    return;
                }
                b.setOnAction(e -> ctx.cart.remove(item));
                setGraphic(b);
            }
        });
        cDel.setPrefWidth(110);

        table.getColumns().setAll(List.of(cTitle, cPrice, cQty, cSub, cDel));
    }

    private static TableCell<Cart.Item, Number> moneyCell() {
        return new TableCell<>() {
            @Override
            protected void updateItem(Number v, boolean empty) {
                super.updateItem(v, empty);
                setText(empty || v == null ? null : Fmt.money(v.doubleValue()));
            }
        };
    }

    /** Resultado de revalidar un libro: el libro vigente, o null si ya no existe. */
    private record Check(Cart.Item item, Book book, ApiException error) {
    }

    private void confirm() {
        List<Cart.Item> items = new ArrayList<>(ctx.cart.items());
        loading.run("Verificando precios y existencias…", () -> {
            List<Check> out = new ArrayList<>();
            for (Cart.Item i : items) {
                try {
                    out.add(new Check(i, ctx.services.books.get(i.isbn()), null));
                } catch (ApiException e) {
                    if (e.status() == 404) {
                        out.add(new Check(i, null, e));
                    } else {
                        throw e;
                    }
                }
            }
            return out;
        }, this::applyChecks);
    }

    private void applyChecks(List<Check> checks) {
        Map<String, String> cambios = new LinkedHashMap<>();
        for (Check c : checks) {
            Cart.Item i = c.item();
            if (c.book() == null) {
                cambios.put(i.titulo(), "ya no existe en el catalogo (" + c.error().code() + "); se quito de la cesta");
                ctx.cart.remove(i);
                continue;
            }
            Book b = c.book();
            List<String> partes = new ArrayList<>();
            i.stockProperty().set(b.stockSeguro());
            if (Math.abs(b.precioSeguro() - i.precioProperty().get()) > 0.004) {
                partes.add("precio " + Fmt.money(i.precioProperty().get()) + " → " + Fmt.money(b.precioSeguro()));
                i.precioProperty().set(b.precioSeguro());
            }
            if (b.stockSeguro() <= 0) {
                partes.add("se agoto; se quito de la cesta");
                ctx.cart.remove(i);
            } else if (b.stockSeguro() < i.cantidadProperty().get()) {
                partes.add("solo hay " + b.stockSeguro() + " (pediste " + i.cantidadProperty().get() + ")");
                i.cantidadProperty().set(b.stockSeguro());
            }
            if (!partes.isEmpty()) {
                cambios.put(i.titulo(), String.join("; ", partes));
            }
        }
        table.refresh();
        if (!cambios.isEmpty()) {
            StringBuilder sb = new StringBuilder();
            cambios.forEach((t, c) -> sb.append("• ").append(t).append(": ").append(c).append("\n"));
            sb.append("\nRevisa la cesta y vuelve a confirmar.");
            Alerts.warn("La cesta cambio", sb.toString());
            return;
        }
        new CheckoutDialog(ctx).showForCart();
    }

    @Override
    public void onShow() {
        table.refresh();
    }

    @Override
    public Node node() {
        return root;
    }
}
