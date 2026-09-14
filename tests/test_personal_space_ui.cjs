const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../personal-space.js'),'utf8');
const reply=(profile=null)=>({ok:true,profile,summary:{portfolio_saved:true,fund_count:2,saved_at:'2026-09-12T09:00:00Z',manual_available:true}});
const profile={first_name:'Ada',version:1,created_at:'2026-09-12'};
async function page(responses,hash=''){
  const nodes=new Map(),calls=[],location={hash,replace(value){this.redirect=value}};
  const node=id=>{if(!nodes.has(id))nodes.set(id,{hidden:['home','welcome','load-recovery'].includes(id),textContent:'',value:'',disabled:false,events:{},focus(){this.focused=true},addEventListener(event,fn){this.events[event]=fn}});return nodes.get(id)};
  const context=vm.createContext({document:{getElementById:node},location,fetch:async(url,options)=>{
    calls.push({url,payload:JSON.parse(options.body)});
    const result=responses.shift();if(result instanceof Error)throw result;
    return {ok:result.ok,json:async()=>result};
  }});
  vm.runInContext(source,context);
  await new Promise(resolve=>setImmediate(resolve));
  return {node,calls,location,run:code=>vm.runInContext(code,context),submit:async id=>node(id).events.submit({preventDefault(){}})};
}
test('first visit stays on welcome until save succeeds, then opens remembered home',async()=>{
  const p=await page([reply(),reply(profile)]);
  assert.equal(p.node('welcome').hidden,false);assert.equal(p.node('home').hidden,true);
  p.node('first-name').value='Ada';await p.submit('create-space');
  assert.equal(p.node('welcome').hidden,true);assert.equal(p.node('home-title').textContent,'Welcome back, Ada.');
  assert.equal(p.node('home-title').focused,true);
  assert.deepEqual(p.calls.map(c=>c.url),['/api/space/bootstrap','/api/space/create']);
  assert.deepEqual(p.calls[1].payload,{first_name:'Ada'});
});
test('return visits open home directly and names render as text',async()=>{
  const p=await page([reply({...profile,first_name:'<img src=x onerror=alert(1)>'}),reply({...profile,first_name:''})]);
  assert.equal(p.node('welcome').hidden,true);
  assert.equal(p.node('home-title').textContent,'Welcome back, <img src=x onerror=alert(1)>.');
  assert.equal(p.node('edit-profile').events.submit,undefined);
});
test('failed reads offer recovery without inviting profile overwrite',async()=>{
  const p=await page([Error('Profile unavailable'),reply(profile)]);
  assert.equal(p.node('home').hidden,true);assert.equal(p.node('welcome').hidden,true);
  assert.equal(p.node('load-recovery').hidden,false);assert.equal(p.node('space-error').textContent,'Profile unavailable');
  await p.run('loadSpace()');assert.equal(p.node('load-recovery').hidden,true);assert.equal(p.node('home').hidden,false);
});
test('failed saves retain input and allow retry; double submits are ignored',async()=>{
  const p=await page([reply(),{ok:false,error:'Disk is full'}]);
  p.node('first-name').value='Ada';await p.submit('create-space');
  assert.equal(p.node('welcome').hidden,false);assert.equal(p.node('first-name').value,'Ada');
  assert.equal(p.node('create-button').disabled,false);assert.equal(p.node('space-error').textContent,'Disk is full');
  p.node('create-button').disabled=true;await p.submit('create-space');assert.equal(p.calls.length,2);
});
test('legacy research bookmarks go to workspace without a profile API call',async()=>{
  for(const hash of ['#portfolio','#xray','#sources']){
    const p=await page([],hash);assert.equal(p.location.redirect,hash==='#sources'?'/profile/data/sources':'/portfolio'+hash);assert.equal(p.calls.length,0);
  }
});

test('new and interrupted spaces continue to security setup; legacy spaces do not',async()=>{
 const created=await page([reply(),reply({...profile,setup_complete:false})]);
 await created.submit('create-space');assert.equal(created.location.redirect,'/setup');
 const resumed=await page([reply({...profile,setup_complete:false})]);assert.equal(resumed.location.redirect,'/setup');
 const existing=await page([reply(profile)]);assert.equal(existing.location.redirect,undefined);
});
