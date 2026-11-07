package mx.eg4.desktop.ui;

import javafx.geometry.Pos;
import javafx.scene.Node;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.ScrollPane;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;

import mx.eg4.desktop.config.AppConfig.Service;
import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.model.ProgresoSoap;
import mx.eg4.desktop.model.Usuario;
import mx.eg4.desktop.ui.util.Alerts;
import mx.eg4.desktop.ui.util.Fmt;
import mx.eg4.desktop.ui.util.LoadingPane;

/** Mi perfil: GET /users/me + "Progreso de clasificacion (SOAP)" (ObtenerProgresoUsuario). */
public final class ProfileView implements View {

    private final Ctx ctx;
    private final BorderPane root = new BorderPane();
    private final GridPane info = new GridPane();
    private final Label userError = new Label();
    private final Label sCorreo = new Label("—");
    private final Label sClasificados = new Label("—");
    private final Label sPendientes = new Label("—");
    private final Label soapError = new Label();
    private final LoadingPane userLoading;
    private final LoadingPane soapLoading;

    public ProfileView(Ctx ctx) {
        this.ctx = ctx;
        Label title = new Label("Mi perfil");
        title.getStyleClass().add("view-title");
        Button refresh = new Button("Actualizar");
        refresh.setOnAction(e -> load());
        Region sp = new Region();
        HBox.setHgrow(sp, Priority.ALWAYS);
        HBox header = new HBox(12, title, sp, refresh);
        header.setAlignment(Pos.CENTER_LEFT);
        header.getStyleClass().add("view-header");

        info.setHgap(18);
        info.setVgap(8);
        userError.getStyleClass().add("error-text");
        userError.setWrapText(true);
        Label userTitle = new Label("Datos de la cuenta (GET /users/me)");
        userTitle.getStyleClass().add("section-title");
        VBox userPanel = new VBox(12, userTitle, info, userError);
        userPanel.getStyleClass().add("panel");
        userLoading = new LoadingPane(userPanel);

        Label soapTitle = new Label("Progreso de clasificacion (SOAP)");
        soapTitle.getStyleClass().add("section-title");
        Label soapInfo = new Label("POST " + ctx.config.baseUrl(Service.BOOKS) + "/soap · operacion "
                + "ObtenerProgresoUsuario (SOAP 1.1) con tu correo como correoClasificador.");
        soapInfo.getStyleClass().add("muted-small");
        soapInfo.setWrapText(true);
        GridPane sg = new GridPane();
        sg.setHgap(18);
        sg.setVgap(8);
        sg.addRow(0, key("correo"), sCorreo);
        sg.addRow(1, key("totalClasificados"), sClasificados);
        sg.addRow(2, key("totalPendientes"), sPendientes);
        sClasificados.getStyleClass().add("big-number");
        sClasificados.setId("soap-clasificados");
        sPendientes.getStyleClass().add("big-number");
        soapError.getStyleClass().add("error-text");
        soapError.setWrapText(true);
        Button soapBtn = new Button("Consultar por SOAP");
        soapBtn.setOnAction(e -> loadSoap());
        VBox soapPanel = new VBox(12, soapTitle, soapInfo, sg, soapError, soapBtn);
        soapPanel.getStyleClass().add("panel");
        soapLoading = new LoadingPane(soapPanel);

        VBox content = new VBox(18, userLoading, soapLoading);
        content.setMaxWidth(760);
        ScrollPane sc = new ScrollPane(content);
        sc.setFitToWidth(true);
        sc.getStyleClass().add("plain-scroll");
        root.getStyleClass().add("view");
        root.setTop(header);
        root.setCenter(sc);
    }

    @Override
    public void onShow() {
        load();
    }

    private void load() {
        userError.setText("");
        userLoading.run("Consultando perfil…", ctx.services.users::me, this::renderUser, err -> {
            ApiException api = Alerts.unwrap(err);
            if (api != null && api.isSessionEnded()) {
                return;
            }
            userError.setText("No se pudo cargar el perfil: " + Alerts.message(err)
                    + (api != null ? " (" + api.code() + ")" : ""));
        });
        loadSoap();
    }

    private void renderUser(Usuario u) {
        info.getChildren().clear();
        int r = 0;
        r = row(r, "Nombre", u.nombreCompleto());
        r = row(r, "Correo", u.email());
        r = row(r, "Rol", u.role() + (u.roleId() == null ? "" : " (role_id " + u.roleId() + ")"));
        r = row(r, "Id de usuario", Fmt.text(u.idUsuario()));
        r = row(r, "Cuenta activa", yesNo(u.activo()));
        r = row(r, "Correo verificado", yesNo(u.emailVerificado()));
        r = row(r, "Creada", Fmt.date(u.createdAt()));
        row(r, "Actualizada", Fmt.date(u.updatedAt()));
    }

    private void loadSoap() {
        String correo = ctx.session.email();
        soapError.setText("");
        if (correo == null) {
            return;
        }
        soapLoading.run("Consultando SOAP…", () -> ctx.services.soap.progresoUsuario(correo), this::renderSoap,
                err -> {
                    ApiException api = Alerts.unwrap(err);
                    sCorreo.setText(correo);
                    sClasificados.setText("—");
                    sPendientes.setText("—");
                    soapError.setText(Alerts.message(err) + (api != null ? " (" + api.code() + ")" : ""));
                });
    }

    private void renderSoap(ProgresoSoap p) {
        sCorreo.setText(Fmt.text(p.correo()));
        sClasificados.setText(String.valueOf(p.totalClasificados()));
        sPendientes.setText(String.valueOf(p.totalPendientes()));
    }

    private int row(int r, String k, String v) {
        Label lv = new Label(v == null ? "—" : v);
        lv.setWrapText(true);
        info.addRow(r, key(k), lv);
        return r + 1;
    }

    private static String yesNo(Boolean b) {
        return b == null ? "—" : b ? "Si" : "No";
    }

    private static Label key(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("field-label");
        return l;
    }

    @Override
    public Node node() {
        return root;
    }
}
