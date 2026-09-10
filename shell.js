/* Shared connection indicator. Reads status supplied by each page; no API calls. */
function renderGatewayIndicator(connection, busy=false, issue='') {
  const node=id=>document.getElementById(id);
  const connected=connection?.state==='connected';
  const restricted=connected&&connection.read_only===true;
  const mode=connected?connection.mode:null;
  const state=restricted?'attention':connected?mode:!connection&&busy?'checking':connection?.state==='disconnected'?'offline':'attention';
  const label=connected?(mode==='live'?'Live account':'Paper account')+(restricted?' · Read-only':''):state==='checking'?'Connecting…':state==='offline'?'Disconnected':'Needs attention';
  node('gateway-menu').dataset.state=state;
  node('account-label').textContent=label;
  node('gateway-toggle').setAttribute('aria-label','IBKR: '+label+'. Open connection details');
  node('gateway-title').textContent=connected?(mode==='live'?'Live account · real money':'Paper account · virtual money'):connection?.state==='multiple_connections'?'Two Gateways are connected':state==='checking'?'Checking IB Gateway…':'IB Gateway is not ready';
  node('gateway-detail').textContent=restricted?'IBKR has Read-Only API enabled. You can view holdings, but cannot send investments. Untick Read-Only API in Gateway’s API settings, apply, then refresh here.':connection?.message||(busy?'Checking your local Gateway connection…':issue||'Open IB Gateway and sign in. Lens will detect the connected account automatically.');
  node('gateway-issue').textContent=connected?issue:'';
  node('gateway-issue').hidden=!connected||!issue;
  node('gateway-refresh').disabled=busy;
  node('gateway-refresh').textContent=busy?'Checking…':'Refresh connection';
  document.body.classList.toggle('live',mode==='live');
}
function openGatewayMenu(){
  const menu=document.getElementById('gateway-menu');
  menu.open=true;document.getElementById('gateway-toggle').focus();
}
document.addEventListener('click',event=>{
  const menu=document.getElementById('gateway-menu');
  if(menu?.open&&!menu.contains(event.target))menu.open=false;
});
document.addEventListener('keydown',event=>{
  const menu=document.getElementById('gateway-menu');
  if(event.key==='Escape'&&menu?.open){menu.open=false;document.getElementById('gateway-toggle').focus();}
});
