const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const api=fs.readFileSync(path.join(__dirname,'../device-api.js'),'utf8');
function page(cancel=false){
 const calls=[],ceremonies=[];
 const context=vm.createContext({Uint8Array,AbortController,atob,btoa,Error,JSON,
  window:{isSecureContext:true,PublicKeyCredential:{}},navigator:{credentials:{get:async options=>{
   ceremonies.push(options);if(cancel){const e=Error('Cancelled');e.name='NotAllowedError';throw e}
   return {id:'aWQ',rawId:new Uint8Array([1,2]).buffer,type:'public-key',response:{clientDataJSON:new Uint8Array([3]).buffer,authenticatorData:new Uint8Array([4]).buffer,signature:new Uint8Array([5]).buffer}};
  }}},fetch:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>url.endsWith('/session')?{ok:true,session:'browser-session'}:{ok:true,challenge_id:'challenge-1',options:{challenge:'AQI',rpId:'localhost',allowCredentials:[{id:'aWQ',type:'public-key'}],userVerification:'required'}}}}});
 vm.runInContext(api,context);return {calls,ceremonies,run:s=>vm.runInContext(s,context)};
}
test('browser assertion is session-bound and does not submit an order itself',async()=>{
 const p=page();const result=await p.run("LensDevice.approve('review-1')");
 assert.equal(result.challenge_id,'challenge-1');assert.equal(result.credential.response.signature,'BQ');
 assert.equal(p.calls.length,2);assert.equal(p.calls[1].options.headers['X-Lens-Session'],'browser-session');
 assert.equal(JSON.parse(p.calls[1].options.body).review_id,'review-1');
 assert.equal(p.ceremonies[0].publicKey.userVerification,'required');
 assert.deepEqual(Array.from(p.ceremonies[0].publicKey.challenge),[1,2]);
 assert.equal(p.calls.some(c=>c.url==='/api/execute'),false);
});
test('cancelled device prompt supplies no synthetic success',async()=>{
 const p=page(true);await assert.rejects(p.run("LensDevice.approve('review-1')"),/cancelled or timed out/);
 assert.equal(p.calls.length,2);
});
test('concurrent session initialization issues one session request',async()=>{
 const p=page();await p.run('Promise.all([LensDevice.init(),LensDevice.init()])');assert.equal(p.calls.length,1);
});
test('canonical localhost navigation preserves theme and research bookmark',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../local-origin.js'),'utf8');let redirect='',saved='';
 vm.runInNewContext(source,{URL,location:{href:'http://127.0.0.1:8642/workspace#xray',replace:url=>redirect=url},localStorage:{getItem:()=> 'dark'}});
 assert.equal(redirect,'http://localhost:8642/workspace?lens_theme=dark#xray');
 vm.runInNewContext(source,{URL,location:{href:redirect},history:{replaceState:(a,b,url)=>redirect=url},localStorage:{setItem:(key,value)=>saved=value}});
 assert.equal(saved,'dark');assert.equal(redirect,'/workspace#xray');
});
