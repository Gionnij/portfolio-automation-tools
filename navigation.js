/* Profile identity comes from the local installation, never a broker. */
(async()=>{
 try{
  const r=await fetch('/api/space/bootstrap',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  const d=await r.json();if(!r.ok||!d.ok)return;
  const name=d.profile?.first_name||'Your profile';
  for(const id of ['lens-profile-name','lens-heading-name']){const el=document.getElementById(id);if(el)el.textContent=name}
  const avatar=document.getElementById('lens-avatar');if(avatar)avatar.textContent=d.profile?.first_name?Array.from(name)[0].toUpperCase():'◦';
 }catch{/* Keep the navigation available if the profile cannot be read. */}
})();
