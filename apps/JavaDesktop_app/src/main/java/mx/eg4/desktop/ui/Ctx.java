package mx.eg4.desktop.ui;

import javafx.stage.Stage;

import mx.eg4.desktop.cart.Cart;
import mx.eg4.desktop.config.AppConfig;
import mx.eg4.desktop.service.Services;
import mx.eg4.desktop.session.Session;

/** Lo que comparten todas las pantallas. */
public final class Ctx {

    public final AppConfig config;
    public final Session session;
    public final Services services;
    public final Cart cart;
    public final Stage stage;
    private Navigator navigator;

    public Ctx(AppConfig config, Session session, Services services, Cart cart, Stage stage) {
        this.config = config;
        this.session = session;
        this.services = services;
        this.cart = cart;
        this.stage = stage;
    }

    public Navigator nav() {
        return navigator;
    }

    void setNavigator(Navigator n) {
        this.navigator = n;
    }
}
