const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
function page(){
 const nodes=new Map(),events={};
 const node=id=>{if(!nodes.has(id))nodes.set(id,{dataset:{},textContent:'',hidden:false,disabled:false,open:false,contains:target=>target==='inside',focus(){this.focused=true},setAttribute(k,v){this[k]=v}});return nodes.get(id)};
 const ctx=vm.createContext({document:{getElementById:node,body:{classList:{toggle(){}}},addEventListener:(type,fn)=>{events[type]=fn}}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../shell.js'),'utf8'),ctx);
 return {node,events,run:s=>vm.runInContext(s,ctx)};
}
test('live and paper states stay compact and never open the details automatically',()=>{
 const {node,run}=page();
 for(const mode of ['live','paper']){
  run(`renderGatewayIndicator({state:'connected',mode:'${mode}',message:'Connection details'})`);
  assert.equal(node('gateway-menu').open,false);
  assert.equal(node('gateway-menu').dataset.state,mode);
  assert.equal(node('account-label').textContent,mode==='live'?'Live account':'Paper account');
 }
});
test('Escape and outside click close the menu; inside clicks leave it open',()=>{
 const {node,events,run}=page();run('openGatewayMenu()');
 assert.equal(node('gateway-menu').open,true);
 events.click({target:'inside'});assert.equal(node('gateway-menu').open,true);
 events.keydown({key:'Escape'});assert.equal(node('gateway-menu').open,false);assert.equal(node('gateway-toggle').focused,true);
 run('openGatewayMenu()');events.click({target:'outside'});assert.equal(node('gateway-menu').open,false);
});
test('read-only and disconnected errors are explained inside the indicator',()=>{
 const {node,run}=page();run("renderGatewayIndicator({state:'connected',mode:'paper',read_only:true})");
 assert.match(node('account-label').textContent,/Paper account · Read-only/);
 assert.match(node('gateway-detail').textContent,/Untick Read-Only API/);
 assert.equal(node('gateway-menu').dataset.state,'attention');
 run("renderGatewayIndicator({state:'disconnected',message:'Sign in to Gateway.'})");
 assert.equal(node('account-label').textContent,'Disconnected');
 assert.equal(node('gateway-detail').textContent,'Sign in to Gateway.');
});
test('all pages load the same frame and connection component',()=>{
 for(const file of ['workspace.html','investing.html']){
  const html=fs.readFileSync(path.join(__dirname,'..',file),'utf8');
  assert.match(html,/href="\/shell.css"/);assert.match(html,/src="\/shell.js"/);
  assert.match(html,/<details class="gateway-menu"/);
  assert.doesNotMatch(html,/class="gateway-bar"|id="gateway-banner"/);
 }
});
