/* Native browser ceremonies. Never fabricate verification or retry submission. */
const LensDevice=(()=>{
 let session='',pending=null,controller=null;
 const decode=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
 const encode=b=>btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
 async function init(){
  if(session)return session;
  if(!pending)pending=(async()=>{const r=await fetch('/api/device/session',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Open Lens at http://localhost:8642.');session=d.session;return session})().finally(()=>{pending=null});
  return pending;
 }
 async function call(action,p={}){
  await init();
  const r=await fetch('/api/device/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Lens-Session':session},body:JSON.stringify(p)});
  const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||d.log||'Device approval could not complete.');return d;
 }
 function available(){return !!(window.isSecureContext&&window.PublicKeyCredential&&navigator.credentials)}
 function abort(){controller?.abort();controller=null}
 async function ceremony(d,registration=false){
  if(!available())throw Error('Device approval is unavailable in this browser. Open Lens in Safari, Chrome or Edge.');
  const options={...d.options,challenge:decode(d.options.challenge)};
  if(options.user)options.user={...options.user,id:decode(options.user.id)};
  for(const key of ['allowCredentials','excludeCredentials'])if(options[key])options[key]=options[key].map(c=>({...c,id:decode(c.id)}));
  abort();controller=new AbortController();
  try{
   const c=await navigator.credentials[registration?'create':'get']({publicKey:options,signal:controller.signal});
   if(!c)throw Error('Device approval was cancelled.');
   const response={clientDataJSON:encode(c.response.clientDataJSON)};
   for(const key of ['attestationObject','authenticatorData','signature','userHandle'])if(c.response[key])response[key]=encode(c.response[key]);
   return {challenge_id:d.challenge_id,credential:{id:c.id,rawId:encode(c.rawId),type:c.type,response}};
  }catch(e){
   if(['NotAllowedError','AbortError'].includes(e.name))throw Error('Device approval was cancelled or timed out. No orders were sent.');
   throw Error(e.message||'Device approval failed. No orders were sent.');
  }finally{controller=null}
 }
 async function approve(reviewId){return ceremony(await call('orders-options',{review_id:reviewId}))}
 return {init,call,ceremony,approve,available,abort,headers:()=>session?{'X-Lens-Session':session}:{}};
})();
