package mx.eg4.desktop.model;

/** Libro de books (GET /books o GET /books/<isbn>). autor y genero solo vienen en la lista. */
public record Book(String isbn, String titulo, Integer anio, Double precio, Integer stock, String formato,
                   String autor, String genero, String portada, String imageUrl, String descripcion) {

    public boolean disponible() {
        return stock != null && stock > 0;
    }

    public int stockSeguro() {
        return stock == null ? 0 : stock;
    }

    public double precioSeguro() {
        return precio == null ? 0 : precio;
    }

    public String portadaUrl() {
        return portada != null && !portada.isBlank() ? portada : imageUrl;
    }
}
