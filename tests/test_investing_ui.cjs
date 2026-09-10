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
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',innerHTML:'',disabled:false,hidden:false,checked:false,setAttribute(){},addEventListener(){},close(){this.open=false},showModal(){this.open=true},focus(){},classList:{toggle(){}},parentElement:{addEventListener(){}}});return nodes.get(id)};
  node('contribute').value='177.58';node('balance-sort').value='held';
  const context=vm.createContext({Intl,Date,Number,JSON,Math,Boolean,String,Array,Object,Error,Promise,setTimeout,clearTimeout,window:{addEventListener(){}},document:{getElementById:node,querySelectorAll:()=>[],querySelector:()=>node('options')}});
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
  assert.equal(node('snap-invested').textContent,'€10,124');
  assert.equal(node('snap-cash').textContent,'€50');
  assert.equal(run('DATA.weights[0][1]'),'0');
  assert.equal(run('DATA.plan_id'),'keep-this-approval');
  assert.equal(run('FRESH'),true);
  assert.equal(run('OUTCOMES.ok'),true);
});

test('completed submission refreshes chart automatically and keeps the fill receipt',async()=>{
  const {node,run}=page();
  node('confirm-phrase').value='2468';
  run(`selected=()=>[0];REVIEW={allowed:true,account:'paper',plan_id:DATA.plan_id,selection:'[0]'};request=async action=>action==='execute'?{ok:true,results:[{ticker:'4COP',side:'BUY',qty:2,filled:2,status:'filled'}]}:(${JSON.stringify(response())});`);
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

test('default sorting uses held value, then target, then ticker, with empty positions last',()=>{
  const {run}=page();
  const rows=[{ticker:'EMPTY-A',value:0,shares:0,target:1},{ticker:'SMALL',value:10,shares:1,target:1},
    {ticker:'EMPTY-B',value:0,shares:0,target:5},{ticker:'BBB',value:500,shares:5,target:10},
    {ticker:'AAA',value:500,shares:10,target:10},{ticker:'HIGH-TARGET',value:500,shares:2,target:20}];
  const order=run(`(${JSON.stringify(rows)}).sort((a,b)=>compareHoldings(a,b,'held')).map(r=>r.ticker).join(',')`);
  assert.equal(order,'HIGH-TARGET,AAA,BBB,SMALL,EMPTY-B,EMPTY-A');
});

test('underfunded review shows exact shortfall, offers XEON, and cannot send',async()=>{
  const {node,run}=page();
  run(`selected=()=>[0];request=async()=>({ok:true,account:'paper',plan_id:DATA.plan_id,funding:{allowed:false,reason:'budget',cash:50.46,cash_budget:600,shortfall:549.54,budget_shortfall:549.54,xeon_can_replace:true,replacement_deploy:549.54}});`);
  await run('openReview()');
  assert.match(node('review-body').innerHTML,/€549.54/);
  assert.match(node('review-body').innerHTML,/cannot send orders/);
  assert.match(node('review-body').innerHTML,/Use XEON instead/);
  assert.doesNotMatch(node('review-body').innerHTML,/Send paper orders|confirm-phrase/);
  node('confirm-phrase').value='2468';
  run("request=async()=>{throw Error('Must not send')} ");
  await run('executeOrders()');
  assert.equal(run('FRESH'),true);
});

test('XEON replacement preserves total planned funding and requires a new preview',()=>{
  const {node,run}=page();
  run(`REVIEW={allowed:false,account:'paper',plan_id:DATA.plan_id,xeon_can_replace:true,cash:50.46,replacement_deploy:749.54};`);
  run('useXeonForShortfall()');
  assert.equal(Number(node('contribute').value),50.46);
  assert.equal(Number(node('deploy').value),749.54);
  assert.equal(run('FRESH'),false);
  assert.equal(run('REVIEW'),null);
});

test('funded review exposes confirmation only after successful funding check',async()=>{
  const {node,run}=page();
  run(`selected=()=>[0];request=async()=>({ok:true,account:'paper',plan_id:DATA.plan_id,funding:{allowed:true,reason:'funded'}});`);
  await run('openReview()');
  assert.match(node('review-body').innerHTML,/Send paper orders/);
  assert.equal(run('reviewMatches()'),true);
  node('confirm-phrase').value='2468';run('checkConfirm()');
  assert.equal(node('send-button').disabled,false);
  run('REVIEW=null;checkConfirm()');
  assert.equal(node('send-button').disabled,true);
});

test('a funding change at submission returns to a blocked review without losing the preview',async()=>{
  const {node,run}=page();node('confirm-phrase').value='2468';
  run(`selected=()=>[0];REVIEW={allowed:true,account:'paper',plan_id:DATA.plan_id,selection:'[0]'};request=async()=>({ok:false,not_submitted:true,funding_blocked:true,funding:{allowed:false,reason:'budget',cash:20,cash_budget:600,shortfall:580}});`);
  await run('executeOrders()');
  assert.equal(run('FRESH'),true);
  assert.equal(run('DATA.pending'),true);
  assert.equal(run('OUTCOMES'),null);
  assert.match(node('review-body').innerHTML,/€580.00/);
  assert.equal(run('reviewMatches()'),false);
});

/* The approval gate is a numeric PIN. Two guards protect a submission: the
   page refuses to enable the button unless the entry LOOKS like a PIN, and the
   local app refuses the submission unless the PIN actually verifies. Both are
   exercised here - the second one is what stands between a wrong guess and a
   real order. */

test('a PIN can be set from the review dialog and unlocks the send button',async()=>{
  const {node,run}=page();
  run(`selected=()=>[0];REVIEW={allowed:true,account:'paper',plan_id:DATA.plan_id,selection:'[0]'};`);
  run(`PIN_SET=false;request=async(action,p)=>action==='pin'&&p.op==='set'?{ok:true,set:true}:{ok:true};`);
  node('pin-new').value='2468';node('pin-again').value='2468';
  await run('savePin()');
  assert.equal(run('PIN_SET'),true);
  assert.doesNotMatch(node('pin-msg').textContent,/not match|4 to 12/);
  node('confirm-phrase').value='2468';run('checkConfirm()');
  assert.equal(node('send-button').disabled,false);
});

test('an entry that is not a PIN never enables the send button',()=>{
  const {node,run}=page();
  run(`selected=()=>[0];REVIEW={allowed:true,account:'paper',plan_id:DATA.plan_id,selection:'[0]'};`);
  for(const bad of ['','EXECUTE','12','abcd','12a4','1234567890123']){
    node('confirm-phrase').value=bad;run('checkConfirm()');
    assert.equal(node('send-button').disabled,true,`"${bad}" must not unlock the button`);
  }
  node('confirm-phrase').value='2468';run('checkConfirm()');
  assert.equal(node('send-button').disabled,false);
});

test('a wrong PIN is refused by the local app and places no orders',async()=>{
  const {node,run}=page();
  node('confirm-phrase').value='9999';
  run(`selected=()=>[0];REVIEW={allowed:true,account:'paper',plan_id:DATA.plan_id,selection:'[0]'};`);
  run(`sent=null;request=async(action,p)=>{if(action!=='execute')return {ok:true};sent=p;`
     +`return {ok:false,not_submitted:true,log:'the PIN is not correct'}};`);
  await run('executeOrders()');
  assert.equal(run('sent.confirm'),'9999');          // the entry reaches the app
  assert.equal(run('OUTCOMES.ok'),false);
  assert.equal(run('OUTCOMES.notSubmitted'),true);   // nothing reached the broker
  assert.equal(run('OUTCOMES.results.length'),0);
  assert.equal(run('DATA.results.length'),0);
});

test('the right PIN submits and records the fills',async()=>{
  const {node,run}=page();
  node('confirm-phrase').value='2468';
  run(`selected=()=>[0];REVIEW={allowed:true,account:'paper',plan_id:DATA.plan_id,selection:'[0]'};`);
  run(`sent=null;request=async(action,p)=>{if(action!=='execute')return {ok:true};sent=p;`
     +`return {ok:true,results:[{ticker:'4COP',side:'BUY',qty:2,filled:2,status:'filled'}]}};`);
  await run('executeOrders()');
  assert.equal(run('sent.confirm'),'2468');
  assert.equal(run('OUTCOMES.ok'),true);
  assert.equal(run('OUTCOMES.results[0].filled'),2);
});
