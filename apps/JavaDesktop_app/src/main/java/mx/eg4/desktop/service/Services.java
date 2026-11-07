package mx.eg4.desktop.service;

import mx.eg4.desktop.http.ApiClient;

/** Agrupa los clientes de cada microservicio. */
public final class Services {

    public final ApiClient api;
    public final LoginService login;
    public final BooksService books;
    public final UsersService users;
    public final AuthorsService authors;
    public final PedidosService pedidos;
    public final PagosService pagos;
    public final EnviosService envios;
    public final SoapService soap;

    public Services(ApiClient api) {
        this.api = api;
        this.login = new LoginService(api);
        this.books = new BooksService(api);
        this.users = new UsersService(api);
        this.authors = new AuthorsService(api);
        this.pedidos = new PedidosService(api);
        this.pagos = new PagosService(api);
        this.envios = new EnviosService(api);
        this.soap = new SoapService(api);
    }
}
