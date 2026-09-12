const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../activity.js'),'utf8');
function element(){return {textContent:'',children:[],hidden:false,disabled:false,value:'all',events:{},append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},addEventListener(k,fn){this.events[k]=fn}}}
const tick=()=>new Promise(r=>setImmediate(r));
async function page(replies){
 const nodes=new Map(),calls=[];const node=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
 const ctx=vm.createContext({document:{getElementById:node,createElement:element},fetch:async(url,options)=>{calls.push({url,payload:JSON.parse(options.body)});const reply=await replies.shift();return{ok:reply.ok,json:async()=>reply}}});
 vm.runInContext(source,ctx);await tick();return{node,calls,run:s=>vm.runInContext(s,ctx)};
}
const reply=(entries=[],extra={})=>({ok:true,entries,total:entries.length,next_offset:null,warnings:[],...extra});
function text(e){return e.textContent+' '+e.children.map(text).join(' ')}
test('saved statuses and untrusted fields are text; there is no approval control',async()=>{
 const p=await page([reply([{kind:'submission',phase:'uncertain',account:'live',created_at:'2026-09-12T10:00:00Z',broker_account:'U123',method:'device',orders:[{side:'BUY',qty:2,ticker:'<script>bad()</script>',limit_price:25,currency:'EUR'}],results:[{side:'BUY',qty:2,ticker:'TEST',status:'working',filled:0}]}])]);
 const card=p.node('activity-list').children[0];assert.match(text(card),/Some orders may have reached/);assert.match(text(card),/working/);assert.match(text(card),/<script>bad\(\)<\/script>/);
 assert.equal(card.innerHTML,undefined);assert.deepEqual(p.calls.map(c=>c.url),['/api/activity']);
});
test('empty views, filters and pagination use only saved activity',async()=>{
 const entry={kind:'portfolio',account:'personal',created_at:'2026-09-12T10:00:00Z'};
 const p=await page([reply(),reply([entry],{total:2,next_offset:30}),reply([entry],{total:2})]);
 assert.match(p.node('activity-status').textContent,/No saved activity/);
 p.node('activity-filter').value='personal';await p.run('loadActivity()');await p.run('loadActivity(true)');
 assert.equal(p.calls[1].payload.account,'personal');assert.equal(p.calls[2].payload.offset,30);
 assert.equal(p.node('activity-list').children.length,2);assert.equal(p.node('activity-more').hidden,true);
});
test('late responses cannot replace a newer filter and read errors remain visible',async()=>{
 let resolve;const delayed=new Promise(r=>resolve=r);
 const p=await page([delayed,reply([]),{ok:false,error:'Saved activity unavailable'}]);
 p.node('activity-filter').value='live';await p.run('loadActivity()');resolve(reply([{kind:'space',account:'personal',created_at:'2026-09-12'}]));await tick();
 assert.equal(p.node('activity-list').children.length,0);
 await p.run('loadActivity()');assert.match(p.node('activity-status').textContent,/unavailable/);
});
