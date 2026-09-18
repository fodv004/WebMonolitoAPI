// Cliente HTTP del microservicio de autenticación (apps/services/login).
// El monolito ya no registra ni valida usuarios contra PostgreSQL: delega en
// POST /register y POST /login de ese servicio (siempre con ?format=json).
// Usa el fetch nativo de Node (>=18); no hay dependencias nuevas.
require('dotenv').config();

const AUTH_URL = (process.env.AUTH_SERVICE_URL || 'http://localhost:5000').replace(/\/+$/, '');
const TIMEOUT_MS = Number(process.env.AUTH_SERVICE_TIMEOUT_MS || 10000);

// El servicio no respondió (caído, timeout, respuesta que no es JSON...).
class AuthUnavailableError extends Error {}

async function post(path, payload) {
  let res;
  try {
    res = await fetch(`${AUTH_URL}${path}?format=json`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(payload),
      redirect: 'manual',
      signal: AbortSignal.timeout(TIMEOUT_MS)
    });
  } catch (e) {
    throw new AuthUnavailableError(`${AUTH_URL}${path}: ${e.cause?.code || e.name}`);
  }
  let body;
  try { body = await res.json(); } catch { throw new AuthUnavailableError(`${AUTH_URL}${path}: respuesta no JSON (HTTP ${res.status})`); }
  return { status: res.status, body };
}

exports.AuthUnavailableError = AuthUnavailableError;

// Campos del formulario del monolito -> contrato del microservicio (email en vez de correo).
exports.register = ({ nombre, apellido_paterno, apellido_materno, correo, password }) =>
  post('/register', { nombre, apellido_paterno, apellido_materno, email: correo, password });

exports.login = ({ correo, password }) => post('/login', { email: correo, password });

// Texto para mostrar al usuario: el detalle por campo (400) o el mensaje del servicio.
exports.mensajeDeError = ({ status, body }, porDefecto) => {
  if (status >= 500 && status !== 503) return porDefecto;
  const detalle = Array.isArray(body?.errors) ? body.errors.map(e => e.message).filter(Boolean).join(' ') : '';
  return detalle || body?.message || porDefecto;
};

// Códigos que el formulario puede mostrar tal cual; cualquier otro (5xx...) se presenta como 503.
exports.statusParaVista = status => ([400, 401, 403, 409].includes(status) ? status : 503);
