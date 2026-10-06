"""
routes/
Blueprints del microservicio authors. Cada blueprint nuevo se registra en
register_routes().

Las escrituras (POST, PUT, PATCH, DELETE) deben llevar @require_auth o
@require_role(ADMIN_ROLE_ID) de common/auth.py.
"""


def register_routes(app):
    from routes.authors import bp as authors_bp

    app.register_blueprint(authors_bp)
