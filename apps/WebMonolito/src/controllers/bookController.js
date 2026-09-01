const books=require('../models/bookModel'),catalog=require('../models/catalogModel'),fs=require('fs');
const selections=async()=>({formatos:await catalog.list('formatos'),autores:await catalog.list('autores'),generos:await catalog.list('generos'),conceptos:await catalog.list('conceptos')});
// Valida el contenido real del archivo (magic bytes), sin confiar en la extensión
// ni en el mimetype que reporta el navegador (ambos se pueden falsificar renombrando).
function esImagenValida(filePath){
  const buf=Buffer.alloc(12);
  const fd=fs.openSync(filePath,'r');
  fs.readSync(fd,buf,0,12,0);
  fs.closeSync(fd);
  const esJPEG=buf[0]===0xFF&&buf[1]===0xD8&&buf[2]===0xFF;
  const esPNG=buf[0]===0x89&&buf[1]===0x50&&buf[2]===0x4E&&buf[3]===0x47;
  const esWEBP=buf.toString('ascii',0,4)==='RIFF'&&buf.toString('ascii',8,12)==='WEBP';
  return esJPEG||esPNG||esWEBP;
}
exports.list=async(req,res,next)=>{try{res.render('books/list',{items:await books.list(req.query.q),q:req.query.q||''})}catch(e){next(e)}};
exports.detail=async(req,res,next)=>{try{const book=await books.get(req.params.isbn);if(!book)return res.status(404).render('error',{message:'Libro no encontrado.',status:404});res.render('books/detail',{book, ...(await selections())})}catch(e){next(e)}};
exports.form=async(req,res,next)=>{try{res.render('books/form',{book:req.params.isbn?await books.get(req.params.isbn):null,...(await selections())})}catch(e){next(e)}};
exports.save=async(req,res,next)=>{try{await books.save(req.body,req.params.isbn);await books.setRelations(req.body.isbn,req.body);res.redirect((res.locals.base||'')+'/libros/'+req.body.isbn)}catch(e){next(e)}};
exports.remove=async(req,res,next)=>{try{await books.remove(req.params.isbn);res.redirect((res.locals.base||'')+'/libros')}catch(e){next(e)}};
exports.addConcept=async(req,res,next)=>{try{await books.addConcept(req.params.isbn,req.body.id_concepto,req.body.definicion);res.redirect((res.locals.base||'')+'/libros/'+req.params.isbn)}catch(e){next(e)}};
exports.removeConcept=async(req,res,next)=>{try{await books.removeConcept(req.params.isbn,req.params.id);res.redirect((res.locals.base||'')+'/libros/'+req.params.isbn)}catch(e){next(e)}};
exports.addImage=async(req,res,next)=>{try{
  let url=req.body.url;
  if(req.file){
    if(!esImagenValida(req.file.path)){
      fs.unlinkSync(req.file.path); // borra el archivo falso ya guardado en disco
      throw new Error('El archivo no es una imagen válida (el contenido no coincide con el tipo declarado).');
    }
    url='/uploads/'+req.file.filename;
  }
  if(!url)throw new Error('Selecciona una imagen o proporciona una URL.');
  await books.addImage(req.params.isbn,url,req.body.es_principal==='on',req.body.orden);
  res.redirect((res.locals.base||'')+'/libros/'+req.params.isbn)
}catch(e){next(e)}};
exports.removeImage=async(req,res,next)=>{try{await books.removeImage(req.params.id);res.redirect((res.locals.base||'')+'/libros/'+req.params.isbn)}catch(e){next(e)}};