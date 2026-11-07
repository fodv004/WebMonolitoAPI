package mx.eg4.desktop.service;

import java.util.ArrayList;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;

import mx.eg4.desktop.config.AppConfig.Service;
import mx.eg4.desktop.http.ApiClient;
import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.http.Json;
import mx.eg4.desktop.model.Book;

/** books (5001): GET /books y GET /books/&lt;isbn&gt; (ApiClient agrega ?format=json). */
public final class BooksService {

    private final ApiClient api;

    BooksService(ApiClient api) {
        this.api = api;
    }

    public List<Book> list() throws ApiException {
        JsonNode arr = api.get(Service.BOOKS, "/books", false);
        List<Book> out = new ArrayList<>();
        if (arr.isArray()) {
            arr.forEach(n -> out.add(Json.convert(n, Book.class)));
        }
        return out;
    }

    public Book get(String isbn) throws ApiException {
        return Json.convert(api.get(Service.BOOKS, "/books/" + Paths.seg(isbn), false), Book.class);
    }
}
