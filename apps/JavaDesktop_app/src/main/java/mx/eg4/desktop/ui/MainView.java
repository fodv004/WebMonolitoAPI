package mx.eg4.desktop.ui;

import java.util.LinkedHashMap;
import java.util.Map;

import javafx.geometry.Pos;
import javafx.scene.Node;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.ProgressIndicator;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;

import mx.eg4.desktop.model.Usuario;
import mx.eg4.desktop.ui.util.Async;

/** Ventana principal: barra superior (usuario, rol, cerrar sesion) y barra lateral de navegacion. */
public final class MainView implements View, Navigator {

    private enum Section { CATALOGO, CESTA, COMPRAS, RASTREO, PERFIL, ADMIN }

    private final Ctx ctx;
    private final BorderPane root = new BorderPane();
    private final StackPane content = new StackPane();
    private final Map<Section, Button> navButtons = new LinkedHashMap<>();
    private final Map<Section, View> views = new LinkedHashMap<>();
    private Section current;

    private final CatalogView catalog;
    private final CartView cart;
    private final PurchasesView purchases;
    private final TrackingView tracking;
    private final ProfileView profile;
    private final AdminView admin;

    public MainView(Ctx ctx, Runnable onLogout) {
        this.ctx = ctx;
        ctx.setNavigator(this);
        catalog = new CatalogView(ctx);
        cart = new CartView(ctx);
        purchases = new PurchasesView(ctx);
        tracking = new TrackingView(ctx);
        profile = new ProfileView(ctx);
        admin = ctx.session.isAdmin() ? new AdminView(ctx) : null;

        views.put(Section.CATALOGO, catalog);
        views.put(Section.CESTA, cart);
        views.put(Section.COMPRAS, purchases);
        views.put(Section.RASTREO, tracking);
        views.put(Section.PERFIL, profile);
        if (admin != null) {
            views.put(Section.ADMIN, admin);
        }

        root.getStyleClass().add("main-root");
        root.setTop(topBar(onLogout));
        root.setLeft(sideBar());
        content.getStyleClass().add("content");
        root.setCenter(content);
        show(Section.CATALOGO);
    }

    private Node topBar(Runnable onLogout) {
        Label brand = new Label("📚  Library");
        brand.getStyleClass().add("brand");

        ProgressIndicator busy = new ProgressIndicator();
        busy.setMaxSize(20, 20);
        busy.visibleProperty().bind(Async.RUNNING.greaterThan(0));
        Label busyText = new Label("Cargando…");
        busyText.getStyleClass().add("muted-small");
        busyText.visibleProperty().bind(busy.visibleProperty());

        Usuario u = ctx.session.user();
        Label name = new Label(u == null ? "" : u.nombreCompleto());
        name.getStyleClass().add("user-name");
        Label role = new Label(ctx.session.role());
        role.getStyleClass().addAll("role-badge", ctx.session.isAdmin() ? "role-admin" : "role-cliente");

        Button logout = new Button("Cerrar sesion");
        logout.getStyleClass().add("ghost");
        logout.setOnAction(e -> {
            logout.setDisable(true);
            onLogout.run();
        });

        Region spacer = new Region();
        HBox.setHgrow(spacer, Priority.ALWAYS);
        HBox bar = new HBox(14, brand, spacer, busy, busyText, name, role, logout);
        bar.setAlignment(Pos.CENTER_LEFT);
        bar.getStyleClass().add("top-bar");
        bar.setId("top-bar");
        logout.setId("logout");
        return bar;
    }

    private Node sideBar() {
        VBox side = new VBox(4);
        side.getStyleClass().add("side-bar");
        addNav(side, Section.CATALOGO, "📖   Catalogo");
        Button cesta = addNav(side, Section.CESTA, "");
        cesta.textProperty().bind(ctx.cart.countBinding().asString("🛒   Cesta (%d)"));
        addNav(side, Section.COMPRAS, "🧾   Mis compras");
        addNav(side, Section.RASTREO, "🚚   Rastrear");
        addNav(side, Section.PERFIL, "👤   Mi perfil");
        if (admin != null) {
            Label sep = new Label("ADMINISTRADOR");
            sep.getStyleClass().add("side-section");
            side.getChildren().add(sep);
            addNav(side, Section.ADMIN, "🛠   Administracion");
        }
        return side;
    }

    private Button addNav(VBox side, Section s, String text) {
        Button b = new Button(text);
        b.setId("nav-" + s.name().toLowerCase(java.util.Locale.ROOT));
        b.getStyleClass().add("nav-button");
        b.setMaxWidth(Double.MAX_VALUE);
        b.setOnAction(e -> show(s));
        navButtons.put(s, b);
        side.getChildren().add(b);
        return b;
    }

    private void show(Section s) {
        if (s == current) {
            return;
        }
        if (current != null) {
            views.get(current).onHide();
            navButtons.get(current).getStyleClass().remove("active");
        }
        current = s;
        navButtons.get(s).getStyleClass().add("active");
        View v = views.get(s);
        content.getChildren().setAll(v.node());
        v.onShow();
    }

    /** Al cerrar sesion: cierra el WebSocket y lo que tenga abierto la pantalla actual. */
    public void dispose() {
        if (current != null) {
            views.get(current).onHide();
        }
        tracking.close();
    }

    @Override
    public void goCatalog() {
        show(Section.CATALOGO);
    }

    @Override
    public void goCart() {
        show(Section.CESTA);
    }

    @Override
    public void goPurchases(Integer pedidoId) {
        purchases.selectOnNextLoad(pedidoId);
        if (current == Section.COMPRAS) {
            purchases.reload();
        } else {
            show(Section.COMPRAS);
        }
    }

    @Override
    public void goTracking(String codigo) {
        if (current == Section.RASTREO) {
            if (codigo != null) {
                tracking.consult(codigo);
            }
        } else {
            tracking.consultOnShow(codigo);
            show(Section.RASTREO);
        }
    }

    @Override
    public Node node() {
        return root;
    }
}
