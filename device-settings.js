const deviceNode=id=>document.getElementById(id);
let deviceBusy=false;
const deviceSetup=document.body.dataset.lensRoute==='/setup';
let setupPinReady=false;
async function deviceRefresh(){
 const state=await LensDevice.call('status');
 const response=await fetch('/api/pin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({op:'status'})});
 const pin=await response.json();if(!response.ok||!pin.ok)throw Error('Could not check your PIN settings.');
 const supported=LensDevice.available();
 deviceNode('unsupported-device').hidden=supported;
 deviceNode('pin-first').hidden=pin.set;
 deviceNode('device-enrollment').hidden=!supported||!pin.set||state.registered;
 deviceNode('device-test').hidden=!supported||!state.registered||state.tested;
 deviceNode('device-activation').hidden=!supported||!state.tested;
 deviceNode('device-reset').hidden=!state.registered||!!state.modes.length;
 deviceNode('device-status').textContent=state.tested?'Device verification tested. Choose paper and live activation below.':state.registered?'Device registered. Complete the no-trade test.':'No device credential registered yet.';
 deviceNode('approval-modes').innerHTML=['paper','live'].map(mode=>'<div class="status-line"><strong>'+ (mode==='paper'?'Paper':'Live')+' orders:</strong> '+(state.modes.includes(mode)?'Device approval required':'Lens PIN required')+'</div>').join('');
 deviceNode('enable-paper').hidden=state.modes.includes('paper');
 deviceNode('enable-live').hidden=state.modes.includes('live');
 deviceNode('disable-device').hidden=!state.modes.length;
 deviceNode('retry-device').hidden=true;
 setupPinReady=pin.set;
 deviceNode('setup-flow').hidden=!deviceSetup;
 deviceNode('setup-finish').hidden=!deviceSetup;
 deviceNode('finish-setup').disabled=!pin.set;
 deviceNode('finish-setup').textContent=state.modes.length?'Open my space':'Use PIN for now';
 deviceNode('change-pin-card').hidden=deviceSetup||!pin.set;
 if(deviceSetup){
  document.querySelector('.hero').hidden=true;
  deviceNode('device-test').hidden=!supported||!state.registered||state.tested;
  for(const [id,on] of [['pin',!pin.set],['device',pin.set&&!state.tested],['modes',state.tested]])deviceNode('setup-step-'+id).classList.toggle('current',on);
  deviceNode('device-status').textContent=!pin.set?'First, choose a PIN you can remember.':!state.tested?'Your PIN is saved. Set up and test device verification next, or continue with your PIN.':'Device verification tested. Choose paper and live approval separately, or keep using your PIN.';
 }

}
async function deviceAction(fn){
 if(deviceBusy)return;deviceBusy=true;
 deviceNode('device-error').textContent='';deviceNode('device-success').textContent='';
 document.querySelectorAll('button').forEach(b=>b.disabled=true);
 try{await fn();await deviceRefresh()}
 catch(e){deviceNode('device-error').textContent=e.message;deviceNode('retry-device').hidden=false}
 finally{deviceBusy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);deviceNode('finish-setup').disabled=!setupPinReady}
}
async function deviceFlow(name,pinId){
 const pin=pinId?deviceNode(pinId).value:undefined;
 if(pinId)deviceNode(pinId).value='';
 const options=await LensDevice.call(name+'-options',{pin});
 const proof=await LensDevice.ceremony(options,name==='register');
 const result=await LensDevice.call(name+'-verify',proof);
 deviceNode('device-success').textContent=result.test_approved?'Test approval verified. No orders were sent.':name==='register'?'Device registered. Try the no-trade test next.':name==='disable'?'Both paper and live orders now require your Lens PIN.':'Device approval activated for '+name.replace('enable-','')+' orders. No orders were sent.';
}
deviceNode('register-device').addEventListener('click',()=>deviceAction(()=>deviceFlow('register','register-pin')));
deviceNode('test-device').addEventListener('click',()=>deviceAction(()=>deviceFlow('test')));
deviceNode('retest-device').addEventListener('click',()=>deviceAction(()=>deviceFlow('test')));
for(const mode of ['paper','live'])deviceNode('enable-'+mode).addEventListener('click',()=>deviceAction(()=>deviceFlow('enable-'+mode,'activation-pin')));
deviceNode('disable-device').addEventListener('click',()=>deviceAction(()=>deviceFlow('disable','activation-pin')));
deviceNode('retry-device').addEventListener('click',()=>location.reload());
deviceNode('create-device-pin').addEventListener('submit',event=>{
 event.preventDefault();deviceAction(async()=>{
  const pin=deviceNode('setup-pin').value;
  if(pin!==deviceNode('setup-pin-again').value)throw Error('The two PIN entries do not match.');
  const r=await fetch('/api/pin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({op:'set',pin})});
  const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||d.log||'PIN could not be saved.');
  deviceNode('setup-pin').value='';deviceNode('setup-pin-again').value='';
  deviceNode('device-success').textContent='Lens PIN saved. You can now set up device verification.';
 });
});
deviceAction(async()=>{});

deviceNode('reset-device').addEventListener('click',()=>deviceAction(async()=>{
 const pin=deviceNode('reset-pin').value;deviceNode('reset-pin').value='';
 await LensDevice.call('reset-enrollment',{pin});
 deviceNode('device-success').textContent='Registration cleared. You can now set up a different passkey.';
}));

deviceNode('change-pin-form').addEventListener('submit',event=>{
 event.preventDefault();deviceAction(async()=>{
  const pin=deviceNode('new-pin').value,current=deviceNode('current-pin').value;
  if(pin!==deviceNode('new-pin-again').value)throw Error('The two new PIN entries do not match.');
  const r=await fetch('/api/pin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({op:'set',current,pin})});
  const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||d.log||'PIN could not be changed.');
  for(const id of ['current-pin','new-pin','new-pin-again'])deviceNode(id).value='';
  deviceNode('device-success').textContent='Your new PIN is saved. Device approval preferences are unchanged.';
 });
});
deviceNode('finish-setup').addEventListener('click',()=>deviceAction(async()=>{
 if(!setupPinReady)throw Error('Create your PIN first.');
 const r=await fetch('/api/space/complete-setup',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
 const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||d.log||'Setup could not be saved.');
 location.assign('/');
}));
