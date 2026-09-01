const catalog=require('../models/catalogModel');
exports.list=async(req,res,next)=>{try{res.render('catalogs/list',{type:req.params.type,items:await catalog.list(req.params.type),fields:catalog.fields(req.params.type)});}catch(e){next(e)}};
exports.form=async(req,res,next)=>{try{const {type,id}=req.params;res.render('catalogs/form',{type,item:id?await catalog.get(type,id):null,fields:catalog.fields(type)});}catch(e){next(e)}};
exports.save=async(req,res,next)=>{try{await catalog.save(req.params.type,req.body,req.params.id);res.redirect((res.locals.base||'')+'/catalogos/'+req.params.type)}catch(e){next(e)}};
exports.remove=async(req,res,next)=>{try{await catalog.remove(req.params.type,req.params.id);res.redirect((res.locals.base||'')+'/catalogos/'+req.params.type)}catch(e){next(e)}};
