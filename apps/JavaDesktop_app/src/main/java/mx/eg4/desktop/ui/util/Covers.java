package mx.eg4.desktop.ui.util;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import javafx.scene.image.Image;
import javafx.scene.image.ImageView;

import mx.eg4.desktop.util.Log;

/** Portadas cargadas en segundo plano con una imagen local si no hay portada o si falla. */
public final class Covers {

    private static final Image PLACEHOLDER = new Image(Covers.class.getResource("/img/sin-portada.png").toExternalForm());
    private static final Map<String, Image> CACHE = new ConcurrentHashMap<>();
    /** Portadas que aun se estan descargando (solo hilo de JavaFX). */
    private static int pending;

    private Covers() {
    }

    /** Cuantas portadas siguen descargandose. */
    public static int pending() {
        return pending;
    }

    public static ImageView view(String url, double w, double h) {
        ImageView iv = new ImageView(PLACEHOLDER);
        iv.setFitWidth(w);
        iv.setFitHeight(h);
        iv.setPreserveRatio(true);
        iv.setSmooth(true);
        load(iv, url);
        return iv;
    }

    public static void load(ImageView iv, String url) {
        if (url == null || url.isBlank() || !(url.startsWith("http://") || url.startsWith("https://"))) {
            iv.setImage(PLACEHOLDER);
            return;
        }
        Image cached = CACHE.get(url);
        if (cached != null && !cached.isError()) {
            iv.setImage(cached.getProgress() >= 1 ? cached : PLACEHOLDER);
            if (cached.getProgress() < 1) {
                watch(iv, cached, url);
            }
            return;
        }
        // backgroundLoading = true: la imagen se descarga en un hilo de JavaFX aparte.
        Image img = new Image(url, 300, 0, true, true, true);
        CACHE.put(url, img);
        pending++;
        boolean[] done = {false};
        Runnable finish = () -> {
            if (!done[0]) {
                done[0] = true;
                pending--;
            }
        };
        img.errorProperty().addListener((o, a, err) -> {
            if (err) {
                finish.run();
            }
        });
        img.progressProperty().addListener((o, a, p) -> {
            if (p.doubleValue() >= 1) {
                finish.run();
            }
        });
        if (img.isError() || img.getProgress() >= 1) {
            finish.run();
        }
        watch(iv, img, url);
    }

    private static void watch(ImageView iv, Image img, String url) {
        img.errorProperty().addListener((obs, old, err) -> {
            if (err) {
                CACHE.remove(url);
                Log.warn("Portada no disponible: " + url);
                iv.setImage(PLACEHOLDER);
            }
        });
        img.progressProperty().addListener((obs, old, p) -> {
            if (p.doubleValue() >= 1 && !img.isError()) {
                iv.setImage(img);
            }
        });
    }
}
