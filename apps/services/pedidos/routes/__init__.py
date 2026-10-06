"""
routes/
Blueprints del microservicio pedidos. Cada blueprint nuevo se registra en
register_routes().

Las escrituras (POST, PUT, PATCH, DELETE) deben llevar @require_auth o
@require_role(ADMIN_ROLE_ID) de common/auth.py.
"""


def register_routes(app):
    from routes.pedidos import bp as pedidos_bp

    app.register_blueprint(pedidos_bp)
