const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const {webcrypto,createDecipheriv,randomBytes}=require('node:crypto');
function page(response, crypto=webcrypto){
 const nodes=new Map(), calls=[], downloads=[], blobs=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,textContent:'',value:'',checked:false,open:false,events:{},addEventListener(name,fn){this.events[name]=fn},showModal(){this.open=true},close(){this.open=false;this.events.close?.()}});return nodes.get(id)};
 const ctx=vm.createContext({
  crypto,TextEncoder,Uint8Array,Blob,navigator:{clipboard:{writeText:async()=>{throw Error('denied')}}},
  document:{hidden:false,getElementById:node,body:{appendChild(){}},createElement:()=>({click(){downloads.push(this.download)},remove(){}})},
  window:{addEventListener(){}},setInterval(){},setTimeout(){},renderGatewayIndicator(){},
  URL:{createObjectURL:blob=> {blobs.push(blob);return 'blob:export'},revokeObjectURL(){}},
  fetch:async(url,options)=>{calls.push({url,options});return response}
 });
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../data-backup.js'),'utf8'),ctx);
 return {node,calls,downloads,blobs,run:(code='downloadAllData()')=>vm.runInContext(code,ctx)};
}
test('download uses protected POST and only reports browser handoff',async()=>{
 const p=page({ok:true,headers:new Map([['Content-Type','application/zip'],['Content-Disposition','attachment; filename="lens-data-2026-09-11-120000.zip"']]),blob:async()=>({})});
 await p.run();
 assert.equal(p.calls[0].url,'/api/data/export');assert.equal(p.calls[0].options.method,'POST');
 assert.deepEqual(p.downloads,['lens-data-2026-09-11-120000.zip']);
 assert.match(p.node('download-status').textContent,/handed to your browser/);
 assert.equal(p.node('download-data').disabled,false);
});

function zipResponse(){return {ok:true,headers:new Map([['Content-Type','application/zip']]),arrayBuffer:async()=>new Uint8Array(Buffer.from('PK synthetic saved data')).buffer}}
function decrypt(blob,key){
 const decipher=createDecipheriv('aes-256-gcm',key,blob.subarray(24,36));
 decipher.setAAD(blob.subarray(0,36));decipher.setAuthTag(blob.subarray(-16));
 return Buffer.concat([decipher.update(blob.subarray(36,-16)),decipher.final()]);
}
test('encrypted backup requires saved-key acknowledgement and decrypts with the displayed key',async()=>{
 const p=page(zipResponse());p.run('openBackup()');
 const keyText=p.node('recovery-key').value;
 assert.match(keyText,/^LENS1-(?:[0-9A-F]{8}-){7}[0-9A-F]{8}$/);
 await p.run('downloadEncryptedBackup()');assert.equal(p.calls.length,0);
 p.node('recovery-confirmed').checked=true;
 await p.run('downloadEncryptedBackup()');
 assert.equal(p.calls[0].options.body,'{}');
 const encrypted=Buffer.from(await p.blobs[0].arrayBuffer());
 assert.equal(encrypted.subarray(0,8).toString(),'LENSBAK1');
 const key=Buffer.from(keyText.slice(6).replaceAll('-',''),'hex');
 assert.equal(decrypt(encrypted,key).toString(),'PK synthetic saved data');
 assert.equal(encrypted.includes(Buffer.from('synthetic saved data')),false);
 assert.equal(encrypted.includes(key),false);
 assert.match(p.downloads[0],new RegExp(encrypted.subarray(8,24).toString('hex')+'\\.lensbackup$'));
 assert.throws(()=>decrypt(encrypted,randomBytes(32)));
 for(const offset of [0,8,24,36,encrypted.length-1]){
  const changed=Buffer.from(encrypted);changed[offset]^=1;assert.throws(()=>decrypt(changed,key));
 }
 await p.run('downloadEncryptedBackup()');
 assert.equal(p.calls.length,1);assert.equal(p.blobs[1],p.blobs[0]);
});
test('cancel clears the key; reopening creates a different key and backup ID',()=>{
 const p=page(zipResponse());p.run('openBackup()');const first=p.node('recovery-key').value;
 const id=p.node('backup-id').textContent;
 p.node('backup-dialog').close();assert.equal(p.node('recovery-key').value,'');
 assert.equal(p.run('backupState'),null);
 p.run('openBackup()');assert.notEqual(p.node('recovery-key').value,first);assert.notEqual(p.node('backup-id').textContent,id);
 assert.equal(p.node('recovery-confirmed').checked,false);
});
test('key file matches the backup and clipboard failure offers a manual option',async()=>{
 const p=page(zipResponse());p.run('openBackup(); downloadRecoveryKey()');
 const text=await p.blobs[0].text();assert.ok(text.includes(p.node('recovery-key').value));
 assert.ok(text.includes(p.run('backupState.filename')));assert.equal(p.calls.length,0);
 await p.run('copyRecoveryKey()');assert.match(p.node('key-status').textContent,/copy it manually/);
});
test('export failure retains the key for retry without an unencrypted fallback',async()=>{
 const response={ok:false,json:async()=>({error:'An investing action is running.'})};
 const p=page(response);p.run('openBackup()');const key=p.node('recovery-key').value;
 p.node('recovery-confirmed').checked=true;await p.run('downloadEncryptedBackup()');
 assert.equal(p.downloads.length,0);assert.match(p.node('backup-error').textContent,/investing action/);
 assert.equal(p.node('recovery-key').value,key);assert.equal(p.node('download-backup').disabled,false);
 Object.assign(response,zipResponse());await p.run('downloadEncryptedBackup()');assert.equal(p.downloads.length,1);
});
test('unsupported crypto and oversized exports do not offer an unencrypted backup',async()=>{
 const unsupported=page(zipResponse(),{});unsupported.run('openBackup()');
 assert.equal(unsupported.node('backup-dialog').open,false);assert.equal(unsupported.calls.length,0);
 const response=zipResponse();response.headers.set('Content-Length',String(257*1024*1024));
 const p=page(response);p.run('openBackup()');p.node('recovery-confirmed').checked=true;
 await p.run('downloadEncryptedBackup()');assert.equal(p.downloads.length,0);assert.match(p.node('backup-error').textContent,/too large/);
});
test('busy response and unexpected content show errors and allow retry',async()=>{
 for(const response of [{ok:false,json:async()=>({error:'Investing action running'})},{ok:true,headers:new Map([['Content-Type','text/html']])}]){
  const p=page(response);await p.run();
  assert.equal(p.downloads.length,0);assert.ok(p.node('download-error').textContent);
  assert.equal(p.node('download-status').textContent,'');assert.equal(p.node('download-data').disabled,false);
 }
});

test('opening backup settings does not contact the broker or create a download',()=>{
 const p=page({});assert.equal(p.calls.length,0);assert.equal(p.downloads.length,0);
});
