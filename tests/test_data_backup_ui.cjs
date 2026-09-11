const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function page(response){
 const nodes=new Map(), calls=[], downloads=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,textContent:'',addEventListener(){}});return nodes.get(id)};
 const ctx=vm.createContext({
  document:{hidden:true,getElementById:node,body:{appendChild(){}},createElement:()=>({click(){downloads.push(this.download)},remove(){}})},
  window:{addEventListener(){}},setInterval(){},setTimeout(){},renderGatewayIndicator(){},
  URL:{createObjectURL:()=> 'blob:export',revokeObjectURL(){}},
  fetch:async(url,options)=>{calls.push({url,options});return response}
 });
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../data-backup.js'),'utf8'),ctx);
 return {node,calls,downloads,run:()=>vm.runInContext('downloadAllData()',ctx)};
}
test('download uses protected POST and only reports browser handoff',async()=>{
 const p=page({ok:true,headers:new Map([['Content-Type','application/zip'],['Content-Disposition','attachment; filename="lens-data-2026-09-11-120000.zip"']]),blob:async()=>({})});
 await p.run();
 assert.equal(p.calls[0].url,'/api/data/export');assert.equal(p.calls[0].options.method,'POST');
 assert.deepEqual(p.downloads,['lens-data-2026-09-11-120000.zip']);
 assert.match(p.node('download-status').textContent,/handed to your browser/);
 assert.equal(p.node('download-data').disabled,false);
});
test('busy response and unexpected content show errors and allow retry',async()=>{
 for(const response of [{ok:false,json:async()=>({error:'Investing action running'})},{ok:true,headers:new Map([['Content-Type','text/html']])}]){
  const p=page(response);await p.run();
  assert.equal(p.downloads.length,0);assert.ok(p.node('download-error').textContent);
  assert.equal(p.node('download-status').textContent,'');assert.equal(p.node('download-data').disabled,false);
 }
});
