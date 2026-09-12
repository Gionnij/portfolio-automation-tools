// Setup presentation only. Native authentication and HTTP calls are synthetic.
const {test}=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../device-settings.js'),'utf8');
const tick=()=>new Promise(r=>setImmediate(r));
async function page({pin=false,registered=false,tested=false,modes=[],route='/setup',supported=true}={}){
 const nodes=new Map(),calls=[],events=[],state={ok:true,registered,tested,modes};
 const node=id=>{if(!nodes.has(id))nodes.set(id,{hidden:false,disabled:false,textContent:'',innerHTML:'',value:'',events:{},classList:{toggle(){}},addEventListener(k,f){this.events[k]=f}});return nodes.get(id)};
 const location={assign(url){this.redirect=url},reload(){}};
 const ctx=vm.createContext({document:{body:{dataset:{lensRoute:route}},getElementById:node,querySelector:()=>node('hero'),querySelectorAll:()=>Array.from(nodes.values())},location,LensDevice:{available:()=>supported,call:async(action,p)=>{events.push({action,p});if(action==='status')return state;if(action.endsWith('-options'))return {challenge_id:'demo'};if(action==='test-verify'){state.tested=true;return{test_approved:true}};return{ok:true}},ceremony:async()=>{events.push({action:'native-prompt'});return{credential:'synthetic'}}},fetch:async(url,options)=>{const p=JSON.parse(options.body);calls.push({url,p});if(url==='/api/pin'&&p.op==='set')pin=true;return{ok:true,json:async()=>url==='/api/pin'?{ok:true,set:pin}:{ok:true}}}});
 vm.runInContext(source,ctx);await tick();return{node,calls,events,location,run:s=>vm.runInContext(s,ctx),submit:async id=>{node(id).events.submit({preventDefault(){}});await tick()}};
}
test('fresh setup requires matching PIN entries before offering device setup or completion',async()=>{
 const p=await page();assert.equal(p.node('pin-first').hidden,false);assert.equal(p.node('finish-setup').disabled,true);assert.equal(p.node('device-enrollment').hidden,true);
 p.node('setup-pin').value='1234';p.node('setup-pin-again').value='9876';await p.submit('create-device-pin');
 assert.equal(p.calls.filter(c=>c.p.op==='set').length,0);assert.match(p.node('device-error').textContent,/do not match/);
 p.node('setup-pin-again').value='1234';await p.submit('create-device-pin');
 assert.equal(p.node('device-enrollment').hidden,false);assert.equal(p.node('finish-setup').disabled,false);assert.equal(p.node('setup-pin').value,'');
 assert.equal(p.events.some(e=>e.action==='native-prompt'),false);
});
test('continuing with a PIN completes only local setup and never enables live approval',async()=>{
 const p=await page({pin:true});p.node('finish-setup').events.click();await tick();
 assert.equal(p.location.redirect,'/');assert.ok(p.calls.some(c=>c.url==='/api/space/complete-setup'));
 assert.equal(p.events.some(e=>e.action.startsWith('enable-')),false);
 assert.equal(p.calls.some(c=>/execute|prepare/.test(c.url)),false);
});
test('existing credentials and modes survive setup; unsupported browsers retain PIN continuation',async()=>{
 const p=await page({pin:true,registered:true,tested:true,modes:['live'],route:'/profile/settings'});
 assert.equal(p.node('device-enrollment').hidden,true);assert.equal(p.node('enable-live').hidden,true);assert.equal(p.node('setup-flow').hidden,true);assert.equal(p.node('change-pin-card').hidden,false);
 assert.equal(p.events.every(e=>e.action==='status'),true);
 const unsupported=await page({pin:true,supported:false});assert.equal(unsupported.node('unsupported-device').hidden,false);assert.equal(unsupported.node('finish-setup').disabled,false);
});
test('device test requests a native ceremony but never changes approval modes itself',async()=>{
 const p=await page({pin:true,registered:true});p.node('test-device').events.click();await tick();
 assert.ok(p.events.some(e=>e.action==='native-prompt'));assert.ok(p.events.some(e=>e.action==='test-verify'));
 assert.equal(p.events.some(e=>e.action.startsWith('enable-')),false);assert.equal(p.node('device-activation').hidden,false);
});
