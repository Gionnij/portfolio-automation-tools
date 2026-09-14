const profileNode=id=>document.getElementById(id);
const profileRoute=document.body.dataset.lensRoute;
const profilePane=profileRoute==='/invest/rules'?'rules':profileRoute.endsWith('/appearance')?'appearance':profileRoute.endsWith('/connections')?'connections':'details';
profileNode('profile-'+profilePane).hidden=false;
let profileExists=false;
async function profileRequest(url,p={}){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||d.log||'This could not be saved. Try again.');return d}
async function loadProfile(){try{const d=await profileRequest('/api/space/bootstrap');profileExists=!!d.profile;profileNode('profile-form').hidden=!profileExists;profileNode('profile-create').hidden=profileExists;profileNode('profile-first-name').value=d.profile?.first_name||''}catch(e){profileNode('profile-error').textContent=e.message;profileNode('profile-form').hidden=true}}
profileNode('profile-form').addEventListener('submit',async event=>{
 event.preventDefault();const button=profileNode('profile-save');if(button.disabled||!profileExists)return;button.disabled=true;profileNode('profile-error').textContent='';
 try{const d=await profileRequest('/api/space/update',{first_name:profileNode('profile-first-name').value});profileNode('profile-status').textContent='Name saved.';for(const id of ['lens-profile-name','lens-heading-name']){const el=profileNode(id);if(el)el.textContent=d.profile.first_name||'Your profile'}const avatar=profileNode('lens-avatar');if(avatar)avatar.textContent=d.profile.first_name?Array.from(d.profile.first_name)[0].toUpperCase():'◦'}catch(e){profileNode('profile-error').textContent=e.message}finally{button.disabled=false}
});
profileNode('check-connection').addEventListener('click',async()=>{
 const button=profileNode('check-connection');if(button.disabled)return;button.disabled=true;profileNode('connection-status').textContent='Checking IB Gateway…';profileNode('connection-error').textContent='';
 try{const d=await profileRequest('/api/gateway'),c=d.connection;profileNode('connection-status').textContent=c?.state==='connected'?(c.mode==='live'?'Live account · real money':'Paper account · virtual money')+(c.read_only?' · Read-only':' · Connected'):(c?.message||'No single Gateway connection is ready.')}catch(e){profileNode('connection-status').textContent='Connection unavailable.';profileNode('connection-error').textContent=e.message}finally{button.disabled=false}
});
if(profilePane==='details')loadProfile();
