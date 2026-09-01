exports.requireAuth = (req, res, next) => req.session.user ? next() : res.redirect((res.locals.base||'')+'/login');
exports.requireAdmin = (req, res, next) => req.session.user?.es_admin ? next() : res.status(403).render('error', { message: 'Esta acción requiere una cuenta administradora.', status: 403 });
