const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
function page(saved=null,dark=false,blocked=false){
  const events={},windowEvents={},media={matches:dark,addEventListener:(name,fn)=>{media.change=fn}};
  const select={value:'system',addEventListener:(name,fn)=>{select.change=fn}};
  const root={dataset:{}};
  const storage={getItem(){if(blocked)throw Error('blocked');return saved},setItem(key,value){if(blocked)throw Error('blocked');saved=value}};
  const context={window:{matchMedia:()=>media,addEventListener:(name,fn)=>{windowEvents[name]=fn}},localStorage:storage,
    document:{documentElement:root,getElementById:()=>select,addEventListener:(name,fn)=>{events[name]=fn}}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../theme.js'),'utf8'),context);
  events.DOMContentLoaded();
  return {root,select,media,windowEvents,saved:()=>saved,choose(value){select.change({target:{value}})}};
}
test('first visit follows system appearance and responds to changes',()=>{
  const p=page(null,true);assert.equal(p.root.dataset.theme,'dark');assert.equal(p.select.value,'system');
  p.media.matches=false;p.media.change();assert.equal(p.root.dataset.theme,'light');
});
test('manual override persists, ignores system changes, and can return to System',()=>{
  const p=page();p.choose('dark');assert.equal(p.saved(),'dark');
  p.media.change();assert.equal(p.root.dataset.theme,'dark');
  assert.equal(page(p.saved()).root.dataset.theme,'dark');
  p.choose('light');p.media.matches=true;p.media.change();assert.equal(p.root.dataset.theme,'light');
  p.choose('system');assert.equal(p.root.dataset.theme,'dark');assert.equal(p.saved(),'system');
});
test('invalid preferences and unavailable storage still allow theme changes',()=>{
  assert.equal(page('invalid',true).select.value,'system');
  const p=page(null,true,true);p.choose('light');assert.equal(p.root.dataset.theme,'light');
});
test('other tabs synchronize changes and clearing storage restores system mode',()=>{
  const p=page('dark');p.windowEvents.storage({key:'lens-theme',newValue:'light'});
  assert.equal(p.root.dataset.theme,'light');assert.equal(p.select.value,'light');
  p.windowEvents.storage({key:null,newValue:null});assert.equal(p.select.value,'system');
});
test('every app page initializes theme in its head and exposes the same control',()=>{
  for(const file of ['workspace.html','investing.html','data-backup.html','personal-space.html','device-approval.html','activity.html']){
    const html=fs.readFileSync(path.join(__dirname,'..',file),'utf8');
    assert.match(html,/<head>[\s\S]*?<script src="\/theme.js"><\/script>[\s\S]*?<\/head>/);
    assert.match(html,/<select id="theme-select"[^>]+aria-label="Color theme"/);
    for(const value of ['system','light','dark'])assert.ok(html.includes(`<option value="${value}">`));
  }
});
