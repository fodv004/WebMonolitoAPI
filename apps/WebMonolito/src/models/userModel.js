const db = require('../config/db');
exports.findByEmail = async correo => (await db.query('SELECT * FROM usuarios WHERE correo=$1 AND activo=TRUE', [correo])).rows[0];
exports.list = async () => (await db.query('SELECT id_usuario,nombre,correo,es_admin,activo,fecha_registro FROM usuarios ORDER BY id_usuario')).rows;
exports.get = async id => (await db.query('SELECT id_usuario,nombre,correo,es_admin,activo FROM usuarios WHERE id_usuario=$1',[id])).rows[0];
exports.create = async ({nombre,correo,password_hash,es_admin=false}) => db.query('INSERT INTO usuarios(nombre,correo,password_hash,es_admin) VALUES($1,$2,$3,$4)',[nombre,correo,password_hash,es_admin]);
exports.update = async (id,{nombre,correo,password_hash,es_admin,activo}) => { const columns=['nombre=$1','correo=$2','es_admin=$3','activo=$4']; const args=[nombre,correo,es_admin === 'on',activo === 'on']; if(password_hash){columns.push(`password_hash=$${args.length+1}`);args.push(password_hash);} args.push(id); return db.query(`UPDATE usuarios SET ${columns.join(',')} WHERE id_usuario=$${args.length}` ,args); };
exports.remove = async id => db.query('DELETE FROM usuarios WHERE id_usuario=$1',[id]);
