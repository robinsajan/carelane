'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownLeft, ArrowRight, Bell, CalendarClock, CalendarDays, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, ClipboardList, Clock3, HeartPulse, LayoutDashboard, LockKeyhole, LogOut, Menu, Plus, Search, Settings2, ShieldCheck, Sparkles, Stethoscope, Users, X } from 'lucide-react';
import { api, dateText, hospitalDate, query, type Row } from './api';
import { PasswordInput, Avatar, Badge, Empty, ErrorBox, Field, Loading, Modal, Submit, useLoad } from './ui';
import { PatientDirectory, PatientForm, PatientProfile } from './patients';
import { Queue, VisitDetail, VisitForm } from './visits';
import { InlineVisitStatus } from './visit-status';
import { VisitActions } from './visit-actions';
import { FollowupsPanel, FollowupDetail, FollowupForm } from './followups';
import { Reports, Settings } from './settings';
import { Billing, BillDialog } from './billing';
import { PasswordRules, validPassword } from './password-rules';
import { ReceiptText } from 'lucide-react';

export type AppContext = { user:Row; catalog:Row; refresh:number; notify:(message:string)=>void; changed:()=>void; openPatient:(id:number)=>void; openVisit:(id:number)=>void; newVisit:(patient?:Row,followup?:Row)=>void; newFollowup:(patient?:Row,visit?:Row)=>void; openFollowup:(id:number)=>void; openFollowups:()=>void; openBilling:(visitId:number)=>void; openBill:(billId:number)=>void };
const navigation = [{name:'OPD',icon:ClipboardList},{name:'Dashboard', icon:LayoutDashboard},{name:'Patients',icon:Users},{name:'Billing',icon:ReceiptText}];

export default function Home() {
  const [user,setUser]=useState<Row|null>(null), [boot,setBoot]=useState(true), [setup,setSetup]=useState(false), [bootError,setBootError]=useState('');
  const [followupsOpen,setFollowupsOpen]=useState(false);
  const [nav,setNav]=useState('OPD'), [mobile,setMobile]=useState(false), [refresh,setRefresh]=useState(0), [catalog,setCatalog]=useState<Row|null>(null);
  const [toast,setToast]=useState(''), [overlay,setOverlay]=useState<Row|null>(null), [patientId,setPatientId]=useState<number|null>(null);
  const [reminders,setReminders]=useState<Row[]>([]), [reminderOpen,setReminderOpen]=useState(false), [passwordOpen,setPasswordOpen]=useState(false);
  const seen=useRef('');
  const initialize=useCallback(async()=>{setBoot(true);setBootError('');try {const health=await api('/health');setSetup(health.setup_required);if(!health.setup_required) { try{setUser(await api('/auth/me'));}catch(e:any){if(e.status!==401)throw e;}}}catch(e:any){setBootError(e.message);}finally{setBoot(false);}},[]);
  useEffect(()=>{initialize();const expired=()=>{setUser(null);setFollowupsOpen(false);setCatalog(null);setOverlay(null);setPatientId(null);setReminders([]);};window.addEventListener('opd-session-expired',expired);return()=>window.removeEventListener('opd-session-expired',expired);},[initialize]);
  const notify=(message:string)=>{setToast(message);};
  useEffect(()=>{if(!toast)return;const id=setTimeout(()=>setToast(''),5000);return()=>clearTimeout(id);},[toast]);
  useEffect(()=>{if(!user||user.must_change)return;let active=true;api('/catalog').then(x=>{if(active){setCatalog(x);setBootError('');}}).catch(e=>{if(active)setBootError(e.message);});return()=>{active=false;};},[user,refresh]);
  useEffect(()=>{
    if(!user||user.must_change)return;
    let active=true,inFlight=false;
    const check=async()=>{
      if(document.visibilityState==='hidden'||inFlight)return;
      inFlight=true;
      try{const rows=await api('/daily-reminders');if(!active)return;
        setReminders(rows);
        const day=hospitalDate(catalog?.settings.timezone||'Asia/Kolkata');
        const key=rows.length?day+':'+rows.map((r:Row)=>`${r.id}-${r.schedule_revision}`).join(','):'';
        if(key&&key!==seen.current)setReminderOpen(true);
        seen.current=key;
      }catch{}finally{inFlight=false;}
    };
    check();
    const timer=setInterval(check,60000);
    document.addEventListener('visibilitychange',check);
    return()=>{active=false;clearInterval(timer);document.removeEventListener('visibilitychange',check);};
  },[user,refresh,catalog?.settings.timezone]);
  useEffect(()=>{
    const expiries=(catalog?.doctors||[]).map((doctor:Row)=>doctor.disabled_until?new Date(doctor.disabled_until).getTime():0).filter((expiry:number)=>expiry>Date.now());
    if(!expiries.length)return;
    const timer=setTimeout(()=>setRefresh(value=>value+1),Math.max(0,Math.min(...expiries)-Date.now())+100);
    return()=>clearTimeout(timer);
  },[catalog]);
  const changed=()=>setRefresh(x=>x+1);
  const go=(name:string)=>{if(!window.dispatchEvent(new Event('opd-before-navigation',{cancelable:true})))return;setNav(name);setPatientId(null);setMobile(false);};
  const ctx: AppContext = {user:user||{},catalog:catalog||{},refresh,notify,changed,openBilling:(visitId)=>setOverlay({kind:'bill',visitId}),openBill:(billId)=>setOverlay({kind:'bill',billId}),openFollowups:()=>setFollowupsOpen(true),
    openPatient:(id)=>{setNav('Patients');setPatientId(id);setOverlay(null);},
    openVisit:(id)=>setOverlay({kind:'visitDetail',id}),newVisit:(patient,followup)=>setOverlay({kind:'visit',patient,followup}),
    newFollowup:(patient,visit)=>setOverlay({kind:'follow',patient,visit}),openFollowup:(id)=>setOverlay({kind:'followDetail',id})};
  if(boot)return <div className="boot"><Brand/><Loading/></div>;
  if(!user)return <Login setup={setup} initialError={bootError} retry={initialize} onLogin={u=>{setUser(u);setSetup(false);setBootError('');setNav('OPD');seen.current='';}}/>;
  if(user.must_change)return <PasswordGate user={user} onDone={async()=>{setUser(await api('/auth/me'));}}/>;
  if(!catalog)return <div className="boot"><Brand/>{!bootError&&<Loading/>}<ErrorBox message={bootError}/></div>;
  const hospital=catalog.settings.hospital_name;
  return <div className="app-shell">
    {mobile&&<div className="sidebar-scrim" onClick={()=>setMobile(false)}/>}
    <aside id="workspace-navigation" aria-label="Workspace navigation" className={`sidebar ${mobile?'show':''}`}>
      <Brand/>
      <button className="icon-btn sidebar-close mobile-menu" aria-label="Close navigation" onClick={()=>setMobile(false)}><X size={20}/></button>
      <div className="hospital-switch"><span className="hospital-symbol"><HeartPulse size={20}/></span><div><strong>{hospital}</strong><small>OPD administration</small></div><ShieldCheck size={15}/></div>
      <div className="nav-label">Workspace</div>
      <nav>{navigation.map(({name,icon:Icon})=><button key={name} className={`nav-item ${nav===name?'active':''}`} aria-label={name} title={name} aria-current={nav===name?'page':undefined} onClick={()=>go(name)}><Icon size={19}/><span>{name}</span>{name==='Follow-ups'&&reminders.length>0&&<b>{reminders.length}</b>}</button>)}</nav>
      {user.role==='Master'&&<><div className="nav-label manage-label">Administration</div>
      <button className={`nav-item ${nav==='Settings'?'active':''}`} aria-label="Settings & setup" title="Settings & setup" onClick={()=>go('Settings')}><Settings2 size={19}/><span>Settings & setup</span></button></>}
      <div className="sidebar-bottom">
      <button className="nav-item" title="Follow-up reminders" aria-label={`Follow-up reminders: ${reminders.length}`} aria-expanded={reminderOpen} onClick={()=>{setReminderOpen(x=>!x);setMobile(false);}}><Bell size={19}/><span>Reminders</span>{reminders.length>0&&<b>{reminders.length}</b>}</button>
      <button type="button" className="account-trigger" popoverTarget="account-options" aria-label={`Account options for ${user.name}`} title={user.name}><Avatar name={user.name} small/><span className="account-name">{user.name}</span></button>
      <div id="account-options" popover="auto" className="account-popover">
        <strong>{user.name}</strong>
        <button type="button" onClick={()=>{document.getElementById('account-options')?.hidePopover();setPasswordOpen(true);setMobile(false);}}><LockKeyhole size={16}/>Change password</button>
        <button type="button" onClick={async()=>{try{await api('/auth/logout','POST');setUser(null);setFollowupsOpen(false);setCatalog(null);setOverlay(null);setReminders([]);setPatientId(null);}catch(e:any){notify(e.message);}}}><LogOut size={16}/>Sign out</button>
      </div>
      </div>
    </aside>
    <div className="workspace">
    <button className="icon-btn mobile-menu navigation-toggle" aria-label="Open navigation" aria-expanded={mobile} aria-controls="workspace-navigation" onClick={()=>setMobile(true)}><Menu size={21}/></button>
    <main>
      <ErrorBox message={bootError}/>
      {nav==='Dashboard'&&<Dashboard ctx={ctx}/>}
      {nav==='Patients'&&(patientId?<PatientProfile id={patientId} ctx={ctx} back={()=>setPatientId(null)} edit={p=>setOverlay({kind:'patient',patient:p})}/>:<PatientDirectory ctx={ctx} search="" register={()=>setOverlay({kind:'patient'})}/>)}
      {nav==="OPD"&&<Queue ctx={ctx} register={()=>setOverlay({kind:'patient',fromOPD:true})}/>}
      {nav==='Billing'&&<Billing ctx={ctx}/>}
      {nav==='Settings'&&<Settings ctx={ctx} password={()=>setPasswordOpen(true)}/>}
      <footer className="page-footer"><span><ShieldCheck size={13}/> Hospital workspace</span><span>{hospital} <i/> OPD management</span></footer>
    </main></div>
    {toast&&<div role="status" className="toast"><Check size={17}/>{toast}<button className="icon-btn" aria-label="Dismiss notification" onClick={()=>setToast('')}><X size={14}/></button></div>}
    {followupsOpen&&<FollowupsPanel ctx={ctx} close={()=>setFollowupsOpen(false)}/>}
    {overlay?.kind==='patient'&&<PatientForm patient={overlay.patient} ctx={ctx} close={()=>setOverlay(null)} saved={(p,visit,existing)=>{changed();notify(existing?'Existing patient ready':overlay.patient?'Patient updated':'Patient registered');if(visit)setOverlay({kind:'visit',patient:p});else {setOverlay(null);if(!overlay.fromOPD)ctx.openPatient(p.id);}}}/>}
    {overlay?.kind==='visit'&&<VisitForm patient={overlay.patient} followup={overlay.followup} ctx={ctx} close={()=>setOverlay(null)} saved={()=>{setOverlay(null);setNav('OPD');setPatientId(null);changed();notify('Visit created and added to the queue');}}/>}
    {overlay?.kind==='bill'&&<BillDialog visitId={overlay.visitId} billId={overlay.billId} ctx={ctx} close={()=>setOverlay(null)}/>}
    {overlay?.kind==='visitDetail'&&<VisitDetail id={overlay.id} ctx={ctx} close={()=>setOverlay(null)}/>}
    {overlay?.kind==='follow'&&<FollowupForm patient={overlay.patient} visit={overlay.visit} ctx={ctx} close={()=>setOverlay(null)} saved={()=>{setOverlay(null);changed();notify('Follow-up scheduled');}}/>}
    {overlay?.kind==='followDetail'&&<FollowupDetail id={overlay.id} ctx={ctx} close={()=>setOverlay(null)}/>}
    {passwordOpen&&<Modal title="Change your password" subtitle="Changing your password signs out other sessions." onClose={()=>setPasswordOpen(false)}><PasswordForm done={async()=>{setPasswordOpen(false);notify('Password updated');setUser(await api('/auth/me'));}}/></Modal>}
    {reminderOpen&&<div className="reminder-panel" role="region" aria-label="Follow-up reminder pop-up"><div className="reminder-title"><span className="reminder-icon"><Bell size={19}/></span><div><h3>Follow-up reminders</h3><p>Daily at 9:00 AM · {reminders.length} due or overdue</p></div><button className="icon-btn" aria-label="Close reminders" onClick={()=>setReminderOpen(false)}><X size={18}/></button></div><div className="reminder-items">{!reminders.length?<Empty title="You're all caught up" text="Due reminders will appear here."/>:reminders.map(r=><div className="reminder-item" key={r.id}><strong>{r.patient_name}</strong><span className="mono">{r.uhid}</span><p>{r.doctor_name} · {dateText(r.due_date)} {r.due_time}</p><div className="reminder-actions"><button onClick={()=>{ctx.openFollowup(r.id);setReminderOpen(false);}}>Open record<ArrowRight size={12}/></button><button onClick={async()=>{try{await api(`/daily-reminders/${r.id}`,'POST',{revision:r.schedule_revision,action:'snooze',minutes:30});changed();notify('Reminder snoozed for 30 minutes');}catch(e:any){notify(e.message);}}}>Snooze 30m</button><button onClick={async()=>{try{await api(`/daily-reminders/${r.id}`,'POST',{revision:r.schedule_revision,action:'acknowledge'});changed();}catch(e:any){notify(e.message);}}} aria-label={`Acknowledge reminder for ${r.patient_name}`}><CheckCheck size={16}/></button></div></div>)}</div><div className="reminder-foot">On-screen reminders only · No messages sent</div></div>}
  </div>;
}

export function Brand(){return <div className="brand"><span><Activity size={24} strokeWidth={2.5}/></span><strong>carelane<span>OPD WORKSPACE</span></strong></div>;}

function Login({setup,onLogin,initialError,retry}:{setup:boolean;onLogin:(u:Row)=>void;initialError:string;retry:()=>void}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[form,setForm]=useState({username:'',password:'',name:'',hospital_name:'',setup_key:''});
  const update=(k:string,v:string)=>setForm({...form,[k]:v});
  return <div className="login-page"><section className="login-story"><Brand/><div className="story-content"><h1>Hospital reception,<br/>in one workspace.</h1><p>Register patients, manage the doctor queue, and arrange their next visit.</p><div className="login-workflow"><div><Users size={20}/><span><strong>A permanent patient record</strong><small>Find returning patients by name and reuse their UHID.</small></span></div><div><ClipboardList size={20}/><span><strong>A queue for each doctor</strong><small>Track arrivals from waiting through completed.</small></span></div><div><CalendarClock size={20}/><span><strong>Follow-ups for your team</strong><small>Schedule a return visit with an on-screen reminder.</small></span></div></div></div><div className="story-bottom"><ShieldCheck size={16}/> Access controlled. Built for your hospital team.</div></section><section className="login-form-area"><div className="login-form"><span className="login-lock"><LockKeyhole size={24}/></span><h2>{setup?'Set up your hospital':'Staff sign in'}</h2><p>{setup?'Create the single Master account to get started.':'Sign in to your hospital workspace.'}</p><ErrorBox message={error||initialError}/>{initialError&&<button className="text-btn" onClick={retry}>Reconnect to local server</button>}<form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{onLogin(await api(setup?'/auth/setup':'/auth/login','POST',setup?form:{username:form.username,password:form.password}));}catch(e:any){setError(e.message);}finally{setBusy(false);}}}>
      {setup&&<><Field label="Hospital name" required><input required value={form.hospital_name} onChange={e=>update('hospital_name',e.target.value)} placeholder="Your hospital name"/></Field><Field label="Your full name" required><input required value={form.name} onChange={e=>update('name',e.target.value)} placeholder="Master account holder"/></Field><Field label="Local setup key" required hint="Find this in backend/data/opd.setup-key on the local server."><PasswordInput required value={form.setup_key} onChange={e=>update('setup_key',e.target.value)} autoComplete="off"/></Field></>}
      <Field label="Username" required><input required autoComplete="username" value={form.username} onChange={e=>update('username',e.target.value)} placeholder="Enter your username"/></Field><Field label="Password" required hint={setup?'At least 12 characters. Keep your Master credentials safe.':undefined}><PasswordInput minLength={setup?12:1} required autoComplete={setup?'new-password':'current-password'} value={form.password} onChange={e=>update('password',e.target.value)} placeholder="Enter your password"/></Field>{setup&&<PasswordRules value={form.password}/>}<button className="btn primary login-submit" disabled={busy||(setup&&!validPassword(form.password))}>{busy?<span className="spinner"/>:null}{busy?'Please wait…':setup?'Create Master account':'Sign in to workspace'}<ArrowRight size={17}/></button></form><div className="login-note"><ShieldCheck size={15}/>{setup?'Only one Master account can be created.':'Access is restricted to authorized hospital staff.'}</div></div><span className="login-copyright">Carelane · Hospital OPD management</span></section></div>;
}

export function PasswordForm({done}:{done:()=>void}){const[error,setError]=useState(''),[busy,setBusy]=useState(false),[newPassword,setNewPassword]=useState(''),[confirm,setConfirm]=useState('');return <form className="form-body" onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);setBusy(true);setError('');if(f.get('new_password')!==f.get('confirm')){setError('New passwords must match.');setBusy(false);return;}try{await api('/auth/password','POST',{current_password:f.get('current_password'),new_password:f.get('new_password')});done();}catch(e:any){setError(e.message);}finally{setBusy(false);}}}><ErrorBox message={error}/><Field label="Current password" required><PasswordInput name="current_password" required autoComplete="current-password"/></Field><Field label="New password" required hint="At least 12 characters."><PasswordInput name="new_password" value={newPassword} onChange={e=>setNewPassword(e.target.value)} minLength={12} maxLength={128} required autoComplete="new-password"/></Field><PasswordRules value={newPassword}/><Field label="Confirm new password" required><PasswordInput name="confirm" value={confirm} onChange={e=>setConfirm(e.target.value)} minLength={12} maxLength={128} required autoComplete="new-password"/></Field><div className="form-actions"><button className="btn primary" disabled={busy||!validPassword(newPassword)||newPassword!==confirm}>{busy?'Saving…':'Update password'}</button></div></form>;}
function PasswordGate({user,onDone}:{user:Row;onDone:()=>void}){return <div className="boot"><Brand/><div className="password-card"><h2>Secure your account, {user.name}</h2><p>Please replace your temporary password before continuing.</p><PasswordForm done={onDone}/></div></div>;}

export function Dashboard({ctx}:{ctx:AppContext}) {
  const {data,error,loading}=useLoad('/dashboard',ctx.refresh);
  const statuses=data?.statuses||{};
  const stats=data?[{label:"Today's visits",value:data.total_visits,sub:'All OPD visits today'}, {label:'Patients waiting',value:statuses.Waiting||0,sub:`${statuses['Being Attended']||0} currently being attended`},{label:'Completed visits',value:statuses.Completed||0,sub:'Attendance completed today'},{label:'Follow-ups today',value:data.followups_today,sub:`${data.overdue} overdue follow-ups`}]:[];
  const trend:Row[]=data?.trend||[];
  const max=Math.max(4,Math.ceil(Math.max(0,...trend.map((x:Row)=>x.visits))/4)*4);
  return <><div className="page-heading"><div><h1>Dashboard</h1><p>OPD analytics and reports.</p></div>{data&&<div className="date-pill"><CalendarDays size={16}/>{dateText(data.date)}</div>}</div><ErrorBox message={error}/>
    {!data&&loading?<Loading/>:data&&<><div className="stats-grid">{stats.map(({label,value,sub})=><div className="stat-card" key={label}><div className="stat-label"><span>{label}</span></div><strong>{Number(value||0).toLocaleString()}</strong><small>{sub}</small></div>)}</div>
    <section className="card trend-card"><div className="card-heading"><div><h2>OPD activity</h2><p>Patient visits over the last 7 days</p></div><span className="muted">Last 7 days</span></div><div className="chart-area"><div className="chart-scale">{[max,Math.round(max*.75),Math.round(max*.5),Math.round(max*.25),0].map((v,i)=><span key={i}>{v}</span>)}</div><div className="chart-plot"><div className="chart-grid"><i/><i/><i/><i/><i/></div><div className="bars">{trend.map((x:Row,i:number)=><div className="bar-col" key={x.date}><div className="bar-space"><div className={`bar ${i===trend.length-1?'current':''}`} style={{height:`${x.visits/max*100}%`}} title={`${x.date}: ${x.visits} visits`}>{x.visits>0&&<span>{x.visits}</span>}</div></div><small>{x.date===data.date?'Today':new Date(x.date+'T12:00').toLocaleDateString('en-IN',{weekday:'short'})}</small></div>)}</div></div></div><div className="chart-legend"><i/>OPD visits <span>{trend.reduce((a:number,x:Row)=>a+x.visits,0)} total this week</span></div></section></>}
    <div className="spaced-top"><Reports ctx={ctx} embedded/></div>
  </>;
}
