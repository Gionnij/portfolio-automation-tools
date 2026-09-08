// Presentation regressions using the real page script and an in-memory DOM.
// All requests are stubbed. This never opens a browser or contacts a broker.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'../investing.html'),'utf8').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/loadSnapshot\(\);\s*$/,'');
function page(){
  const nodes=new Map();
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',innerHTML:'',disabled:false,hidden:false,checked:false,setAttribute(){},addEventListener(){},close(){},classList:{toggle(){}},parentElement:{addEventListener(){}}});return nodes.get(id)};
  node('contribute').value='177.58';node('balance-sort').value='gap';
  const context=vm.createContext({Intl,Date,Number,JSON,Math,Boolean,String,Array,Object,Error,Promise,setTimeout,clearTimeout,window:{addEventListener(){}},document:{getElementById:node,querySelectorAll:()=>[]}});
  vm.runInContext(script,context);
  const run=s=>vm.runInContext(s,context);
  run(`DATA={has_report:true,account:'paper',nav:10000,snapshot_date:'2026-09-08',weights:[['4COP','0','1.5']],funds:{'4COP':{name:'Copper fund'}},pending:true,plan_id:'keep-this-approval',orders:[{ticker:'4COP',side:'BUY',qty:2,est_price:62}],results:[]};FRESH=true;INPUTS='unchanged';`);
  return {node,run};
}
const response=(shares=2,account='paper')=>({ok:true,account,read_at:'2026-09-08T10:00:00Z',nav:10124,cash:50.46,warnings:[],open_orders:0,holdings:[{ticker:'4COP',name:'Copper fund',shares,value:shares*62,current_pct:shares*62/10124*100,target_pct:1.5}]});

test('read-only refresh replaces an old zero-weight chart without changing approval or results',async()=>{
  const {node,run}=page();
  run('OUTCOMES={results:[],ok:true};');
  run(`request=async()=>(${JSON.stringify(response())});`);
  await run('refreshBalances()');
  assert.match(node('balance-content').innerHTML,/2 shares/);
  assert.match(node('balance-content').innerHTML,/1\.2%/);
  assert.doesNotMatch(node('balance-content').innerHTML,/Not currently held/);
  assert.match(node('balance-content').innerHTML,/Gateway holdings/);
  assert.equal(node('snapshot-value').textContent,'€10,124');
  assert.equal(run('DATA.weights[0][1]'),'0');
  assert.equal(run('DATA.plan_id'),'keep-this-approval');
  assert.equal(run('FRESH'),true);
  assert.equal(run('OUTCOMES.ok'),true);
});

test('completed submission refreshes chart automatically and keeps the fill receipt',async()=>{
  const {node,run}=page();
  node('confirm-phrase').value='EXECUTE';
  run(`selected=()=>[0];request=async action=>action==='execute'?{ok:true,results:[{ticker:'4COP',side:'BUY',qty:2,filled:2,status:'filled'}]}:(${JSON.stringify(response())});`);
  await run('executeOrders()');
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(node('balance-content').innerHTML,/2 shares/);
  assert.match(node('preview-card').innerHTML,/1 order filled/);
  assert.equal(run('OUTCOMES.results[0].filled'),2);
  assert.equal(run('FRESH'),false);
});

test('failed refresh retains last-known holdings and never falls back to the zero preview',async()=>{
  const {node,run}=page();
  run(`BALANCES=${JSON.stringify(response())};request=async()=>{throw Error('Gateway disconnected')};`);
  await run('refreshBalances()');
  assert.match(node('balance-content').innerHTML,/Last known Gateway holdings/);
  assert.match(node('balance-content').innerHTML,/2 shares/);
  assert.match(node('balance-content').innerHTML,/Gateway disconnected/);
});

test('broker figures from a different account cannot populate the chart',()=>{
  const {node,run}=page();
  run(`BALANCES=${JSON.stringify(response(2,'live'))};renderBalance();`);
  assert.doesNotMatch(node('balance-content').innerHTML,/2 shares/);
  assert.match(node('balance-content').innerHTML,/Saved preview/);
});

test('known shares remain visible when valuation is unavailable',()=>{
  const {node,run}=page();const partial=response();partial.nav=null;partial.holdings[0].value=null;partial.holdings[0].current_pct=null;
  run(`BALANCES=${JSON.stringify(partial)};renderBalance();`);
  assert.match(node('balance-content').innerHTML,/2 shares · valuation unavailable/);
  assert.match(node('balance-content').innerHTML,/Allocation unavailable/);
  assert.doesNotMatch(node('balance-content').innerHTML,/Not currently held/);
});

test('holdings work before the first investment preview exists',()=>{
  const {node,run}=page();
  run(`DATA={has_report:false};BALANCES=${JSON.stringify(response())};renderBalance();`);
  assert.match(node('balance-content').innerHTML,/2 shares/);
  assert.match(node('balance-content').innerHTML,/Copper fund/);
  assert.doesNotMatch(node('balance-content').innerHTML,/Connect the selected account/);
});
