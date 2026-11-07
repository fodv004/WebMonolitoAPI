package mx.eg4.desktop.cart;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import javafx.beans.Observable;
import javafx.beans.binding.Bindings;
import javafx.beans.binding.DoubleBinding;
import javafx.beans.binding.IntegerBinding;
import javafx.beans.property.DoubleProperty;
import javafx.beans.property.IntegerProperty;
import javafx.beans.property.SimpleDoubleProperty;
import javafx.beans.property.SimpleIntegerProperty;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;

import mx.eg4.desktop.model.Book;

/** Cesta en memoria. Solo se modifica desde el hilo de JavaFX. */
public final class Cart {

    public static final class Item {
        private final String isbn;
        private final String titulo;
        private final DoubleProperty precio = new SimpleDoubleProperty();
        private final IntegerProperty cantidad = new SimpleIntegerProperty();
        private final IntegerProperty stock = new SimpleIntegerProperty();
        private final DoubleBinding subtotal;

        Item(Book b, int cantidad) {
            this.isbn = b.isbn();
            this.titulo = b.titulo();
            this.precio.set(b.precioSeguro());
            this.stock.set(b.stockSeguro());
            this.cantidad.set(cantidad);
            this.subtotal = this.precio.multiply(this.cantidad);
        }

        public String isbn() {
            return isbn;
        }

        public String titulo() {
            return titulo;
        }

        public DoubleProperty precioProperty() {
            return precio;
        }

        public IntegerProperty cantidadProperty() {
            return cantidad;
        }

        public IntegerProperty stockProperty() {
            return stock;
        }

        public DoubleBinding subtotalBinding() {
            return subtotal;
        }
    }

    private final ObservableList<Item> items = FXCollections.observableArrayList(
            i -> new Observable[]{i.cantidad, i.precio});
    private final IntegerBinding count = Bindings.createIntegerBinding(
            () -> items.stream().mapToInt(i -> i.cantidad.get()).sum(), items);
    private final DoubleBinding total = Bindings.createDoubleBinding(
            () -> items.stream().mapToDouble(i -> i.precio.get() * i.cantidad.get()).sum(), items);

    public ObservableList<Item> items() {
        return items;
    }

    public IntegerBinding countBinding() {
        return count;
    }

    public DoubleBinding totalBinding() {
        return total;
    }

    public Item find(String isbn) {
        return items.stream().filter(i -> i.isbn.equals(isbn)).findFirst().orElse(null);
    }

    /**
     * Agrega (o suma) un libro. La cantidad total se limita al stock conocido.
     * Devuelve la cantidad que quedo en la cesta.
     */
    public int add(Book b, int cantidad) {
        Item existente = find(b.isbn());
        int stock = b.stockSeguro();
        if (existente == null) {
            Item nuevo = new Item(b, Math.min(cantidad, stock));
            items.add(nuevo);
            return nuevo.cantidad.get();
        }
        existente.precio.set(b.precioSeguro());
        existente.stock.set(stock);
        existente.cantidad.set(Math.min(existente.cantidad.get() + cantidad, stock));
        return existente.cantidad.get();
    }

    public void remove(Item i) {
        items.remove(i);
    }

    public void clear() {
        items.clear();
    }

    public boolean isEmpty() {
        return items.isEmpty();
    }

    /** Cuerpo de POST /pedidos: [{"isbn","cantidad"}]. */
    public List<Map<String, Object>> lineasParaPedido() {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Item i : items) {
            Map<String, Object> l = new LinkedHashMap<>();
            l.put("isbn", i.isbn);
            l.put("cantidad", i.cantidad.get());
            out.add(l);
        }
        return out;
    }
}
