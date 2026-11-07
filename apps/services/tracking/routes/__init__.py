"""
routes/
Blueprints y WebSocket del microservicio tracking.
"""


def register_routes(app):
    from routes.envios import bp as envios_bp
    from routes.ws import sock

    app.register_blueprint(envios_bp)
    sock.init_app(app)
