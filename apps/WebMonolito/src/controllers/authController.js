const auth=require('../services/authClient'), users=require('../models/userModel');
// Registro e inicio de sesión se delegan en el microservicio de auth (AUTH_SERVICE_URL);
// este controlador solo traduce su respuesta a las vistas y mantiene la sesión de Express.
const SERVICIO_CAIDO='El servicio de autenticación no está disponible en este momento. Intenta de nuevo más tarde.';
exports.loginForm=(req,res)=>res.render('login',req.query.registro==='pendiente'?{notice:'Cuenta creada. Revisa tu correo para confirmar tu cuenta: podrás iniciar sesión cuando abras el enlace que te enviamos.'}:{});
exports.login=async(req,res,next)=>{try{const r=await auth.login(req.body);const u=r.status===200&&r.body?.data?.user;if(!u)return res.status(auth.statusParaVista(r.status)).render('login',{error:auth.mensajeDeError(r,'No se pudo iniciar sesión.')});req.session.user={id:u.id_usuario,nombre:users.nombreCompleto(u),es_admin:u.es_admin};res.redirect((res.locals.base||'')+'/?flash=login_success');}catch(e){if(e instanceof auth.AuthUnavailableError){console.error(e.message);return res.status(503).render('login',{error:SERVICIO_CAIDO});}next(e)}};
exports.registerForm=(req,res)=>res.render('register');
exports.register=async(req,res,next)=>{try{const r=await auth.register(req.body);if(r.status===201)return res.redirect((res.locals.base||'')+'/login?registro=pendiente');res.status(auth.statusParaVista(r.status)).render('register',{error:auth.mensajeDeError(r,'No se pudo completar el registro.')});}catch(e){if(e instanceof auth.AuthUnavailableError){console.error(e.message);return res.status(503).render('register',{error:SERVICIO_CAIDO});}next(e)}};
exports.logout=(req,res)=>{const base=res.locals.base||'';req.session.destroy(()=>res.redirect(base+'/login?flash=logout_success'))};
