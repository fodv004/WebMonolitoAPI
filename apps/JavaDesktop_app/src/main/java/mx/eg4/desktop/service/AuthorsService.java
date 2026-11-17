package mx.eg4.desktop.service;

import java.util.ArrayList;
import java.util.List;

import mx.eg4.desktop.config.AppConfig.Service;
import mx.eg4.desktop.http.ApiClient;
import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.http.Json;
import mx.eg4.desktop.model.Author;

/** authors (gateway /authors): GET /authors/by-book/&lt;isbn&gt;. */
public final class AuthorsService {

    private final ApiClient api;

    AuthorsService(ApiClient api) {
        this.api = api;
    }

    public List<Author> byBook(String isbn) throws ApiException {
        List<Author> out = new ArrayList<>();
        api.get(Service.AUTHORS, "/authors/by-book/" + Paths.seg(isbn), false).path("authors")
                .forEach(n -> out.add(Json.convert(n, Author.class)));
        return out;
    }
}
