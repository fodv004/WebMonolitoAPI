const db = require('../config/db');
// Los apellidos son opcionales en BD (cuentas antiguas migradas): cadena vacía -> NULL.
const vacioANull = v => (v && String(v).trim()) || null;
exports.nombreCompleto = u => [u.nombre, u.apellido_paterno, u.apellido_materno].filter(Boolean).join(' ');
exports.list = async () => (await db.query('SELECT id_usuario,nombre,apellido_paterno,apellido_materno,correo,es_admin,activo,estado_cuenta,fecha_registro FROM usuarios ORDER BY id_usuario')).rows;
exports.get = async id => (await db.query('SELECT id_usuario,nombre,apellido_paterno,apellido_materno,correo,es_admin,activo,estado_cuenta FROM usuarios WHERE id_usuario=$1',[id])).rows[0];
// Solo lo usa el CRUD del administrador (/usuarios). El registro público y el login se delegan en el
// microservicio de auth; las altas del administrador no envían correo, así que nacen 'confirmado'.
exports.create = async ({nombre,apellido_paterno,apellido_materno,correo,password_hash,es_admin=false,estado_cuenta='confirmado'}) => db.query('INSERT INTO usuarios(nombre,apellido_paterno,apellido_materno,correo,password_hash,es_admin,estado_cuenta) VALUES($1,$2,$3,$4,$5,$6,$7)',[nombre.trim(),vacioANull(apellido_paterno),vacioANull(apellido_materno),correo,password_hash,es_admin,estado_cuenta]);
exports.update = async (id,{nombre,apellido_paterno,apellido_materno,correo,password_hash,es_admin,activo,estado_cuenta}) => { const columns=['nombre=$1','apellido_paterno=$2','apellido_materno=$3','correo=$4','es_admin=$5','activo=$6','estado_cuenta=$7']; const args=[nombre.trim(),vacioANull(apellido_paterno),vacioANull(apellido_materno),correo,es_admin === 'on',activo === 'on',estado_cuenta === 'pendiente' ? 'pendiente' : 'confirmado']; if(password_hash){columns.push(`password_hash=$${args.length+1}`);args.push(password_hash);} args.push(id); return db.query(`UPDATE usuarios SET ${columns.join(',')} WHERE id_usuario=$${args.length}` ,args); };
exports.remove = async id => db.query('DELETE FROM usuarios WHERE id_usuario=$1',[id]);
