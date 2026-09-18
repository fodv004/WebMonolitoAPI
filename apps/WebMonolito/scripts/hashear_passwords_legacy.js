// Convierte a bcrypt las contraseñas que siguen en texto plano en usuarios.password_hash.
//
// Por qué: el login del monolito ahora se delega en el microservicio de auth, que solo
// acepta hashes bcrypt. Las cuentas del seed (demo1234, en texto plano) dejarían de entrar.
//
//   cd apps/WebMonolito
//   node scripts/hashear_passwords_legacy.js
//
// - Cada contraseña conserva su mismo valor; solo cambia cómo se guarda (nunca se pierde acceso).
// - Es idempotente: las filas que ya tienen hash bcrypt no se tocan.
// - Los marcadores de posición del seed (CAMBIAR_POR_HASH_BCRYPT_REAL, hash_de_ejemplo) NO se
//   hashean, porque quedarían como contraseña real conocida. Para el administrador genera un
//   hash con una clave propia (ver README.md) y haz el UPDATE.
const bcrypt = require('bcrypt');
const db = require('../src/config/db');

const PLACEHOLDERS = ['CAMBIAR_POR_HASH_BCRYPT_REAL', 'hash_de_ejemplo'];

(async () => {
  const { rows } = await db.query("SELECT id_usuario, correo, password_hash FROM usuarios WHERE password_hash !~ '^\\$2[aby]\\$' ORDER BY id_usuario");
  let convertidas = 0;
  const omitidas = [];
  for (const u of rows) {
    if (PLACEHOLDERS.includes(u.password_hash)) { omitidas.push(u.correo); continue; }
    await db.query('UPDATE usuarios SET password_hash=$1 WHERE id_usuario=$2', [await bcrypt.hash(u.password_hash, 12), u.id_usuario]);
    convertidas++;
  }
  console.log(`Contraseñas convertidas a bcrypt: ${convertidas}`);
  if (omitidas.length) {
    console.log(`Omitidas (marcador del seed, asigna una contraseña real): ${omitidas.join(', ')}`);
    console.log(`  node -e "require('bcrypt').hash('TuClaveSegura',12).then(console.log)"`);
    console.log(`  UPDATE usuarios SET password_hash='<hash>' WHERE correo='<correo>';`);
  }
  await db.end();
})().catch(e => { console.error(e); process.exit(1); });
