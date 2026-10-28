'use client';

import { useEffect, useId, useRef, useState } from 'react';

import { AlertTriangle, ArrowLeft, ArrowRight, CalendarClock, Check, ChevronRight, ClipboardList, Clock3, Edit3, GitMerge, MapPin, Phone, Plus, Search, ShieldAlert, UserRound, X } from 'lucide-react';

import { api, ApiError, dateText, hospitalDate, query, type Row } from './api';

import type { AppContext } from './page';

import { Avatar, Badge, Empty, ErrorBox, Field, Loading, Modal, Pager, SearchBox, Select, Submit, useLoad } from './ui';

export function PatientDirectory({ctx,search,register}:{ctx:AppContext;search:string;register:()=>void}) {

  const[q,setQ]=useState(search),[page,setPage]=useState(1),[inactive,setInactive]=useState(false);

  useEffect(()=>{setQ(search);setPage(1);},[search]);

  const{data,error,loading}=useLoad('/patients?'+query({q,page,include_inactive:inactive}),ctx.refresh);

  return <><div className="page-heading"><div><h1>Patients</h1><p>Search existing patients or register a new patient.</p></div><button className="btn primary" onClick={register}><Plus size={17}/>Register patient</button></div><div className="card"><div className="list-toolbar"><SearchBox value={q} onChange={v=>{setQ(v);setPage(1);}}/><label className="check-label"><input type="checkbox" checked={inactive} onChange={e=>{setInactive(e.target.checked);setPage(1);}}/>Include inactive patients</label><span className="subtle-pill">{data?.total||0} patients</span></div><ErrorBox message={error}/>{loading&&!data?<Loading/>:data?.items.length?<><div className="table-scroll"><table><thead><tr><th>Patient</th><th>Uhid</th><th>Age / gender</th><th>Contact</th><th>Registered</th><th>Status</th><th/></tr></thead><tbody>{data.items.map((p:Row)=><tr key={p.id}><td><button className="patient-cell" onClick={()=>ctx.openPatient(p.id)}><Avatar name={p.name}/><span><strong>{p.name}</strong><small>{p.address}</small></span></button></td><td><span className="mono id-chip">{p.uhid}</span></td><td>{ageLabel(p,ctx.catalog.settings.timezone)}<small className="cell-sub">{p.gender}</small></td><td>{p.no_mobile?'No mobile':p.phone}</td><td>{dateText(p.created_at,false,ctx.catalog.settings.timezone)}</td><td><Badge value={p.active?'Active':'Inactive'}/></td><td><button className="icon-btn" aria-label={`Open ${p.name}`} onClick={()=>ctx.openPatient(p.id)}><ChevronRight size={18}/></button></td></tr>)}</tbody></table></div><Pager data={{...data,page_size:20}} page={page} setPage={setPage}/></>:<Empty title={q?'No matching patients':'Your patient directory starts here'} text={q?'Try a different name, UHID or mobile number.':'Register a patient to create their permanent hospital record.'} action={!q?<button className="btn primary" onClick={register}><Plus size={16}/>Register patient</button>:undefined}/>}</div></>;

}

export function ageLabel(p:Row,zone='Asia/Kolkata') {

  if(p.dob){const birth=new Date(p.dob+'T12:00'),current=new Date(hospitalDate(zone)+'T12:00');let years=current.getFullYear()-birth.getFullYear();if(current.getMonth()<birth.getMonth()||(current.getMonth()===birth.getMonth()&&current.getDate()<birth.getDate()))years--;if(years>=1)return `${years} years`;const months=(current.getFullYear()-birth.getFullYear())*12+current.getMonth()-birth.getMonth()-(current.getDate()<birth.getDate()?1:0);if(months>=1)return `${months} months`;return `${Math.max(0,Math.floor((current.getTime()-birth.getTime())/86400000))} days`;}

  return `${p.approximate?'~ ':''}${p.age_value} ${p.age_unit.toLowerCase()} (recorded ${dateText(p.age_recorded_on)})`;

}

const blank:Row={name:'',first_name:'',middle_name:'',surname:'',gender:'',age_value:'',age_unit:'Years',dob:'',approximate:true,phone:'',no_mobile:false,address:'',data:{},active:true};

export function PatientForm({patient,ctx,close,saved}:{patient?:Row;ctx:AppContext;close:()=>void;saved:(p:Row,visit:boolean,existing?:boolean)=>void}) {

  const [form,setForm]=useState<Row>(patient?{...patient,name:patient.name||[patient.first_name,patient.middle_name,patient.surname].filter(Boolean).join(' '),data:{...patient.data}}:{...blank,data:{}}),[more,setMore]=useState(!!patient),[error,setError]=useState(''),[busy,setBusy]=useState(false),[matches,setMatches]=useState<Row[]>([]),[ack,setAck]=useState(false);

  const submission=useRef(crypto.randomUUID());

  const [selectedExisting,setSelectedExisting]=useState<Row|null>(null),[selectionEdited,setSelectionEdited]=useState(false);

  const [suggestions,setSuggestions]=useState<Row[]>([]),[suggestionsOpen,setSuggestionsOpen]=useState(false),[suggestionsLoading,setSuggestionsLoading]=useState(false),[searchError,setSearchError]=useState(''),[activeSuggestion,setActiveSuggestion]=useState(-1);

  const suggestionsId=useId();

  const existing=patient||selectedExisting;

  const nameQuery=form.name.trim();

  useEffect(()=>{

    let active=true;

    setSuggestions([]);setSearchError('');setActiveSuggestion(-1);

    if(existing||nameQuery.length<1){setSuggestionsLoading(false);return;}

    setSuggestionsLoading(true);

    const timer=setTimeout(()=>{

      api('/patients?'+query({q:nameQuery,page:1,name_only:true})).then(result=>{if(active)setSuggestions(result.items.slice(0,6));})

        .catch(e=>{if(active)setSearchError(e.message);})

        .finally(()=>{if(active)setSuggestionsLoading(false);});

    },250);

    return()=>{active=false;clearTimeout(timer);};

  },[nameQuery,existing]);

  const chooseExisting=(p:Row)=>{

    setSelectedExisting(p);setForm({...p,name:p.name||[p.first_name,p.middle_name,p.surname].filter(Boolean).join(' '),data:{...p.data}});setMore(true);setSelectionEdited(false);

    setSuggestionsOpen(false);setSuggestions([]);setError('');setSearchError('');setMatches([]);setAck(false);

  };

  const clearExisting=()=>{

    setSelectedExisting(null);setForm({...blank,data:{}});setMore(false);setSelectionEdited(false);

    setSuggestions([]);setSuggestionsOpen(false);setError('');setMatches([]);setAck(false);submission.current=crypto.randomUUID();

  };

  const update=(k:string,v:any)=>{setForm(f=>({...f,[k]:v}));setSelectionEdited(true);setAck(false);setMatches([]);if(k==='name'){setSuggestionsOpen(true);setSuggestions([]);setActiveSuggestion(-1);}};

  const extra=(k:string,v:string)=>{setSelectionEdited(true);setForm(f=>({...f,data:{...f.data,[k]:v}}));};

  const submit=async(visit:boolean)=>{

    if(selectedExisting&&!selectionEdited){saved(selectedExisting,visit,true);return;}
    if(!form.dob&&(form.age_value===''||form.age_value==null)){setError('Enter date of birth or age.');return;}

    setBusy(true);setError('');

    const body={first_name:form.name.trim(),middle_name:'',surname:'',gender:form.gender,age_value:form.dob?null:Number(form.age_value),age_unit:form.age_unit,dob:form.dob||null,approximate:form.approximate,phone:form.phone,no_mobile:!!form.no_mobile,address:form.address,data:form.data,active:!!form.active,...(existing?{version:existing.version}:{}),duplicate_ack:ack};

    try{const result=await api(existing?`/patients/${existing.id}`:'/patients',existing?'PATCH':'POST',body,submission.current);saved(result,visit,!!selectedExisting);}

    catch(e:any){setError(e.message);if(e.detail?.duplicates)setMatches(e.detail.duplicates);}

    finally{setBusy(false);}

  };

  const nameInputProps = {
    role: 'combobox' as const,
    autoComplete: 'off',
    'aria-autocomplete': 'list' as const,
    'aria-expanded': suggestionsOpen && !existing && nameQuery.length >= 1,
    'aria-controls': suggestionsId,
    'aria-activedescendant': suggestionsOpen && activeSuggestion >= 0 ? `${suggestionsId}-${activeSuggestion}` : undefined,
    onFocus: () => setSuggestionsOpen(true),
    onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (existing) return;
      if (e.key === 'Escape' && suggestionsOpen && nameQuery.length >= 1) {
        e.preventDefault(); e.stopPropagation(); setSuggestionsOpen(false); setActiveSuggestion(-1);
      } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault(); setSuggestionsOpen(true);
        setActiveSuggestion(i => suggestions.length ? (e.key === 'ArrowDown' ? (i+1)%suggestions.length : (i<=0 ? suggestions.length-1 : i-1)) : -1);
      } else if (e.key === 'Enter' && suggestionsOpen && suggestions.length) {
        e.preventDefault(); chooseExisting(suggestions[Math.max(0,activeSuggestion)]);
      }
    },
  };

  const dobChanged=(v:string)=>{setSelectionEdited(true);let age=form.age_value;if(v){const b=new Date(v+'T12:00'),t=new Date(ctx.catalog.today+'T12:00');age=t.getFullYear()-b.getFullYear();if(t.getMonth()<b.getMonth()||(t.getMonth()===b.getMonth()&&t.getDate()<b.getDate()))age--;age=Math.max(0,age);}setForm(f=>({...f,dob:v,age_value:age,age_unit:'Years',approximate:!v}));};

  return <Modal title={patient?'Edit patient details':selectedExisting?'Existing patient details':'Register a patient'} subtitle={existing?`${existing.uhid} · Permanent patient record`:'A single UHID connects every visit. Fields marked * are required.'} onClose={close} wide><form onSubmit={e=>{e.preventDefault();const action=(e.nativeEvent as SubmitEvent).submitter?.getAttribute('value');submit(action==='visit');}}><div className="form-body"><ErrorBox message={error}/>{selectedExisting&&<div className="existing-patient-banner"><Check size={19}/><div><strong>Existing patient selected</strong><small>{selectedExisting.name} · {selectedExisting.uhid}. Create a visit using this UHID.</small></div><button type="button" className="text-btn" onClick={clearExisting}>Choose another / new patient</button></div>}{matches.length>0&&<div className="duplicate-box"><strong><AlertTriangle size={16}/>Possible existing patient records</strong><p>These patients have the same name. Review their details before registering another patient.</p>{matches.map(p=><button className="duplicate-match" type="button" key={p.id} onClick={()=>chooseExisting(p)}><span>{p.name}<small>{p.uhid} · {p.phone}</small></span><ArrowRight size={15}/></button>)}<label className="check-label"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>I reviewed the matches. This is a different patient.</label></div>}

      <h3 className="form-section"><UserRound size={17}/>Basic information</h3><div className="form-grid three"><div className="name-lookup full-name-field"><Field label="Name" required><input {...nameInputProps} required maxLength={240} value={form.name} onChange={e=>update('name',e.target.value)} placeholder="Patient full name"/></Field></div>{suggestionsOpen&&!existing&&nameQuery.length>=1&&<div className="name-suggestions" id={suggestionsId} role="listbox" aria-label="Existing patient suggestions"><div className="name-suggestions-heading">Existing patients · Select to use their record</div>{suggestionsLoading?<div className="name-suggestions-message" role="status">Searching patient records…</div>:searchError?<div className="name-suggestions-message" role="alert">{searchError}</div>:suggestions.length?suggestions.map((p,i)=><button key={p.id} id={`${suggestionsId}-${i}`} type="button" role="option" aria-selected={activeSuggestion===i} className={activeSuggestion===i?'highlighted':''} onMouseDown={e=>e.preventDefault()} onMouseEnter={()=>setActiveSuggestion(i)} onClick={()=>chooseExisting(p)}><Avatar name={p.name} small/><span><strong>{p.name}</strong><small>{p.uhid} · {p.gender} · {p.phone||'No mobile'}</small><small>{ageLabel(p,ctx.catalog.settings.timezone)} · {p.address}</small></span><ChevronRight size={15}/></button>):<div className="name-suggestions-message">No existing patients match. Continue registering a new patient.</div>}</div>}<Field label="Gender" required><Select required value={form.gender} onChange={e=>update('gender',e.target.value)}><option value="">Select gender</option>{['Male','Female','Other','Unknown','Prefer not to say'].map(x=><option key={x}>{x}</option>)}</Select></Field><Field label="Date of birth" required={form.age_value===''||form.age_value==null} hint="Enter date of birth, or provide age below."><input required={form.age_value===''||form.age_value==null} type="date" max={ctx.catalog.today} value={form.dob||''} onInput={e=>dobChanged(e.currentTarget.value)}/></Field><Field label="Age" required={!form.dob} hint={form.dob?'Calculated from date of birth.':'Required when date of birth is unknown.'}><div className="input-pair"><input required={!form.dob} readOnly={!!form.dob} type="number" min={0} max={150} value={form.age_value} onChange={e=>update('age_value',e.target.value)} placeholder="Age"/><Select disabled={!!form.dob} value={form.age_unit} onChange={e=>update('age_unit',e.target.value)}>{['Years','Months','Days'].map(x=><option key={x}>{x}</option>)}</Select></div></Field></div>

      <h3 className="form-section"><Phone size={17}/>Contact & address</h3><div className="form-grid"><Field label="Mobile number" required={!form.no_mobile}><input required={!form.no_mobile} disabled={form.no_mobile} inputMode="numeric" pattern="[0-9]{10}" maxLength={10} value={form.no_mobile?'':form.phone} onChange={e=>update('phone',e.target.value)} placeholder="10-digit mobile number"/><span className="check-label"><input type="checkbox" checked={!!form.no_mobile} onChange={e=>update('no_mobile',e.target.checked)}/>No mobile number</span></Field><Field label="Address" required hint="Enter the patient's address or locality."><textarea required minLength={3} maxLength={500} value={form.address} onChange={e=>update('address',e.target.value)} placeholder="House / street / locality" rows={2}/></Field></div>

      <button className="expand-button" type="button" onClick={()=>setMore(!more)}>{more?'−':'+'} Additional details <span>Optional contact, address and emergency information</span></button>{more&&<><div className="form-grid three">{[['additional_phone','Additional mobile'],['email','Email'],['area','Area'],['landmark','Landmark'],['city','City'],['state','State'],['pincode','Pincode'],['emergency_name','Emergency contact name'],['emergency_relationship','Relationship'],['emergency_phone','Emergency phone']].map(([key,label])=><Field label={label} key={key}><input type={key==='email'?'email':'text'} value={form.data[key]||''} onChange={e=>extra(key,e.target.value)}/></Field>)}<Field label="Blood group"><Select value={form.data.blood_group||'Unknown'} onChange={e=>extra('blood_group',e.target.value)}>{['Unknown','A+','A−','B+','B−','AB+','AB−','O+','O−'].map(x=><option key={x}>{x}</option>)}</Select></Field><Field label="Referral source"><input list="referral-list" value={form.data.referral||''} onChange={e=>extra('referral',e.target.value)}/><datalist id="referral-list">{ctx.catalog.lookups.filter((x:Row)=>x.kind==='referral'&&x.active).map((x:Row)=><option key={x.id} value={x.name}/>)}</datalist></Field></div><Field label="Administrative remarks"><textarea rows={2} value={form.data.remarks||''} onChange={e=>extra('remarks',e.target.value)}/></Field></>}{existing&&<label className="check-label"><input type="checkbox" checked={!!form.active} onChange={e=>update('active',e.target.checked)}/>Patient record is active</label>}</div><div className="form-actions"><button type="button" className="btn secondary" disabled={busy} onClick={close}>Cancel</button><button type="submit" className={`btn ${patient?'primary':'secondary'}`} disabled={busy} value="save">{busy?'Saving...':existing?'Save changes':'Save patient'}</button>{!patient&&<button type="submit" className="btn primary" disabled={busy} value="visit"><Check size={16}/>{busy?'Saving...':selectedExisting&&!selectionEdited?'Create visit':'Save & create visit'}</button>}</div></form></Modal>;

}

export function PatientPicker({value,onPick,ctx,onRegister}:{value?:Row;onPick:(p:Row)=>void;ctx:AppContext;onRegister?:()=>void}) {

  const [q,setQ]=useState(''); const path='/patients?'+query({q,page:1}); const{data,error,loading,dataPath}=useLoad(path,0);

  if(value)return <div className="selected-patient"><Avatar name={value.name||value.patient_name||`${value.first_name} ${value.surname}`}/><div><strong>{value.name||value.patient_name||`${value.first_name} ${value.surname}`}</strong><small>{value.uhid} · {value.phone||'No mobile'}</small></div></div>;

  return <div className="patient-picker"><SearchBox value={q} onChange={setQ}/><ErrorBox message={error}/><div className="picker-results">{data?.items.slice(0,8).map((p:Row)=><button type="button" key={p.id} onClick={()=>onPick(p)}><Avatar name={p.name} small/><span><strong>{p.name}</strong><small>{p.uhid} · {p.phone||'No mobile'}</small></span><ChevronRight size={15}/></button>)}{!loading&&!error&&dataPath===path&&data&&!data.items.length&&<><p>No patients found.</p>{onRegister?<button type="button" className="text-btn" onClick={onRegister}><Plus size={16}/>Register a new Patient</button>:<p>Register the patient first.</p>}</>}</div></div>;

}

export function PatientProfile({id,ctx,back,edit}:{id:number;ctx:AppContext;back:()=>void;edit:(p:Row)=>void}) {

  const{data,error,loading}=useLoad(`/patients/${id}`,ctx.refresh);const[tab,setTab]=useState('Overview'),[merge,setMerge]=useState(false);

  useEffect(()=>{if(data?.redirect_to)ctx.openPatient(data.redirect_to);},[data?.redirect_to]);

  if(!data||data.redirect_to)return <><ErrorBox message={error}/>{loading&&<Loading/>}</>;

  const p=data.patient;

  return <><button className="back-link" onClick={back}><ArrowLeft size={15}/>Patient directory</button><ErrorBox message={error}/><div className="profile-header card"><Avatar name={p.name}/><div className="profile-main"><div className="profile-name"><h1>{p.name}</h1><Badge value={p.active?'Active':'Inactive'}/></div><div className="profile-meta"><span className="mono">{p.uhid}</span><span>{ageLabel(p,ctx.catalog.settings.timezone)} · {p.gender}</span><span><Phone size={13}/>{p.phone||'No mobile'}</span></div><p><MapPin size={13}/>{p.address}</p>{data.aliases.length>0&&<small>Previous identifiers: {data.aliases.join(', ')}</small>}</div><div className="profile-actions"><button className="btn secondary" onClick={()=>edit(p)}><Edit3 size={15}/>Edit details</button><button className="btn primary" disabled={!p.active} onClick={()=>ctx.newVisit(p)}><Plus size={16}/>Create visit</button></div></div>


    <div className="tabs">{['Overview','Visits'].map(x=><button key={x} className={tab===x?'active':''} onClick={()=>setTab(x)}>{x}{x==='Visits'&&<span>{data.visits.length}</span>}</button>)}</div>

    {tab==='Overview'&&<div className="profile-columns"><section className="card detail-card"><h2>Personal details</h2><dl className="details-grid">{[['Full name',p.name],['UHID',p.uhid],['Age',ageLabel(p,ctx.catalog.settings.timezone)],['Date of birth',p.dob?dateText(p.dob):'Not provided'],['Gender',p.gender],['Mobile',p.phone||'No mobile'],['Address',p.address],...Object.entries(p.data).filter(([,v])=>!!v).map(([k,v])=>[k.replaceAll('_',' '),v]),['Registered',dateText(p.created_at,true,ctx.catalog.settings.timezone)]].map(([k,v])=><div key={String(k)}><dt>{k}</dt><dd>{String(v)}</dd></div>)}</dl>{ctx.user.role==='Master'&&<button className="text-btn danger-text" onClick={()=>setMerge(true)}><GitMerge size={15}/>Resolve duplicate patient</button>}</section><div><section className="card detail-card"><div className="section-heading"><h2>Follow-ups</h2><button className="text-btn" disabled={!p.active} onClick={()=>ctx.newFollowup(p)}><Plus size={15}/>Schedule</button></div>{data.followups.length?data.followups.map((f:Row)=><button key={f.id} className="profile-follow" onClick={()=>ctx.openFollowup(f.id)}><span className="stat-icon blue"><CalendarClock size={18}/></span><span><strong>{dateText(f.due_date)} {f.due_time}</strong><small>{f.doctor_name}</small></span><Badge value={f.status}/></button>):<Empty title="No follow-ups yet" text="Schedule a return and set an internal reminder."/>}</section></div></div>}


    {tab==='Visits'&&<section className="card"><div className="card-heading"><div><h2>Visit history</h2><p>A separate record for every attendance.</p></div></div>{data.visits.length?<div className="table-scroll"><table><thead><tr><th>Visit / date</th><th>Doctor</th><th>Type</th><th>Reported complaints</th><th>Status</th><th/></tr></thead><tbody>{data.visits.map((v:Row)=><tr key={v.id}><td><strong>OPD-{String(v.id).padStart(5,'0')}</strong><small className="cell-sub">{dateText(v.arrival_at,true,ctx.catalog.settings.timezone)}</small></td><td>{v.doctor_name}<small className="cell-sub">{v.department_name}</small></td><td>{v.visit_type}</td><td>{v.complaints.map((c:Row)=>c.text).join(', ')}</td><td><Badge value={v.status}/></td><td><button className="icon-btn" aria-label={`Open visit ${v.id}`} onClick={()=>ctx.openVisit(v.id)}><ChevronRight size={17}/></button></td></tr>)}</tbody></table></div>:<Empty title="No visits recorded"/>}</section>}

    {merge&&<MergeForm patient={p} ctx={ctx} close={()=>setMerge(false)}/>}

  </>;

}

function MergeForm({patient,ctx,close}:{patient:Row;ctx:AppContext;close:()=>void}) {

  const[target,setTarget]=useState<Row|null>(null),[reason,setReason]=useState(''),[preview,setPreview]=useState<Row|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);

  const body={source_id:patient.id,target_id:target?.id,source_version:patient.version,target_version:target?.version,reason};

  return <Modal title="Resolve duplicate patient" subtitle="Master only · Review the surviving record carefully." onClose={close} wide><div className="form-body"><ErrorBox message={error}/><div className="warning-box">The current record ({patient.uhid}) will merge into the chosen record. The chosen patient's demographics are retained; all visits and follow-ups remain accessible.</div><h3>Choose the patient record to keep</h3><PatientPicker value={target||undefined} onPick={p=>{setTarget(p);setPreview(null);}} ctx={ctx}/>{target&&<button className="text-btn" onClick={()=>{setTarget(null);setPreview(null);}}>Choose another patient</button>}<Field label="Merge reason" required><textarea minLength={5} value={reason} onChange={e=>{setReason(e.target.value);setPreview(null);}}/></Field>{preview&&<div><h3>Review conflicts</h3><p className="muted">Source values remain in the audit trail. The target values below stay on the patient profile.</p><div className="table-scroll"><table><thead><tr><th>Field</th><th>Source</th><th>Retained</th></tr></thead><tbody>{Object.entries(preview.conflicts).map(([k,v]:[string,any])=><tr key={k}><td>{k}</td><td className="wrap-cell">{String(v.source||'—')}</td><td className="wrap-cell">{String(v.retained||'—')}</td></tr>)}</tbody></table></div><p>{preview.counts.visits} visits · {preview.counts.followups} follow-ups will move.</p></div>}</div><div className="form-actions"><button className="btn secondary" onClick={close}>Cancel</button><button className={`btn ${preview?'danger':'primary'}`} disabled={!target||reason.length<5||busy} onClick={async()=>{setBusy(true);setError('');try{if(!preview)setPreview(await api('/patients/merge/preview','POST',body));else if(window.confirm('Confirm this patient merge? All linked records will move to the surviving UHID.')){const result=await api('/patients/merge/confirm','POST',body);ctx.changed();ctx.notify('Patient records merged');close();ctx.openPatient(result.id);}}catch(e:any){setError(e.message);}finally{setBusy(false);}}}><GitMerge size={16}/>{busy?'Please wait…':preview?'Confirm merge':'Preview merge'}</button></div></Modal>;

}

