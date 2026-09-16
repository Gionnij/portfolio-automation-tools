/* Current policy holdings only. Account status comes from the shared header. */
const homeMetric=id=>document.getElementById(id);
let homeAccount=null,homeSession=null,homeReading=null,homeReadSequence=0,homeReadBusy=false,homeReadError='';
const homeFinite=value=>typeof value==='number'&&Number.isFinite(value);
const homeEuro=(value,signed=false)=>homeFinite(value)?new Intl.NumberFormat('en-IE',{style:'currency',currency:'EUR',minimumFractionDigits:2,maximumFractionDigits:2,signDisplay:signed?'exceptZero':'auto'}).format(value):'—';
function renderHomePerformance(){
 const d=homeReading,p=d?.performance,gain=p?.unrealized_pnl;
 homeMetric('home-holdings-value').textContent=homeEuro(d?.nav);
 homeMetric('home-holdings-cost').textContent=homeEuro(p?.cost_basis);
 homeMetric('home-gain-loss').textContent=homeEuro(gain,true);
 homeMetric('home-gain-percent').textContent=homeFinite(p?.unrealized_pct)?new Intl.NumberFormat('en-GB',{maximumFractionDigits:2,signDisplay:'exceptZero'}).format(p.unrealized_pct)+'%':p?.cost_basis===0?'No holdings yet':'Percentage unavailable';
 homeMetric('home-gain-card').dataset.direction=homeFinite(gain)?gain>0?'gain':gain<0?'loss':'flat':'unknown';
 homeMetric('home-metrics-refresh').disabled=homeReadBusy||!homeAccount;
 const time=d?.read_at?new Date(d.read_at):null;
 const date=time&&!Number.isNaN(time.getTime())?time.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}):'Date unavailable';
 homeMetric('home-metrics-status').textContent=d?(homeReadError?'Last known reading · ':homeReadBusy?'Refreshing · ':'Checked ')+date+' · '+(homeAccount==='live'?'Live':'Paper')+' account':homeReadBusy?'Reading your holdings from IBKR…':homeAccount?'Holdings are unavailable. Refresh to try again.':'Connect IB Gateway to see your holdings and gain/loss.';
 homeMetric('home-metrics-error').textContent=homeReadError|| (d&&!homeFinite(gain)?'Some prices or purchase costs are unavailable. Gain/loss stays unknown until those holdings can be verified.':'');
 homeMetric('home-metrics-fx').hidden=!p?.foreign_currency;
}
async function refreshHomePerformance(){
 if(homeReadBusy||!homeAccount)return;
 const seq=++homeReadSequence,account=homeAccount;
 homeReadBusy=true;renderHomePerformance();
 try{
  const response=await fetch('/api/balances',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account})});
  const data=await response.json();
  if(seq!==homeReadSequence||account!==homeAccount)return;
  if(!response.ok||!data.ok||data.account!==account)throw Error(data.log||data.error||'The account balances could not be verified.');
  homeReading=data;homeReadError='';
 }catch(error){if(seq===homeReadSequence)homeReadError=error.message||'Could not refresh your holdings.';}
 finally{if(seq===homeReadSequence){homeReadBusy=false;renderHomePerformance();}}
}
function followHomeConnection(connection){
 const account=connection?.state==='connected'&&['paper','live'].includes(connection.mode)?connection.mode:null;
 const session=account?(connection.session_key||account):null;
 if(account!==homeAccount||session!==homeSession){homeReadSequence++;homeAccount=account;homeSession=session;homeReading=null;homeReadError='';homeReadBusy=false;renderHomePerformance();}
 if(account&&(!homeReading||homeReadError||Date.now()-Date.parse(homeReading.read_at)>30000))refreshHomePerformance();
}
window.addEventListener('lens-connection',event=>followHomeConnection(event.detail));
homeMetric('home-metrics-refresh').addEventListener('click',refreshHomePerformance);
renderHomePerformance();
