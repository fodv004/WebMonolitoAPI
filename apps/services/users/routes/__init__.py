"""
routes/
Blueprints del microservicio users. Cada blueprint nuevo se registra en
register_routes().

Las escrituras (POST, PUT, PATCH, DELETE) deben llevar @require_auth o
@require_role(ADMIN_ROLE_ID) de common/auth.py.
"""


def register_routes(app):
    from routes.users import bp as users_bp

    app.register_blueprint(users_bp)
