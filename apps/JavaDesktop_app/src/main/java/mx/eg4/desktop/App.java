package mx.eg4.desktop;

import javafx.application.Application;
import javafx.application.Platform;
import javafx.scene.Parent;
import javafx.scene.Scene;
import javafx.stage.Stage;

import mx.eg4.desktop.cart.Cart;
import mx.eg4.desktop.config.AppConfig;
import mx.eg4.desktop.http.ApiClient;
import mx.eg4.desktop.service.Services;
import mx.eg4.desktop.session.Session;
import mx.eg4.desktop.ui.Ctx;
import mx.eg4.desktop.ui.LoginView;
import mx.eg4.desktop.ui.MainView;
import mx.eg4.desktop.ui.util.Alerts;
import mx.eg4.desktop.ui.util.Async;
import mx.eg4.desktop.util.Log;

public class App extends Application {

    private Ctx ctx;
    private Scene scene;
    private MainView main;

    @Override
    public void start(Stage stage) {
        AppConfig cfg = new AppConfig();
        Session session = new Session();
        ApiClient api = new ApiClient(cfg, session);
        ctx = new Ctx(cfg, session, new Services(api), new Cart(), stage);
        api.setOnSessionLost(msg -> Platform.runLater(() -> sessionLost(msg)));

        Log.info("Servidor: " + cfg.host() + " | Java " + System.getProperty("java.version")
                + " | JavaFX " + System.getProperty("javafx.runtime.version"));

        scene = new Scene(new javafx.scene.layout.Pane(), 1320, 840);
        scene.getStylesheets().add(App.class.getResource("/css/app.css").toExternalForm());
        stage.setTitle("Library · Cliente de escritorio");
        stage.setMinWidth(1024);
        stage.setMinHeight(680);
        stage.setScene(scene);
        Alerts.setOwner(stage);
        showLogin();
        stage.show();
    }

    private void showLogin() {
        if (main != null) {
            main.dispose();
            main = null;
        }
        scene.setRoot((Parent) new LoginView(ctx, this::showMain).node());
    }

    private void showMain() {
        main = new MainView(ctx, this::logout);
        scene.setRoot((Parent) main.node());
    }

    /** Cerrar sesion: POST /logout en segundo plano, cierra WebSockets y vuelve al login. */
    private void logout() {
        main.dispose();
        Async.run(() -> {
            ctx.services.login.logout();
            return null;
        }, v -> endSession(), e -> endSession());
    }

    private void endSession() {
        ctx.session.clear();
        ctx.cart.clear();
        showLogin();
    }

    /** 401 sin posibilidad de renovar: avisa y regresa al login. */
    private void sessionLost(String message) {
        if (!ctx.session.isActive()) {
            return;
        }
        endSession();
        Alerts.warn("Sesion terminada", message);
    }

    @Override
    public void stop() {
        if (ctx != null) {
            ctx.session.clear();
        }
        Async.shutdown();
    }
}
