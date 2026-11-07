package mx.eg4.desktop.ui;

import javafx.geometry.Pos;
import javafx.scene.Node;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.PasswordField;
import javafx.scene.control.ProgressIndicator;
import javafx.scene.control.TextField;
import javafx.scene.layout.HBox;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;

import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.ui.util.Alerts;
import mx.eg4.desktop.ui.util.Async;

/** Pantalla de inicio de sesion: POST /login?format=json. */
public final class LoginView implements View {

    private final StackPane root = new StackPane();
    private final Ctx ctx;
    private final Runnable onLoggedIn;
    private final TextField email = new TextField();
    private final PasswordField password = new PasswordField();
    private final Button enter = new Button("Iniciar sesion");
    private final Label error = new Label();
    private final ProgressIndicator spinner = new ProgressIndicator();

    public LoginView(Ctx ctx, Runnable onLoggedIn) {
        this.ctx = ctx;
        this.onLoggedIn = onLoggedIn;
        build();
    }

    private void build() {
        root.getStyleClass().add("login-root");
        root.setId("login-root");
        email.setId("login-email");
        password.setId("login-password");
        enter.setId("login-submit");
        error.setId("login-error");

        Label logo = new Label("📚");
        logo.getStyleClass().add("login-logo");
        Label title = new Label("Library");
        title.getStyleClass().add("login-title");
        Label subtitle = new Label("Inicia sesion para ver el catalogo y tus compras");
        subtitle.getStyleClass().add("muted");

        email.setPromptText("correo@ejemplo.com");
        password.setPromptText("Contrasena");
        Label le = new Label("Correo");
        Label lp = new Label("Contrasena");
        le.getStyleClass().add("field-label");
        lp.getStyleClass().add("field-label");

        enter.getStyleClass().add("primary");
        enter.setMaxWidth(Double.MAX_VALUE);
        enter.setDefaultButton(true);
        enter.setOnAction(e -> submit());

        spinner.setMaxSize(22, 22);
        spinner.setVisible(false);

        error.getStyleClass().add("error-text");
        error.setWrapText(true);
        error.setManaged(false);
        error.setVisible(false);

        Label server = new Label("Servidor: " + ctx.config.host());
        server.getStyleClass().add("muted-small");

        HBox actions = new HBox(10, enter, spinner);
        actions.setAlignment(Pos.CENTER_LEFT);
        HBox.setHgrow(enter, javafx.scene.layout.Priority.ALWAYS);

        VBox card = new VBox(10, logo, title, subtitle, le, email, lp, password, error, actions, server);
        card.getStyleClass().add("login-card");
        card.setMaxWidth(400);
        card.setMaxHeight(VBox.USE_PREF_SIZE);
        root.getChildren().add(card);
    }

    private void submit() {
        String mail = email.getText() == null ? "" : email.getText().trim();
        String pass = password.getText() == null ? "" : password.getText();
        if (mail.isEmpty() || pass.isEmpty()) {
            showError("Escribe tu correo y tu contrasena.");
            return;
        }
        setBusy(true);
        Async.run(() -> ctx.services.login.login(mail, pass), r -> {
            setBusy(false);
            password.clear();
            onLoggedIn.run();
        }, err -> {
            setBusy(false);
            ApiException api = Alerts.unwrap(err);
            showError(api != null ? api.userMessage() + "  (" + api.code() + ")" : Alerts.message(err));
        });
    }

    private void setBusy(boolean busy) {
        enter.setDisable(busy);
        email.setDisable(busy);
        password.setDisable(busy);
        spinner.setVisible(busy);
        if (busy) {
            error.setVisible(false);
            error.setManaged(false);
        }
    }

    private void showError(String msg) {
        error.setText(msg);
        error.setVisible(true);
        error.setManaged(true);
    }

    @Override
    public Node node() {
        return root;
    }
}
