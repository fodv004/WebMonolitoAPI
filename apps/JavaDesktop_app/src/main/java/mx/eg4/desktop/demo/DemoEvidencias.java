package mx.eg4.desktop.demo;

import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

import javax.imageio.ImageIO;

import javafx.application.Application;
import javafx.application.Platform;
import javafx.scene.Node;
import javafx.scene.Parent;
import javafx.scene.Scene;
import javafx.scene.control.Button;
import javafx.scene.control.ButtonType;
import javafx.scene.control.DialogPane;
import javafx.scene.control.Label;
import javafx.scene.control.ProgressBar;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;
import javafx.scene.control.TextField;
import javafx.scene.control.TextInputControl;
import javafx.scene.image.PixelReader;
import javafx.scene.image.WritableImage;
import javafx.scene.layout.Pane;
import javafx.scene.web.WebView;
import javafx.stage.Stage;
import javafx.stage.Window;

import mx.eg4.desktop.App;
import mx.eg4.desktop.ui.util.Async;
import mx.eg4.desktop.ui.util.Covers;
import mx.eg4.desktop.util.Log;

/**
 * Modo de demostracion: recorre la interfaz real de la app (llena campos y pulsa botones,
 * igual que un usuario) y guarda una captura PNG en cada paso, en
 * &lt;raiz del repo&gt;/Evidencias_DD_MM_AAAA/.
 *
 * Credenciales: variables de entorno DEMO_EMAIL / DEMO_PASSWORD (y opcional DEMO_EMAIL_2 /
 * DEMO_PASSWORD_2). Nunca se escriben en archivos ni en el log.
 *
 * Se ejecuta con: mvnw javafx:run -Pdemo
 */
public final class DemoEvidencias extends App {

    private static final DateTimeFormatter CARPETA = DateTimeFormatter.ofPattern("dd_MM_yyyy");
    private static final long POLL_MS = 300;

    private Stage stage;
    private Path outDir;
    private String paso = "inicio";
    private final List<String> guardadas = new ArrayList<>();
    private final List<String> omitidas = new ArrayList<>();

    public static void main(String[] args) {
        Application.launch(DemoEvidencias.class, args);
    }

    @Override
    public void start(Stage st) {
        String email = System.getenv("DEMO_EMAIL");
        String pass = System.getenv("DEMO_PASSWORD");
        if (isBlank(email) || isBlank(pass)) {
            Log.warn("[DEMO] Faltan las variables de entorno DEMO_EMAIL y DEMO_PASSWORD. No se ejecuta el demo.");
            Platform.exit();
            return;
        }
        super.start(st);
        stage = st;
        stage.setTitle("Library · Cliente de escritorio (modo demostracion)");
        Thread t = new Thread(this::run, "demo-evidencias");
        t.setDaemon(true);
        t.start();
    }

    // ================================================================== flujo

    private void run() {
        boolean ok = false;
        try {
            outDir = carpetaEvidencias();
            Files.createDirectories(outDir);
            Log.info("[DEMO] Capturas en " + outDir);
            Log.info("[DEMO] Usuario principal: DEMO_EMAIL definido. Segundo usuario: "
                    + (isBlank(System.getenv("DEMO_EMAIL_2")) ? "no" : "si"));
            flujo();
            ok = true;
        } catch (Exception e) {
            Log.warn("[DEMO] Detenido en el paso " + paso + ": " + e.getMessage());
            try {
                captura("ERROR_" + paso, ventanaActiva());
            } catch (Exception ignored) {
                // sin captura de error
            }
        } finally {
            Log.info("[DEMO] Capturas guardadas (" + guardadas.size() + "): " + String.join(", ", guardadas));
            if (!omitidas.isEmpty()) {
                Log.warn("[DEMO] Omitidas: " + String.join("; ", omitidas));
            }
        }
        if (ok) {
            Log.info("[DEMO] Terminado. Cerrando la app.");
            dormir(1500);
            Platform.runLater(Platform::exit);
        } else {
            Log.warn("[DEMO] La ventana queda abierta para revisar el error.");
        }
    }

    private void flujo() throws Exception {
        // ---------------------------------------------------------- 01 login
        paso = "01_login";
        esperar("pantalla de login", () -> nodo("login-root") != null, 30);
        escribirLogin(System.getenv("DEMO_EMAIL"), System.getenv("DEMO_PASSWORD"));
        esperarCarga();
        captura("01_login", stage);
        entrar();

        // ---------------------------------------------------------- 02 barra / 03 catalogo
        paso = "02_barra_usuario";
        esperarCarga();
        capturaNodo("02_barra_usuario", "top-bar");
        paso = "03_catalogo";
        captura("03_catalogo", stage);

        // ---------------------------------------------------------- 04 busqueda
        paso = "04_busqueda";
        String titulo = fx(() -> tituloDisponible(null));
        if (titulo == null) {
            throw new IllegalStateException("No hay libros con stock en el catalogo.");
        }
        String termino = terminoBusqueda(titulo);
        fx(() -> {
            ((TextField) nodo("catalog-search")).setText(termino);
            return null;
        });
        esperarCarga();
        captura("04_busqueda", stage);

        // ---------------------------------------------------------- 05 detalle
        paso = "05_detalle_libro";
        abrirLibro(titulo);
        Window detalle = ventanaCon("book-detail");
        captura("05_detalle_libro", detalle);
        agregarALaCesta(detalle);

        // ---------------------------------------------------------- 06 cesta
        paso = "06_cesta";
        pulsar("nav-cesta");
        esperarCarga();
        captura("06_cesta", stage);

        // ---------------------------------------------------------- 07 pago aprobado
        paso = "07_pago_aprobado_codigo";
        Window checkout = confirmarCesta();
        crearPedidoYPagar(checkout, "4111111111111111");
        esperar("pago aprobado y codigo de rastreo", () -> {
            Label est = (Label) lookupEn(checkout, "checkout-pago-estado");
            if (est != null && !"APROBADO".equals(est.getText())) {
                throw new IllegalStateException("El pago quedo " + est.getText() + " (se esperaba APROBADO).");
            }
            return lookupEn(checkout, "checkout-code") != null;
        }, 90);
        esperarCarga();
        String codigo = fx(() -> ((Label) lookupEn(checkout, "checkout-code")).getText());
        Log.info("[DEMO] Codigo de rastreo: " + codigo);
        captura("07_pago_aprobado_codigo", checkout);
        cerrar(checkout);
        int pedidoId = pedidoDeCodigo(codigo);

        // ---------------------------------------------------------- 08 pago rechazado
        paso = "08_pago_rechazado";
        pulsar("nav-catalogo");
        fx(() -> {
            ((TextField) nodo("catalog-search")).setText("");
            return null;
        });
        esperarCarga();
        String titulo2 = fx(() -> tituloDisponible(titulo));
        abrirLibro(titulo2 != null ? titulo2 : titulo);
        agregarALaCesta(ventanaCon("book-detail"));
        pulsar("nav-cesta");
        esperarCarga();
        Window checkout2 = confirmarCesta();
        crearPedidoYPagar(checkout2, "4111111111110000");
        esperar("pago rechazado", () -> {
            Label est = (Label) lookupEn(checkout2, "checkout-pago-estado");
            return est != null && "RECHAZADO".equals(est.getText());
        }, 90);
        esperarCarga();
        captura("08_pago_rechazado", checkout2);
        // Cancelar ese pedido para liberar el libro (pide confirmacion).
        pulsarEn(checkout2, "checkout-cancel");
        aceptarAlerta("confirmar cancelacion", 15);
        esperar("pedido cancelado", () -> lookupEn(checkout2, "checkout-pedido-estado") != null, 60);
        esperarCarga();
        cerrar(checkout2);

        // ---------------------------------------------------------- 09 mis compras
        paso = "09_mis_compras_detalle";
        pulsar("nav-compras");
        esperarCarga();
        fx(() -> {
            seleccionarPedido(pedidoId);
            return null;
        });
        esperar("detalle del pedido", () -> nodo("purchases-track") != null, 60);
        esperarCarga();
        captura("09_mis_compras_detalle", stage);

        // ---------------------------------------------------------- 10 rastreo inicio
        paso = "10_rastreo_inicio";
        pulsar("purchases-track");
        esperar("datos del envio", () -> !"—".equals(texto("tracking-estado")), 60);
        esperarCarga();
        esperarTiles();
        captura("10_rastreo_inicio", stage);

        // ---------------------------------------------------------- 11 en ruta 40-60 %
        paso = "11_rastreo_en_ruta";
        Log.info("[DEMO] Esperando a que el envio llegue a 40-60 % (lo mueve el simulador GPS de la VM)…");
        double[] prog = {0};
        esperar("progreso de 40 % o mas", () -> {
            prog[0] = ((ProgressBar) nodo("tracking-progress")).getProgress();
            return prog[0] >= 0.40 || "ENTREGADO".equals(texto("tracking-estado"));
        }, 600);
        if (prog[0] <= 0.60 && !"ENTREGADO".equals(fx(() -> texto("tracking-estado")))) {
            esperarTiles();
            captura("11_rastreo_en_ruta", stage);
        } else {
            omitidas.add("11_rastreo_en_ruta: el progreso salto a " + Math.round(prog[0] * 100) + " % sin pasar por 40-60 %");
        }

        // ---------------------------------------------------------- 12 entregado
        paso = "12_rastreo_entregado";
        esperar("estado ENTREGADO", () -> "ENTREGADO".equals(texto("tracking-estado")), 720);
        esperar("aviso de entrega", () -> alerta() != null, 15);
        esperarTiles();
        captura("12_rastreo_entregado", stage);
        aceptarAlerta("aviso de entrega", 5);

        // ---------------------------------------------------------- 13 perfil + SOAP
        paso = "13_perfil_soap";
        pulsar("nav-perfil");
        esperar("respuesta SOAP", () -> !"—".equals(texto("soap-clasificados")), 60);
        esperarCarga();
        captura("13_perfil_soap", stage);

        // ---------------------------------------------------------- 14 pedido ajeno
        String email2 = System.getenv("DEMO_EMAIL_2");
        String pass2 = System.getenv("DEMO_PASSWORD_2");
        if (!isBlank(email2) && !isBlank(pass2)) {
            paso = "14_pedido_ajeno";
            cerrarSesion();
            escribirLogin(email2, pass2);
            entrar();
            esperarCarga();
            pulsar("nav-rastreo");
            fx(() -> {
                ((TextField) nodo("tracking-code")).setText(codigo);
                return null;
            });
            pulsar("tracking-consult");
            esperar("mensaje del rastreo", () -> nodo("tracking-banner").isVisible(), 60);
            esperarCarga();
            String banner = fx(() -> texto("tracking-banner"));
            if (!fx(() -> nodo("tracking-banner").getStyleClass().contains("banner-error"))) {
                Log.warn("[DEMO] El segundo usuario SI pudo ver el envio (¿es admin?). Mensaje: " + banner);
            }
            captura("14_pedido_ajeno", stage);
        } else {
            omitidas.add("14_pedido_ajeno: no se definieron DEMO_EMAIL_2 / DEMO_PASSWORD_2");
        }

        // ---------------------------------------------------------- 15 logout
        paso = "15_logout";
        cerrarSesion();
        esperarCarga();
        captura("15_logout", stage);
    }

    // ================================================================== acciones de UI

    private void escribirLogin(String email, String pass) throws Exception {
        fx(() -> {
            ((TextInputControl) nodo("login-email")).setText(email);
            ((TextInputControl) nodo("login-password")).setText(pass);
            return null;
        });
    }

    private void entrar() throws Exception {
        pulsar("login-submit");
        esperar("inicio de sesion", () -> {
            Node err = nodo("login-error");
            if (err != null && err.isVisible()) {
                throw new IllegalStateException("Login rechazado: " + ((Label) err).getText());
            }
            return nodo("top-bar") != null;
        }, 60);
    }

    private void cerrarSesion() throws Exception {
        pulsar("logout");
        esperar("pantalla de login", () -> nodo("login-root") != null, 60);
    }

    /** Titulo de la primera tarjeta con stock (distinta de 'excepto'), o null. Hilo FX. */
    private String tituloDisponible(String excepto) {
        Pane grid = (Pane) nodo("catalog-grid");
        for (Node card : grid.getChildren()) {
            if (card.lookup(".badge-ok") != null) {
                String t = ((Label) card.lookup(".card-title")).getText();
                if (excepto == null || !excepto.equals(t)) {
                    return t;
                }
            }
        }
        return null;
    }

    private static String terminoBusqueda(String titulo) {
        for (String w : titulo.split("\\s+")) {
            if (w.replaceAll("[^\\p{L}]", "").length() >= 4) {
                return w.replaceAll("[^\\p{L}\\p{N}]", "");
            }
        }
        return titulo;
    }

    private void abrirLibro(String titulo) throws Exception {
        fx(() -> {
            Pane grid = (Pane) nodo("catalog-grid");
            for (Node card : grid.getChildren()) {
                if (titulo.equals(((Label) card.lookup(".card-title")).getText())) {
                    card.getOnMouseClicked().handle(null);
                    return null;
                }
            }
            throw new IllegalStateException("No se encontro la tarjeta de \"" + titulo + "\"");
        });
        esperar("detalle del libro", () -> ventanaConFx("book-detail") != null, 15);
        esperarCarga();
    }

    private void agregarALaCesta(Window detalle) throws Exception {
        String antes = fx(() -> ((Button) nodo("nav-cesta")).getText());
        pulsarEn(detalle, "detail-add");
        esperar("libro en la cesta", () -> !antes.equals(((Button) nodo("nav-cesta")).getText()), 15);
        cerrar(detalle);
    }

    /** Pulsa Confirmar compra; si la cesta cambio (precio/stock) acepta el aviso y confirma otra vez. */
    private Window confirmarCesta() throws Exception {
        for (int intento = 0; intento < 2; intento++) {
            pulsar("cart-confirm");
            esperar("verificacion de la cesta", () -> ventanaConFx("checkout") != null || alerta() != null, 60);
            Window w = fx(() -> ventanaConFx("checkout"));
            if (w != null) {
                esperarCarga();
                return w;
            }
            Log.warn("[DEMO] La cesta cambio al verificarla; se acepta el aviso y se confirma de nuevo.");
            aceptarAlerta("aviso de cesta", 5);
            esperarCarga();
        }
        throw new IllegalStateException("No se pudo confirmar la cesta.");
    }

    private void crearPedidoYPagar(Window checkout, String tarjeta) throws Exception {
        pulsarEn(checkout, "checkout-create");
        esperar("formulario de pago", () -> lookupEn(checkout, "checkout-pay") != null, 60);
        esperarCarga();
        fx(() -> {
            ((TextField) lookupEn(checkout, "checkout-card")).setText(tarjeta);
            return null;
        });
        pulsarEn(checkout, "checkout-pay");
    }

    @SuppressWarnings("unchecked")
    private void seleccionarPedido(int pedidoId) {
        TableView<Object> t = (TableView<Object>) nodo("purchases-table");
        TableColumn<Object, ?> col = t.getColumns().get(0);
        for (int i = 0; i < t.getItems().size(); i++) {
            if (("#" + pedidoId).equals(String.valueOf(col.getCellData(i)))) {
                t.getSelectionModel().select(i);
                t.scrollTo(i);
                return;
            }
        }
        throw new IllegalStateException("El pedido #" + pedidoId + " no aparece en Mis compras.");
    }

    private static int pedidoDeCodigo(String codigo) {
        // LIB-MTY-<año>-<pedido_id con 6 digitos> (tracking/services/envios_service.py)
        String[] p = codigo.split("-");
        return Integer.parseInt(p[p.length - 1]);
    }

    private void pulsar(String id) throws Exception {
        Button b = fx(() -> (Button) nodo(id));
        if (b == null) {
            throw new IllegalStateException("No se encontro el boton #" + id);
        }
        Platform.runLater(b::fire);       // sin esperar: el boton puede abrir un dialogo modal
        dormir(250);
    }

    private void pulsarEn(Window w, String id) throws Exception {
        Button b = fx(() -> (Button) lookupEn(w, id));
        if (b == null) {
            throw new IllegalStateException("No se encontro el boton #" + id);
        }
        Platform.runLater(b::fire);
        dormir(250);
    }

    private void cerrar(Window w) throws Exception {
        fx(() -> {
            w.hide();
            return null;
        });
        dormir(300);
    }

    // ================================================================== alertas

    /** Alert de JavaFX abierto (DialogPane como raiz), o null. Hilo FX. */
    private static Stage alerta() {
        for (Window w : Window.getWindows()) {
            if (w.isShowing() && w instanceof Stage s && s.getScene() != null
                    && s.getScene().getRoot() instanceof DialogPane) {
                return s;
            }
        }
        return null;
    }

    private void aceptarAlerta(String desc, int segundos) throws Exception {
        esperar(desc, () -> alerta() != null, segundos);
        fx(() -> {
            DialogPane dp = (DialogPane) alerta().getScene().getRoot();
            Node ok = dp.lookupButton(ButtonType.OK);
            Platform.runLater(((Button) ok)::fire);
            return null;
        });
        esperar("cerrar " + desc, () -> alerta() == null, 10);
    }

    /** Un error inesperado de la app detiene el demo. Hilo FX. */
    private static void revisarErrores() {
        Stage a = alerta();
        if (a == null) {
            return;
        }
        DialogPane dp = (DialogPane) a.getScene().getRoot();
        String header = dp.getHeaderText() == null ? "" : dp.getHeaderText();
        if ("Error".equals(a.getTitle()) || header.startsWith("Sesion terminada")) {
            String detalle = dp.getContent() instanceof Label l ? l.getText() : "";
            throw new IllegalStateException("La app mostro un error: " + header + " — " + detalle);
        }
    }

    // ================================================================== esperas

    private void esperar(String desc, Callable<Boolean> cond, int segundos) throws Exception {
        long limite = System.currentTimeMillis() + segundos * 1000L;
        while (true) {
            Boolean ok = fx(() -> {
                revisarErrores();
                return cond.call();
            });
            if (Boolean.TRUE.equals(ok)) {
                return;
            }
            if (System.currentTimeMillis() > limite) {
                throw new IllegalStateException("Tiempo agotado (" + segundos + " s) esperando: " + desc);
            }
            dormir(POLL_MS);
        }
    }

    /** Sin peticiones en curso, sin indicadores de carga visibles y con las portadas descargadas. */
    private void esperarCarga() throws Exception {
        esperar("que termine de cargar la pantalla", () -> {
            if (Async.RUNNING.get() > 0 || Covers.pending() > 0) {
                return false;
            }
            for (Window w : Window.getWindows()) {
                if (w.isShowing() && w.getScene() != null) {
                    for (Node n : w.getScene().getRoot().lookupAll(".loading-overlay")) {
                        if (n.isVisible()) {
                            return false;
                        }
                    }
                }
            }
            return true;
        }, 90);
        dormir(700);                       // un pulso para que JavaFX pinte
    }

    /** Tiles del mapa descargados (no detiene el demo si OSM tarda). */
    private void esperarTiles() throws Exception {
        try {
            esperar("tiles del mapa", () -> {
                Node n = stage.getScene().getRoot().lookup(".web-view");
                if (!(n instanceof WebView wv)) {
                    return true;
                }
                Object r = wv.getEngine().executeScript(
                        "(function(){var t=document.querySelectorAll('.leaflet-tile').length;"
                                + "return t>0 && document.querySelectorAll('.leaflet-tile-loaded').length===t;})()");
                return Boolean.TRUE.equals(r);
            }, 20);
        } catch (IllegalStateException e) {
            if (e.getMessage() != null && e.getMessage().startsWith("Tiempo agotado")) {
                Log.warn("[DEMO] Algunos tiles del mapa no terminaron de cargar; se captura de todos modos.");
            } else {
                throw e;
            }
        }
        dormir(800);
    }

    // ================================================================== capturas

    private void captura(String nombre, Window w) throws Exception {
        WritableImage img = fx(() -> w.getScene().snapshot(null));
        guardar(nombre, img);
    }

    private void capturaNodo(String nombre, String id) throws Exception {
        WritableImage img = fx(() -> nodo(id).snapshot(null, null));
        guardar(nombre, img);
    }

    private void guardar(String nombre, WritableImage img) throws IOException {
        int w = (int) img.getWidth();
        int h = (int) img.getHeight();
        BufferedImage bi = new BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB);
        PixelReader pr = img.getPixelReader();
        for (int y = 0; y < h; y++) {
            for (int x = 0; x < w; x++) {
                bi.setRGB(x, y, pr.getArgb(x, y));
            }
        }
        Path f = outDir.resolve(nombre + ".png");
        ImageIO.write(bi, "png", f.toFile());
        guardadas.add(f.getFileName().toString());
        Log.info("[DEMO] Captura " + f.getFileName() + " (" + w + "x" + h + ")");
    }

    /** Raiz del repo (carpeta con .git) + Evidencias_DD_MM_AAAA. */
    private static Path carpetaEvidencias() {
        Path dir = Paths.get(System.getProperty("user.dir")).toAbsolutePath();
        Path raiz = dir;
        for (Path p = dir; p != null; p = p.getParent()) {
            if (Files.exists(p.resolve(".git"))) {
                raiz = p;
                break;
            }
        }
        return raiz.resolve("Evidencias_" + LocalDate.now().format(CARPETA));
    }

    // ================================================================== utilidades

    private Node nodo(String id) {
        Scene sc = stage.getScene();
        return sc == null ? null : sc.getRoot().lookup("#" + id);
    }

    private String texto(String id) {
        Node n = nodo(id);
        return n instanceof Label l ? l.getText() : n instanceof TextInputControl t ? t.getText() : null;
    }

    private static Node lookupEn(Window w, String id) {
        Parent root = w.getScene() == null ? null : w.getScene().getRoot();
        return root == null ? null : root.lookup("#" + id);
    }

    /** Ventana cuya raiz tiene ese id. Hilo FX. */
    private static Window ventanaConFx(String rootId) {
        for (Window w : Window.getWindows()) {
            if (w.isShowing() && w.getScene() != null && rootId.equals(w.getScene().getRoot().getId())) {
                return w;
            }
        }
        return null;
    }

    private Window ventanaCon(String rootId) throws Exception {
        Window w = fx(() -> ventanaConFx(rootId));
        if (w == null) {
            throw new IllegalStateException("No esta abierta la ventana " + rootId);
        }
        return w;
    }

    private Window ventanaActiva() throws Exception {
        return fx(() -> {
            for (Window w : Window.getWindows()) {
                if (w.isShowing() && w.isFocused()) {
                    return w;
                }
            }
            return stage;
        });
    }

    /** Ejecuta en el hilo de JavaFX y espera el resultado. */
    private static <T> T fx(Callable<T> c) throws Exception {
        FutureTask<T> f = new FutureTask<>(c);
        Platform.runLater(f);
        try {
            return f.get(60, TimeUnit.SECONDS);
        } catch (java.util.concurrent.ExecutionException e) {
            if (e.getCause() instanceof Exception ex) {
                throw ex;
            }
            throw e;
        }
    }

    private static void dormir(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static boolean isBlank(String s) {
        return s == null || s.isBlank();
    }
}
