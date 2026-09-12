/* Home uses local snapshots; it never polls the broker or starts a plan. */
(async()=>{
 const node=id=>document.getElementById(id);
 try{
  const r=await fetch('/api/home',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}),d=await r.json();if(!r.ok||!d.ok)throw Error();
  node('home-next-title').textContent=d.next_step.title;node('home-next-copy').textContent=d.next_step.description;node('home-next-link').textContent=d.next_step.label;node('home-next-link').href=d.next_step.href;
  const titles={portfolio:'Portfolio saved',xray:'X-Ray saved',space:'Your space created',receipt:'Order receipt saved'};
  const phases={requested:'Submission outcome to check',uncertain:'Submission outcome to check',not_submitted:'Submission stopped',completed:'Order results recorded'};
  const list=node('home-recent-list');list.replaceChildren();
  for(const e of d.recent){const a=document.createElement('a'),title=document.createElement('span'),date=document.createElement('small');a.href='/profile/activity';title.textContent=(e.account==='personal'?'':e.account==='live'?'Live · ':'Paper · ')+(titles[e.kind]||phases[e.phase]||'Saved activity');const time=new Date(e.created_at);date.textContent=Number.isNaN(time.getTime())?'Saved locally':time.toLocaleDateString(undefined,{day:'numeric',month:'short'});a.append(title,date);list.append(a)}
  node('home-recent-status').textContent=d.warnings.length?'Some saved activity could not be read.':d.recent.length?'':'Your saved work will appear here.';
 }catch{node('home-recent-status').textContent='Recent activity is unavailable. You can still open your portfolio.'}
})();
