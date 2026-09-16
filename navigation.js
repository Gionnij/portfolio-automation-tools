/* Profile identity comes from the local installation, never a broker. */
(async()=>{
 try{
  const r=await fetch('/api/space/bootstrap',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  const d=await r.json();if(!r.ok||!d.ok)return;
  const name=d.profile?.first_name||'Your profile';
  for(const id of ['lens-profile-name']){const el=document.getElementById(id);if(el)el.textContent=name}
  const avatar=document.getElementById('lens-avatar');if(avatar)avatar.textContent=d.profile?.first_name?Array.from(name)[0].toUpperCase():'◦';
 }catch{/* Keep the navigation available if the profile cannot be read. */}
})();

// Reuse investing/workspace connection readers so there is only one poller per page.
if(!['/invest','/portfolio/holdings','/portfolio','/setup'].includes(document.body.dataset.lensRoute)){
 refreshLensConnection();
 window.addEventListener('focus',refreshLensConnection);
 window.setInterval(()=>{if(!document.hidden)refreshLensConnection()},30000);
}
for(const id of ['lens-menu','gateway-menu']){
 const menu=document.getElementById(id);
 menu?.addEventListener('toggle',()=>{if(menu.open){const other=document.getElementById(id==='lens-menu'?'gateway-menu':'lens-menu');if(other)other.open=false;}});
}
document.addEventListener('click',event=>{const menu=document.getElementById('lens-menu');if(menu?.open&&!menu.contains(event.target))menu.open=false;});
document.addEventListener('keydown',event=>{const menu=document.getElementById('lens-menu');if(event.key==='Escape'&&menu?.open){menu.open=false;document.getElementById('lens-menu-toggle').focus();}});
