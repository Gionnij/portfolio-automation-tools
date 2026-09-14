const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../workspace.html'),'utf8');
const script=html.slice(html.indexOf('let holdings=null'),html.indexOf('function toggleRemoveMode()'));
function page(){
 const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',dataset:{},setAttribute(){},disabled:false,hidden:false});return nodes.get(id)};
 const ctx=vm.createContext({location:{pathname:"/portfolio"},Date,Number,Object,Math,$:node,rows:[{isin:'FUND',weight:100}],esc:String,pct:v=>v+'%',renderPortfolio(){},window:{addEventListener(){}},document:{hidden:false,getElementById:node,addEventListener(){},body:{classList:{toggle(){}}},querySelectorAll:()=>[]},setInterval(){}});
 vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../shell.js'),'utf8'),ctx);
 vm.runInContext(script,ctx);return {node,run:s=>vm.runInContext(s,ctx)};
}
function result(mode='paper'){return {holdings:{FUND:{value_eur:200,shares:10}},read_at:'2026-09-10T10:00:00Z',account:mode,connection:{state:'connected',mode,message:'Connected to your '+mode+' account.'}}}
test('automatic view follows live account with clear labeling',async()=>{
 const {node,run}=page();run(`api=async()=>(${JSON.stringify(result('live'))})`);await run('loadHoldings()');
 assert.match(node('account-label').textContent,/Live account/);
 assert.match(run('holdingsNote()'),/Live holdings/);
 assert.match(run('currentCell(0)'),/100%/);
});
test('disconnection clears previous holdings and shows one friendly status',async()=>{
 const {node,run}=page();run(`api=async()=>(${JSON.stringify(result())})`);await run('loadHoldings()');
 run(`api=async()=>({holdings:null,connection:{state:'disconnected',message:'Open IB Gateway and log in.'}})`);await run('loadHoldings()');
 assert.equal(run('holdings'),null);assert.match(node('gateway-detail').textContent,/Open IB Gateway/);
 assert.equal(run('currentCell(0)'),'<span class="cur-none">—</span>');
 assert.equal(run('holdingsAt'),'');
});
test('Gateway switching replaces live holdings with paper without a view selector',async()=>{
 const {run}=page();run(`api=async()=>(${JSON.stringify(result('live'))})`);await run('loadHoldings()');
 run(`api=async()=>(${JSON.stringify(result('paper'))})`);await run('loadHoldings()');
 assert.equal(run('holdingsAccount'),'paper');assert.doesNotMatch(html,/gateway-mode|changeHoldingsAccount/);
});
test('transport failures never repeat raw errors in the table',async()=>{
 const {node,run}=page();run(`api=async()=>{throw Error('server error: [Errno 61] 127.0.0.1:4002')}`);await run('loadHoldings()');
 assert.doesNotMatch(node('gateway-detail').textContent,/Errno|127.0.0.1|server error/);
 assert.equal(run('currentCell(0)'),'<span class="cur-none">—</span>');
});
test('unpriced holdings are unknown rather than zero',async()=>{
 const {run}=page();const d=result();d.holdings.FUND.value_eur=null;
 run(`api=async()=>(${JSON.stringify(d)})`);await run('loadHoldings()');
 assert.match(run('holdingsNote()'),/could not be valued/);assert.doesNotMatch(run('currentCell(0)'),/Not held|100%/);
});
test('ambiguous connections ask for a choice without retaining any holdings',async()=>{
 const {node,run}=page();run(`api=async()=>({holdings:null,connection:{state:'multiple_connections',message:'Keep one account connected in IB Gateway.'}})`);await run('loadHoldings()');
 assert.match(node('gateway-title').textContent,/Two Gateways/);assert.equal(run('holdings'),null);
});

test('connection indicator sits outside all research views',()=>{
 assert.ok(html.indexOf('id="account-label"')<html.indexOf('<section id="view-portfolio"'));
});

test('profile data sources does not fetch brokerage holdings',async()=>{
 const {run}=page();run("location.pathname='/profile/data/sources';api=()=>{throw Error('Broker call')}");
 await run('loadHoldings()');assert.equal(run('holdings'),null);
});
