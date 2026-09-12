/* Read-only local history. No broker, approval or submission endpoints. */
const activityNode=id=>document.getElementById(id);
const activityTitles={space:'Your space created',portfolio:'Latest portfolio saved',xray:'Latest Portfolio X-Ray saved',receipt:'Earlier saved order receipt'};
let activityBusy=false,activityOffset=null,activityGeneration=0;
function activityElement(tag,text,className){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e}
function activityDate(value){const d=new Date(value);return Number.isNaN(d.getTime())?'Date unavailable':d.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'})}
function activityCard(entry){
 const card=activityElement('article',undefined,'activity-card');
 const meta=activityElement('p',undefined,'activity-meta');
 meta.append(activityElement('span',entry.account==='personal'?'Personal':entry.account==='live'?'Live account':'Paper account','account-tag '+entry.account),activityElement('time',activityDate(entry.created_at)));
 card.append(meta);
 const titles={requested:'Submission requested · check outcome',completed:'Submission results recorded',not_submitted:'Stopped before submission',uncertain:'Submission outcome needs checking'};
 card.append(activityElement('h2',activityTitles[entry.kind]||titles[entry.phase]||'Saved activity'));
 if(entry.kind==='submission'){
  const text={requested:'Lens recorded your approval, but has no saved final outcome for this attempt. Check the broker before creating another plan.',completed:'These are the results saved when Lens finished its submission attempt. Working or partial orders may have changed since then.',not_submitted:'The final checks stopped this attempt before orders were sent.',uncertain:'The attempt ended without a confirmed complete outcome. Some orders may have reached the broker. Check IBKR before submitting again.'};
  card.append(activityElement('p',text[entry.phase]));
  card.append(activityElement('p',(entry.broker_account?'Broker account '+entry.broker_account+' · ':'')+(entry.method==='device'?'Approved with device verification':'Approved with Lens PIN'),'small'));
 }
 if(entry.kind==='receipt')card.append(activityElement('p','A receipt retained from earlier Lens activity. Its original approval method and exact account identifier are not recorded here.'));
 if(entry.estimated_date)card.append(activityElement('p','Date shown is when this file was last saved.','small'));
 if(['portfolio','xray'].includes(entry.kind))card.append(activityElement('p','This is your latest saved version; earlier edits were not recorded.'));
 if(entry.kind==='space')card.append(activityElement('p','Your personal space was created in this Lens installation.'));
 if((entry.orders||[]).length||(entry.results||[]).length){
  const details=activityElement('details');details.append(activityElement('summary','View orders and saved results'));
  if(entry.orders?.length){
   details.append(activityElement('h3','Reviewed orders'));
   const list=activityElement('ul');
   entry.orders.forEach(o=>list.append(activityElement('li',`${o.side} ${o.qty} ${o.ticker}${o.isin?' · '+o.isin:''} · ${o.side==='SELL'?'minimum':'maximum'} ${o.limit_price} ${o.currency||'EUR'} per share`)));details.append(list);
  }
  if(entry.results?.length){
   details.append(activityElement('h3','Results at the time'));
   const list=activityElement('ul');
   entry.results.forEach(r=>list.append(activityElement('li',`${r.side} ${r.qty} ${r.ticker} · ${r.status} · ${r.filled??0} filled${r.note?' · '+r.note:''}`)));details.append(list);
  }else details.append(activityElement('p','No per-order results are saved for this attempt.'));
  card.append(details);
 }
 return card;
}
async function loadActivity(more=false){
 const generation=++activityGeneration;
 activityBusy=true;activityNode('activity-more').disabled=true;
 activityNode('activity-status').textContent='Reading saved activity…';
 if(!more){activityNode('activity-list').replaceChildren();activityOffset=null;activityNode('activity-more').hidden=true}
 try{
  const response=await fetch('/api/activity',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account:activityNode('activity-filter').value,limit:30,offset:more?activityOffset:0})});
  const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Activity could not be read. Try again.');
  if(generation!==activityGeneration)return;
  data.entries.forEach(e=>activityNode('activity-list').append(activityCard(e)));
  activityOffset=data.next_offset;
  activityNode('activity-more').hidden=activityOffset===null;
  activityNode('activity-status').textContent=data.total?`${data.total} saved ${data.total===1?'record':'records'}.`:'No saved activity in this view yet.';
  activityNode('activity-warning').textContent=data.warnings.join(' ');
 }catch(e){if(generation===activityGeneration)activityNode('activity-status').textContent=e.message}
 finally{if(generation===activityGeneration){activityBusy=false;activityNode('activity-more').disabled=false}}
}
activityNode('activity-filter').addEventListener('change',()=>loadActivity());
activityNode('activity-refresh').addEventListener('click',()=>loadActivity());
activityNode('activity-more').addEventListener('click',()=>{if(!activityBusy&&activityOffset!==null)loadActivity(true)});
loadActivity();
