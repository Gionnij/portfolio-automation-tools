const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../workspace.html'),'utf8');
const bootstrap=html.match(/\(async\(\)=>\{try\{const d=await api\('bootstrap'\)[\s\S]*?\}\)\(\);/)[0];
const reportCode=html.slice(html.indexOf('function renderReport()'),html.indexOf('\n',html.indexOf('function renderReport()')));
const runCode=html.slice(html.indexOf('async function runXray('),html.indexOf('\n',html.indexOf('async function runXray(')));
function result(){return {ok:true,analyzed_at:'2026-09-11T12:00:00Z',rows:[{isin:'FUND',weight:100}],stats:{funds:1,positions:10,holdings_coverage:100,classified:0,unknown:0,exposure_total:100},overlap:[],warnings:[],holdings:[],exposures:{country:[]}}}
function page(response){
 const nodes=new Map();
 const node=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'Run your first X-Ray',textContent:'',classList:{add(){},remove(){}}});return nodes.get(id)};
 const ctx=vm.createContext({$:node,api:async()=>response,rows:[],manual:[],report:null,revision:0,reportRevision:-1,exposure:'country',location:{hash:'#xray'},renderPortfolio(){},view(){},showError(e){throw e},dateLabel:String,esc:String,pct:String,policyHTML:()=>'',setExposure(){},renderHoldings(){}});
 vm.runInContext(reportCode+'\n'+runCode,ctx);
 return {node,run:s=>vm.runInContext(s,ctx),open:()=>vm.runInContext(bootstrap,ctx)};
}
test('a fresh page renders the saved X-Ray directly and never re-runs analysis',async()=>{
 const d={rows:result().rows,catalog:[],report:result(),report_stale:false};
 const first=page(d);await first.open();
 const reopened=page(d);await reopened.open();
 for(const p of [first,reopened]){
  assert.match(p.node('xray-content').innerHTML,/Underlying positions/);
  assert.doesNotMatch(p.node('xray-content').innerHTML,/Run your first X-Ray|previous snapshot/);
  assert.equal(p.run('reportRevision'),0);
 }
});
test('restored stale results remain visible with a notice',async()=>{
 const p=page({rows:result().rows,catalog:[],report:result(),report_stale:true});await p.open();
 assert.match(p.node('xray-content').innerHTML,/previous snapshot/);
 assert.match(p.node('xray-content').innerHTML,/Underlying positions/);
});
test('first-time visitors retain the empty state',async()=>{
 const p=page({rows:[],catalog:[],report:null});await p.open();
 assert.equal(p.node('xray-content').innerHTML,'Run your first X-Ray');
});
test('a successful update replaces stale results and tracks later allocation edits',async()=>{
 const p=page({rows:result().rows,catalog:[],report:result(),report_stale:true});await p.open();
 p.run(`api=async()=>(${JSON.stringify(result())})`);
 await p.run('runXray({classList:{add(){},remove(){}}})');
 assert.doesNotMatch(p.node('xray-content').innerHTML,/previous snapshot/);
 p.run('revision++;renderReport()');
 assert.match(p.node('xray-content').innerHTML,/previous snapshot/);
});
test('edits during an in-flight analysis keep its results marked as a previous snapshot',async()=>{
 const p=page({rows:result().rows,catalog:[],report:null});await p.open();
 p.run(`api=async()=>{revision++;return ${JSON.stringify(result())}}`);
 await p.run('runXray({classList:{add(){},remove(){}}})');
 assert.match(p.node('xray-content').innerHTML,/previous snapshot/);
});
