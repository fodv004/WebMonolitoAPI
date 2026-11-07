package mx.eg4.desktop.ui;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.Cursor;
import javafx.scene.Node;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.ScrollPane;
import javafx.scene.control.TextField;
import javafx.scene.image.ImageView;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.FlowPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;

import mx.eg4.desktop.model.Book;
import mx.eg4.desktop.ui.util.Covers;
import mx.eg4.desktop.ui.util.Fmt;
import mx.eg4.desktop.ui.util.LoadingPane;

/** Catalogo: GET /books?format=json en tarjetas. La busqueda por titulo filtra en la app. */
public final class CatalogView implements View {

    private final Ctx ctx;
    private final BorderPane root = new BorderPane();
    private final FlowPane grid = new FlowPane(18, 18);
    private final TextField search = new TextField();
    private final Label count = new Label();
    private final Label empty = new Label();
    private final LoadingPane loading;
    private List<Book> books = new ArrayList<>();
    private boolean loaded;

    public CatalogView(Ctx ctx) {
        this.ctx = ctx;
        Label title = new Label("Catalogo");
        title.getStyleClass().add("view-title");
        search.setPromptText("🔍  Buscar por titulo…");
        search.setId("catalog-search");
        grid.setId("catalog-grid");
        search.setPrefWidth(320);
        search.textProperty().addListener((o, a, b) -> render());
        Button refresh = new Button("Actualizar");
        refresh.setOnAction(e -> load());
        count.getStyleClass().add("muted");
        Region spacer = new Region();
        HBox.setHgrow(spacer, Priority.ALWAYS);
        HBox header = new HBox(12, title, spacer, count, search, refresh);
        header.setAlignment(Pos.CENTER_LEFT);
        header.getStyleClass().add("view-header");

        grid.setPadding(new Insets(4, 4, 24, 4));
        grid.getStyleClass().add("book-grid");
        empty.getStyleClass().add("muted");
        StackPane holder = new StackPane(grid, empty);
        StackPane.setAlignment(empty, Pos.TOP_CENTER);
        ScrollPane scroll = new ScrollPane(holder);
        scroll.setFitToWidth(true);
        scroll.getStyleClass().add("plain-scroll");
        loading = new LoadingPane(scroll);

        root.setTop(header);
        root.setCenter(loading);
        root.getStyleClass().add("view");
    }

    @Override
    public void onShow() {
        if (!loaded) {
            load();
        }
    }

    private void load() {
        loading.run("Cargando catalogo…", ctx.services.books::list, list -> {
            books = list;
            loaded = true;
            render();
        });
    }

    private void render() {
        String q = normalize(search.getText());
        List<Node> cards = new ArrayList<>();
        for (Book b : books) {
            if (q.isEmpty() || normalize(b.titulo()).contains(q)) {
                cards.add(card(b));
            }
        }
        grid.getChildren().setAll(cards);
        count.setText(cards.size() + " de " + books.size() + " libros");
        empty.setText(loaded && cards.isEmpty() ? (books.isEmpty() ? "El catalogo esta vacio." :
                "Ningun titulo coincide con \"" + search.getText() + "\".") : "");
    }

    private Node card(Book b) {
        ImageView cover = Covers.view(b.portadaUrl(), 160, 220);
        StackPane coverBox = new StackPane(cover);
        coverBox.getStyleClass().add("cover-box");
        coverBox.setPrefSize(176, 230);

        Label title = new Label(b.titulo());
        title.getStyleClass().add("card-title");
        title.setWrapText(true);
        title.setMaxHeight(42);
        Label author = new Label(b.autor() == null || b.autor().isBlank() ? "Autor no indicado" : b.autor());
        author.getStyleClass().add("muted");
        author.setWrapText(true);
        author.setMaxHeight(36);
        Label price = new Label(Fmt.money(b.precio()));
        price.getStyleClass().add("price");
        Label stock = new Label(b.disponible() ? "Disponible · " + b.stockSeguro() : "Agotado");
        stock.getStyleClass().addAll("badge", b.disponible() ? "badge-ok" : "badge-bad");
        Region sp = new Region();
        HBox.setHgrow(sp, Priority.ALWAYS);
        HBox priceRow = new HBox(6, price, sp, stock);
        priceRow.setAlignment(Pos.CENTER_LEFT);
        Label isbn = new Label("ISBN " + b.isbn());
        isbn.getStyleClass().add("muted-small");
        Label desc = new Label(shortText(b.descripcion(), 90));
        desc.getStyleClass().add("card-desc");
        desc.setWrapText(true);
        desc.setMaxHeight(52);

        VBox card = new VBox(6, coverBox, title, author, priceRow, isbn, desc);
        card.getStyleClass().add("book-card");
        card.setPrefWidth(206);
        card.setMaxWidth(206);
        card.setCursor(Cursor.HAND);
        card.setOnMouseClicked(e -> new BookDetailDialog(ctx, b).show());
        return card;
    }

    static String shortText(String s, int max) {
        if (s == null || s.isBlank()) {
            return "Sin descripcion.";
        }
        String t = s.strip().replaceAll("\\s+", " ");
        return t.length() <= max ? t : t.substring(0, max).strip() + "…";
    }

    private static String normalize(String s) {
        if (s == null) {
            return "";
        }
        return Normalizer.normalize(s, Normalizer.Form.NFD).replaceAll("\\p{M}", "")
                .toLowerCase(Locale.ROOT).trim();
    }

    @Override
    public Node node() {
        return root;
    }
}
