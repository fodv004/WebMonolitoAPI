const express=require('express'),multer=require('multer'),path=require('path'); const auth=require('../middleware/auth'),a=require('../controllers/authController'),c=require('../controllers/catalogController'),u=require('../controllers/userController'),b=require('../controllers/bookController'); const router=express.Router();
const EXTENSIONES_PERMITIDAS=['.jpg','.jpeg','.png','.webp'];
const storage=multer.diskStorage({
  destination:path.join(__dirname,'../../public/uploads'),
  // Nombre generado por el sistema (timestamp + random), nunca el nombre original del usuario.
  filename:(req,file,cb)=>cb(null,Date.now()+'-'+Math.round(Math.random()*1e9)+path.extname(file.originalname).toLowerCase())
});
const upload=multer({
  storage,
  limits:{fileSize:5*1024*1024}, // máximo 5MB por imagen
  fileFilter:(req,file,cb)=>{
    const extension=path.extname(file.originalname).toLowerCase();
    const mimeValido=['image/jpeg','image/png','image/webp'].includes(file.mimetype);
    const extensionValida=EXTENSIONES_PERMITIDAS.includes(extension);
    if(mimeValido && extensionValida) return cb(null, true);
    cb(new Error('Formato de imagen no permitido. Usa JPG, PNG o WebP.'));
  }
});
router.get('/login',a.loginForm);router.post('/login',a.login);router.get('/registro',a.registerForm);router.post('/registro',a.register);router.post('/logout',a.logout);
router.use(auth.requireAuth);router.get('/',b.list);
router.get('/catalogos/:type',auth.requireAdmin,c.list);router.get('/catalogos/:type/nuevo',auth.requireAdmin,c.form);router.post('/catalogos/:type',auth.requireAdmin,c.save);router.get('/catalogos/:type/:id/editar',auth.requireAdmin,c.form);router.post('/catalogos/:type/:id',auth.requireAdmin,c.save);router.post('/catalogos/:type/:id/eliminar',auth.requireAdmin,c.remove);
router.get('/usuarios',auth.requireAdmin,u.list);router.get('/usuarios/nuevo',auth.requireAdmin,u.form);router.post('/usuarios',auth.requireAdmin,u.save);router.get('/usuarios/:id/editar',auth.requireAdmin,u.form);router.post('/usuarios/:id',auth.requireAdmin,u.save);router.post('/usuarios/:id/eliminar',auth.requireAdmin,u.remove);
router.get('/libros',b.list);router.get('/libros/nuevo',auth.requireAdmin,b.form);router.post('/libros',auth.requireAdmin,b.save);router.get('/libros/:isbn',b.detail);router.get('/libros/:isbn/editar',auth.requireAdmin,b.form);router.post('/libros/:isbn',auth.requireAdmin,b.save);router.post('/libros/:isbn/eliminar',auth.requireAdmin,b.remove);router.post('/libros/:isbn/conceptos',auth.requireAdmin,b.addConcept);router.post('/libros/:isbn/conceptos/:id/eliminar',auth.requireAdmin,b.removeConcept);router.post('/libros/:isbn/imagenes',auth.requireAdmin,upload.single('imagen'),b.addImage);router.post('/libros/:isbn/imagenes/:id/eliminar',auth.requireAdmin,b.removeImage);
module.exports=router;