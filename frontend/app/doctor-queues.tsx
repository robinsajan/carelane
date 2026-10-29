'use client';

import { DepartmentBadge, departmentColor } from './department-colors';
import { useState, type CSSProperties } from 'react';
import { ArrowRight, Check, ListOrdered, Plus, ReceiptText, RefreshCw, MoreHorizontal, UserRoundMinus } from 'lucide-react';
import type { Row } from './api';
import type { AppContext } from './page';
import { api, dateText, query } from './api';
import { Avatar, Empty, ErrorBox, Loading, Modal, Pager, SearchBox, useLoad } from './ui';


export function DoctorQueuePatient({visit,ctx,next=false}:{visit:Row;ctx:AppContext;next?:boolean}) {
  const [cancel,setCancel]=useState(false),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [confirmed,setConfirmed]=useState<Row|null>(null);
  const current=confirmed&&confirmed.version>visit.version?confirmed:visit;
  const moved=current.status!==visit.status;
  const save=async(status:string,note='')=>{
    if(busy)return;
    setBusy(true);setError('');
    try {
      setConfirmed(await api(`/visits/${current.id}`,'PATCH',{version:current.version,status,reason:note}));
      setCancel(false);setReason('');ctx.changed();ctx.notify(`Visit marked ${status.toLowerCase()}`);
    }catch(e:any){setError(e.message);if(e.status===409)ctx.changed();}finally{setBusy(false);}
  };
  return <div className={`doctor-queue-entry ${visit.status==='Being Attended'?'attending-entry':''}`}>
    <div className="doctor-queue-patient"><span className="token">{String(visit.token).padStart(2,'0')}</span><button title={`${visit.patient_name} · ${visit.uhid}`} onClick={()=>ctx.openVisit(visit.id)}><strong>{visit.patient_name}</strong><small>{visit.status==='Being Attended'?'In consultation':visit.status==='Cancelled'?'Cancelled':'Next in line'}</small></button>{next&&<span className="queue-next">Next</span>}</div>
    {moved?<p className="queue-action-result" role="status">Marked {current.status.toLowerCase()}</p>:<div className="queue-patient-actions">
      {visit.status==='Waiting'&&<button type="button" className="btn secondary compact queue-attend-action" disabled={busy} aria-label={`Attend ${visit.patient_name}`} onClick={()=>void save('Being Attended')}>{busy?'Saving…':'Attend'}<ArrowRight size={13}/></button>}
      {visit.status==='Being Attended'&&<button type="button" className="btn secondary compact queue-finish-action" disabled={busy} aria-label={`Complete visit for ${visit.patient_name}`} onClick={()=>void save('Completed')}><Check size={13}/>{busy?'Saving…':'Complete'}</button>}
      {visit.status==='Cancelled'?<button type="button" className="btn secondary compact" disabled={busy} aria-label={`Return ${visit.patient_name} to waiting`} onClick={()=>void save('Waiting','Returned to waiting queue')}>Back to waiting</button>:<button type="button" className="queue-cancel-btn" title="Cancel visit" disabled={busy} aria-label={`Cancel visit for ${visit.patient_name}`} onClick={()=>setCancel(!cancel)}><UserRoundMinus size={16}/><span>Cancel</span></button>}
    </div>}
    {cancel&&!moved&&<form className="queue-cancel-form" onSubmit={e=>{e.preventDefault();if(reason.trim().length>=3)void save('Cancelled',reason.trim());}}><label htmlFor={`queue-cancel-${visit.id}`}>Cancellation reason</label><input id={`queue-cancel-${visit.id}`} required minLength={3} maxLength={1000} value={reason} disabled={busy} onChange={e=>setReason(e.target.value)} placeholder="Enter a reason"/><div><button type="submit" className="btn secondary compact" disabled={busy||reason.trim().length<3}>Confirm cancellation</button><button type="button" className="text-btn" disabled={busy} onClick={()=>{setCancel(false);setReason('');}}>Keep visit</button></div></form>}
    {error&&<p className="queue-action-error" role="alert">{error}</p>}
  </div>;
}

export function DoctorQueues({ day, department, ctx, select }: {
  day: string; department: string; ctx: AppContext; select: (doctor: string, status: string) => void;
}) {
  const [availabilityOpen,setAvailabilityOpen]=useState(false);
  const path = '/queues?' + query({ day, department_id: department || 0 });
  const { data, error, loading, dataPath } = useLoad(path, ctx.refresh);
  // Ignore a previous date's result while its replacement is loading.
  const current = dataPath === path ? data : null;
  const queuePriority=(doctor:Row)=>doctor.counts.Waiting>0?0:doctor.counts['Being Attended']>0?1:2;
  // Preserve the existing order among doctors with the same queue priority.
  const doctors:Row[]=[...(current?.items||[])].sort((a,b)=>queuePriority(a)-queuePriority(b));
  const waiting=doctors.reduce((sum,doctor)=>sum+(doctor.counts.Waiting||0),0);
  const consulting=doctors.reduce((sum,doctor)=>sum+(doctor.counts['Being Attended']||0),0);
  const available=doctors.filter(doctor=>doctor.active&&!doctor.counts['Being Attended']).length;
  return <section className="doctor-queues doctor-queue-board" aria-label="Daily doctor queues">
    <header className="queue-board-header"><div><h2><ListOrdered size={20}/>Doctor queues</h2><p>{dateText(day)} · {doctors.length} doctors · {current?.total_visits??0} visits{day===ctx.catalog.today?' today':''}</p></div><button type="button" className="icon-btn" aria-label="Doctor queue options" title="Doctor availability" onClick={()=>setAvailabilityOpen(true)}><MoreHorizontal size={20}/></button></header>
    <div className="queue-board-summary"><span><strong>{waiting}</strong> waiting</span><span><strong>{consulting}</strong> in consultation</span><span><strong>{available}</strong> available doctors</span></div>
    <ErrorBox message={error}/>
    {!current&&loading?<Loading/>:doctors.length?<>
      <div className="queue-board-columns" aria-hidden="true"><span>Doctor</span><span>Current status</span><span>Next in line</span></div>
      <div className="queue-board-rows">{doctors.map(doctor=>{
        const status=!doctor.active?'Inactive':doctor.counts['Being Attended']?'In consultation':'Available';
        return <article className="queue-board-doctor" style={{'--department-color':departmentColor(doctor.department_color)} as CSSProperties} key={doctor.id} aria-label={`Queue for ${doctor.name}`}>
          <div className="queue-board-identity"><Avatar name={doctor.name.replace(/^Dr[.\s]+/i,'')} small/><div><h3><button aria-label={`Open queue for ${doctor.name}`} onClick={()=>select(String(doctor.id),'Waiting')}>{doctor.name}</button></h3><DepartmentBadge name={doctor.department_name} color={doctor.department_color}/><p><i/>{status}</p></div></div>
          <div className="queue-board-patients queue-board-cell" role="group" aria-label={`Current status for ${doctor.name}`}><h4>Current status</h4>
            {doctor.attending.length?doctor.attending.slice(0,1).map((visit:Row)=><DoctorQueuePatient key={visit.id} visit={visit} ctx={ctx}/>):<p className="queue-board-clear">No patient being attended</p>}
            {doctor.counts['Being Attended']>1&&<button className="text-btn queue-board-more" onClick={()=>select(String(doctor.id),'Being Attended')}>View all {doctor.counts['Being Attended']} being attended<ArrowRight size={14}/></button>}
          </div>
          <div className="queue-board-patients queue-board-cell" role="group" aria-label={`Next in line for ${doctor.name}`}><h4>Next in line</h4>
            {doctor.waiting.length?doctor.waiting.slice(0,1).map((visit:Row)=><DoctorQueuePatient key={visit.id} visit={visit} ctx={ctx} next/>):<p className="queue-board-clear">No patients waiting</p>}
            {doctor.counts.Waiting>1&&<button className="text-btn queue-board-more" onClick={()=>select(String(doctor.id),'Waiting')}>View all {doctor.counts.Waiting} waiting<ArrowRight size={14}/></button>}
          </div>
        </article>;
      })}</div>
    </>:!error&&<Empty title="No doctor queues available" text="Add an active doctor in Hospital settings, or choose another department." action={ctx.user.role==='Master'?undefined:<button className="btn secondary" onClick={()=>ctx.newVisit()}><Plus size={15}/>Create visit</button>}/>}
    {availabilityOpen&&<DoctorAvailability ctx={ctx} close={()=>setAvailabilityOpen(false)}/>}
    <footer className="queue-board-footer"><span>Daily queues · Tokens are separate for each doctor</span><span><RefreshCw size={15}/>Updates after saved changes</span></footer>
  </section>;
}


export function CompletedPatients({day,department,ctx}:{day:string;department:string;ctx:AppContext}) {
 const [page,setPage]=useState(1),[search,setSearch]=useState('');
 const path='/visits?'+query({day,department_id:department||0,status:'Completed',q:search.trim(),page});
 const {data,error,loading,dataPath}=useLoad(path,ctx.refresh);
 const current=dataPath===path?data:null;
 return <section className="card completed-patients" aria-label="Completed patients">
  <div className="card-heading completed-heading"><div><h2>Completed patients</h2><p>{dateText(day)} · {current?.total??0} completed visits</p></div><div className="completed-search"><SearchBox value={search} onChange={value=>{setSearch(value);setPage(1);}} placeholder="Search patient name or UHID…"/></div></div>
  <ErrorBox message={error}/>
  {!current&&loading?<Loading/>:current?.items.length?<><div className="completed-table-scroll"><table className="completed-table"><thead><tr><th scope="col">Patient</th><th scope="col">Doctor</th><th scope="col">Billing</th></tr></thead><tbody>{current.items.map((visit:Row)=><tr key={visit.id}>
   <td><button className="completed-patient-link" onClick={()=>ctx.openVisit(visit.id)}><strong>{visit.patient_name}</strong><small>{visit.uhid}</small></button></td>
   <td><div className="completed-doctor-details"><strong>{visit.doctor_name}</strong><span>{visit.department_name}</span></div></td>
   <td><button type="button" className={`completed-bill-button ${visit.bill_id?'is-issued':''}`} aria-label={`${visit.bill_id?'View bill':'Generate bill'} for ${visit.patient_name}`} onClick={()=>visit.bill_id?ctx.openBill(visit.bill_id):ctx.openBilling(visit.id)}><ReceiptText size={14}/><span>{visit.bill_id?'View bill':'Generate bill'}</span><ArrowRight size={13}/></button></td>
  </tr>)}</tbody></table></div><Pager data={current} page={page} setPage={setPage}/></>:!error&&<Empty title={search.trim()?"No matching completed patients":"No completed patients"} text={search.trim()?"Try another patient name or UHID.":"Completed visits will appear here for billing."}/>}
 </section>;
}


export function DoctorAvailability({ctx,close}:{ctx:AppContext;close:()=>void}) {
 const [revision,setRevision]=useState(0),[busy,setBusy]=useState<number|null>(null),[saveError,setSaveError]=useState(''),[search,setSearch]=useState('');
 const {data,error,loading}=useLoad('/doctor-availability',ctx.refresh+revision);
 const doctors:Row[]=(data?.items||[]).filter((doctor:Row)=>doctor.active);
 const terms=search.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
 const matches=doctors.filter(doctor=>terms.every(term=>`${doctor.name} ${doctor.department_name||''}`.toLocaleLowerCase().includes(term)));
 return <Modal title="Doctor availability" subtitle="Manage which doctors are available today." onClose={close} guard={false}><div className="form-body"><ErrorBox message={saveError||error}/><div className="availability-search"><SearchBox value={search} onChange={setSearch} placeholder="Search doctors or departments…"/></div>{!data&&loading?<Loading/>:matches.map((doctor:Row)=><div className="availability-row" key={doctor.id}><div><strong>{doctor.name}</strong>{doctor.disabled_until&&<small>Disabled until {dateText(doctor.disabled_until,true,ctx.catalog.settings.timezone)}</small>}</div><div className="availability-department"><DepartmentBadge name={doctor.department_name} color={doctor.department_color}/></div><button type="button" role="switch" aria-checked={!doctor.disabled_until} className="availability-toggle" disabled={busy!==null} aria-label={`${doctor.disabled_until?'Enable':'Disable for today'} ${doctor.name}`} onClick={async()=>{setBusy(doctor.id);setSaveError('');try{await api(`/doctors/${doctor.id}/availability`,'PATCH',{version:doctor.version,disabled:!doctor.disabled_until});ctx.changed();setRevision(value=>value+1);ctx.notify(doctor.disabled_until?'Doctor enabled':'Doctor disabled until the next 8 AM reset');}catch(e:any){setSaveError(e.message);if(e.status===409)setRevision(value=>value+1);}finally{setBusy(null);}}}><span className="availability-toggle-track" aria-hidden="true"><span/></span><span>{busy===doctor.id?'Saving…':doctor.disabled_until?'Disabled':'Enabled'}</span></button></div>)}{data&&doctors.length>0&&!matches.length&&<Empty title="No matching doctors" text="Try another name or department."/>}{data&&!doctors.length&&<Empty title="No active doctors" text="Master can add or activate doctors in Settings & setup."/>}</div></Modal>;
}
