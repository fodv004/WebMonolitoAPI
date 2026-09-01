const db = require('../config/db');
const catalogs = { formatos: ['id_formato', 'nombre'], generos: ['id_genero', 'nombre'], autores: ['id_autor', 'nombre', 'nacionalidad'], conceptos: ['id_concepto', 'nombre'] };
function config(type) { if (!catalogs[type]) throw new Error('Catálogo inválido'); return catalogs[type]; }
exports.list = async type => { config(type); return (await db.query(`SELECT * FROM ${type} ORDER BY nombre`)).rows; };
exports.get = async (type, id) => { const [key] = config(type); return (await db.query(`SELECT * FROM ${type} WHERE ${key} = $1`, [id])).rows[0]; };
exports.save = async (type, data, id) => { const [key, ...fields] = config(type); const values = fields.map(f => data[f] || null); if (id) { const set = fields.map((f,i) => `${f} = $${i+1}`).join(', '); await db.query(`UPDATE ${type} SET ${set} WHERE ${key} = $${fields.length+1}`, [...values,id]); } else { await db.query(`INSERT INTO ${type} (${fields.join(',')}) VALUES (${fields.map((_,i)=>'$'+(i+1)).join(',')})`, values); } };
exports.remove = async (type, id) => { const [key] = config(type); await db.query(`DELETE FROM ${type} WHERE ${key} = $1`, [id]); };
exports.fields = type => config(type).slice(1);
