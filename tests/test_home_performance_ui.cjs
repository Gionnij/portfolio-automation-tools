const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../home-performance.js'),'utf8');
function page(){
 const nodes=new Map(),calls=[],events={};
 const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',hidden:false,disabled:false,dataset:{},addEventListener(){}});return nodes.get(id)};
 const ctx=vm.createContext({Intl,Date,Number,JSON,Error,document:{getElementById:node},window:{addEventListener:(k,f)=>events[k]=f},fetch:async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return {ok:true,json:async()=>({ok:true,account:'live',read_at:new Date().toISOString(),nav:1100,performance:{cost_basis:1000,unrealized_pnl:100,unrealized_pct:10}})}}});
 vm.runInContext(source,ctx);
 return {node,calls,events,run:s=>vm.runInContext(s,ctx)};
}
test('Home displays open-holding value, cost and signed gain from a read-only balance request',async()=>{
 const p=page();p.events['lens-connection']({detail:{state:'connected',mode:'live',session_key:'live1'}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(p.node('home-holdings-value').textContent,'€1,100.00');assert.equal(p.node('home-gain-loss').textContent,'+€100.00');assert.equal(p.node('home-gain-percent').textContent,'+10%');
 assert.deepEqual(p.calls,[{url:'/api/balances',body:{account:'live'}}]);
 p.run("homeReading.performance={cost_basis:1000,unrealized_pnl:-100,unrealized_pct:-10};renderHomePerformance()");
 assert.equal(p.node('home-gain-loss').textContent,'-€100.00');assert.equal(p.node('home-gain-card').dataset.direction,'loss');
});
test('unknown cost is not zero; a failed same-account refresh labels the last known reading',async()=>{
 const p=page();p.run("homeAccount='live';homeReading={nav:1000,read_at:'2026-09-14T12:00:00Z',performance:{cost_basis:null,unrealized_pnl:null,unrealized_pct:null}};renderHomePerformance()");
 assert.equal(p.node('home-gain-loss').textContent,'—');assert.match(p.node('home-metrics-error').textContent,/unavailable/);
 p.run("fetch=async()=>{throw Error('Connection failed')}");await p.run('refreshHomePerformance()');
 assert.match(p.node('home-metrics-status').textContent,/Last known/);assert.equal(p.node('home-holdings-value').textContent,'€1,000.00');
});
test('account/session changes discard old values and late responses cannot restore them',async()=>{
 const p=page();p.run("fetch=()=>new Promise(resolve=>{pending=resolve});followHomeConnection({state:'connected',mode:'live',session_key:'a'})");
 p.run("followHomeConnection({state:'disconnected'})");
 p.run("pending({ok:true,json:async()=>({ok:true,account:'live',nav:999,performance:{unrealized_pnl:42}})})");
 await new Promise(resolve=>setImmediate(resolve));assert.equal(p.node('home-holdings-value').textContent,'—');assert.equal(p.run('homeReading'),null);
 p.run("homeAccount='live';homeSession='a';homeReading={nav:999};followHomeConnection({state:'connected',mode:'live',session_key:'b'})");assert.equal(p.node('home-holdings-value').textContent,'—');
});
