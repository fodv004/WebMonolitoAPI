const bcrypt=require('bcrypt'),users=require('../models/userModel');
exports.list=async(req,res,next)=>{try{res.render('users/list',{items:await users.list()})}catch(e){next(e)}};
exports.form=async(req,res,next)=>{try{res.render('users/form',{item:req.params.id?await users.get(req.params.id):null})}catch(e){next(e)}};
exports.save=async(req,res,next)=>{try{const data={...req.body};if(data.password)data.password_hash=await bcrypt.hash(data.password,12);if(req.params.id)await users.update(req.params.id,data);else await users.create({...data,password_hash:data.password_hash,es_admin:data.es_admin==='on'});res.redirect((res.locals.base||'')+'/usuarios')}catch(e){next(e)}};
exports.remove=async(req,res,next)=>{try{await users.remove(req.params.id);res.redirect((res.locals.base||'')+'/usuarios')}catch(e){next(e)}};
