package mx.eg4.desktop.ui;

import java.util.List;

import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.Scene;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.ScrollPane;
import javafx.scene.control.Spinner;
import javafx.scene.control.SpinnerValueFactory;
import javafx.scene.image.ImageView;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;
import javafx.stage.Modality;
import javafx.stage.Stage;

import mx.eg4.desktop.model.Author;
import mx.eg4.desktop.model.Book;
import mx.eg4.desktop.ui.util.Alerts;
import mx.eg4.desktop.ui.util.Covers;
import mx.eg4.desktop.ui.util.Fmt;
import mx.eg4.desktop.ui.util.LoadingPane;

/**
 * Detalle de un libro: GET /books/&lt;isbn&gt;?format=json (precio y stock vigentes)
 * + GET /authors/by-book/&lt;isbn&gt; (autores con nacionalidad).
 */
public final class BookDetailDialog {

    private final Ctx ctx;
    private final Book fromList;
    private final Stage stage = new Stage();
    private final ImageView cover;
    private final Label title = new Label();
    private final GridPane info = new GridPane();
    private final Label desc = new Label();
    private final VBox authorsBox = new VBox(4);
    private final Spinner<Integer> qty = new Spinner<>(1, 1, 1);
    private final Button add = new Button("Agregar a la cesta");
    private final Label stockNote = new Label();
    private final Button goCart = new Button("Ir a la cesta");
    private final LoadingPane loading;
    private Book current;

    public BookDetailDialog(Ctx ctx, Book b) {
        this.ctx = ctx;
        this.fromList = b;
        this.current = b;
        cover = Covers.view(b.portadaUrl(), 230, 330);

        title.getStyleClass().add("detail-title");
        title.setWrapText(true);
        desc.setWrapText(true);
        desc.getStyleClass().add("detail-desc");
        info.setHgap(14);
        info.setVgap(6);
        Label autoresTitle = new Label("Autores");
        autoresTitle.getStyleClass().add("section-title");
        Label descTitle = new Label("Descripcion");
        descTitle.getStyleClass().add("section-title");

        qty.setEditable(true);
        qty.setPrefWidth(90);
        add.getStyleClass().add("primary");
        add.setOnAction(e -> addToCart());
        stockNote.getStyleClass().add("muted");
        goCart.setVisible(false);
        goCart.setManaged(false);
        goCart.setOnAction(e -> {
            stage.close();
            ctx.nav().goCart();
        });
        Region spacer = new Region();
        HBox.setHgrow(spacer, Priority.ALWAYS);
        HBox buy = new HBox(10, new Label("Cantidad"), qty, add, stockNote, spacer, goCart);
        buy.setAlignment(Pos.CENTER_LEFT);
        buy.getStyleClass().add("buy-row");

        VBox right = new VBox(12, title, info, autoresTitle, authorsBox, descTitle, desc, buy);
        right.setPadding(new Insets(0, 0, 0, 8));
        HBox.setHgrow(right, Priority.ALWAYS);
        VBox left = new VBox(cover);
        left.getStyleClass().add("cover-box");
        left.setAlignment(Pos.TOP_CENTER);
        left.setMinWidth(250);
        HBox body = new HBox(20, left, right);
        body.setPadding(new Insets(22));
        ScrollPane scroll = new ScrollPane(body);
        scroll.setFitToWidth(true);
        scroll.getStyleClass().add("plain-scroll");
        loading = new LoadingPane(scroll);
        loading.getStyleClass().add("dialog-root");
        loading.setId("book-detail");
        add.setId("detail-add");
        qty.setId("detail-qty");

        Scene scene = new Scene(loading, 820, 560);
        scene.getStylesheets().add(getClass().getResource("/css/app.css").toExternalForm());
        stage.setScene(scene);
        stage.setTitle(b.titulo());
        stage.initOwner(ctx.stage);
        stage.initModality(Modality.WINDOW_MODAL);
        render();
    }

    public void show() {
        stage.show();
        loading.run("Consultando libro…", () -> ctx.services.books.get(fromList.isbn()), b -> {
            current = b;
            render();
        }, err -> {
            add.setDisable(true);
            stockNote.setText("No se pudo consultar el libro: " + Alerts.message(err));
            stockNote.getStyleClass().setAll("error-text");
        });
        authorsBox.getChildren().setAll(muted("Cargando autores…"));
        loading.run("Consultando autores…", () -> ctx.services.authors.byBook(fromList.isbn()), this::renderAuthors,
                err -> authorsBox.getChildren().setAll(error("No se pudieron cargar los autores: " + Alerts.message(err))));
    }

    private void render() {
        Book b = current;
        title.setText(b.titulo());
        info.getChildren().clear();
        int r = 0;
        // GET /books/<isbn> no trae autor ni genero: se usan los de la lista.
        r = row(r, "Autor (catalogo)", fromList.autor());
        r = row(r, "Genero", fromList.genero());
        r = row(r, "Formato", b.formato());
        r = row(r, "Año", b.anio() == null ? null : String.valueOf(b.anio()));
        r = row(r, "ISBN", b.isbn());
        r = row(r, "Precio", Fmt.money(b.precio()));
        r = row(r, "Disponibilidad", b.disponible() ? "Disponible (" + b.stockSeguro() + " en stock)" : "Agotado");
        String d = b.descripcion() != null ? b.descripcion() : fromList.descripcion();
        desc.setText(d == null || d.isBlank() ? "Sin descripcion." : d);

        boolean ok = b.disponible();
        add.setDisable(!ok);
        qty.setValueFactory(new SpinnerValueFactory.IntegerSpinnerValueFactory(1, Math.max(1, b.stockSeguro()), 1));
        var enCesta = ctx.cart.find(b.isbn());
        stockNote.getStyleClass().setAll("muted");
        stockNote.setText(!ok ? "Sin stock" : enCesta != null ? "Ya tienes " + enCesta.cantidadProperty().get()
                + " en la cesta" : "");
    }

    private int row(int r, String k, String v) {
        Label lk = new Label(k);
        lk.getStyleClass().add("field-label");
        Label lv = new Label(v == null || v.isBlank() ? "—" : v);
        lv.setWrapText(true);
        info.addRow(r, lk, lv);
        return r + 1;
    }

    private void renderAuthors(List<Author> authors) {
        if (authors.isEmpty()) {
            authorsBox.getChildren().setAll(muted("authors no tiene autores registrados para este ISBN."));
            return;
        }
        authorsBox.getChildren().clear();
        for (Author a : authors) {
            Label l = new Label("• " + a.nombre() + "  —  " + (a.nacionalidad() == null || a.nacionalidad().isBlank()
                    ? "nacionalidad no registrada" : a.nacionalidad()));
            authorsBox.getChildren().add(l);
        }
    }

    private void addToCart() {
        Integer n = qty.getValue();
        if (n == null || n < 1) {
            return;
        }
        int antes = ctx.cart.find(current.isbn()) == null ? 0 : ctx.cart.find(current.isbn()).cantidadProperty().get();
        int quedo = ctx.cart.add(current, n);
        if (quedo < antes + n) {
            Alerts.warn("Stock limitado", "Solo hay " + current.stockSeguro() + " disponibles. En tu cesta quedaron "
                    + quedo + ".");
        }
        stockNote.setText("✔ En la cesta: " + quedo);
        stockNote.getStyleClass().setAll("ok-text");
        goCart.setVisible(true);
        goCart.setManaged(true);
    }

    private static Label muted(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("muted");
        return l;
    }

    private static Label error(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("error-text");
        l.setWrapText(true);
        return l;
    }
}
