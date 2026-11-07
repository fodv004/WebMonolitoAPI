package mx.eg4.desktop.ui.util;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

import javafx.beans.property.IntegerProperty;
import javafx.beans.property.SimpleIntegerProperty;
import javafx.concurrent.Task;

/** Ejecuta peticiones en hilos de fondo (javafx.concurrent.Task) y regresa el resultado al hilo de JavaFX. */
public final class Async {

    private static final AtomicInteger N = new AtomicInteger();
    private static final ExecutorService POOL = Executors.newFixedThreadPool(8, r -> {
        Thread t = new Thread(r, "peticion-" + N.incrementAndGet());
        t.setDaemon(true);
        return t;
    });

    /** Peticiones en curso (para el indicador global de la barra superior). Solo en el hilo de JavaFX. */
    public static final IntegerProperty RUNNING = new SimpleIntegerProperty(0);

    private Async() {
    }

    /** Debe llamarse desde el hilo de JavaFX. ok y err se ejecutan en el hilo de JavaFX. */
    public static <T> Task<T> run(Callable<T> work, Consumer<T> ok, Consumer<Throwable> err) {
        Task<T> task = new Task<>() {
            @Override
            protected T call() throws Exception {
                return work.call();
            }
        };
        RUNNING.set(RUNNING.get() + 1);
        task.setOnSucceeded(e -> {
            RUNNING.set(RUNNING.get() - 1);
            ok.accept(task.getValue());
        });
        task.setOnFailed(e -> {
            RUNNING.set(RUNNING.get() - 1);
            err.accept(task.getException());
        });
        task.setOnCancelled(e -> RUNNING.set(RUNNING.get() - 1));
        POOL.submit(task);
        return task;
    }

    /** Tarea sin interfaz (p. ej. logout al cerrar la ventana). */
    public static void fireAndForget(Runnable r) {
        POOL.submit(r);
    }

    public static void shutdown() {
        POOL.shutdownNow();
    }
}
