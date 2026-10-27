'use client';

import { useRef, useState } from 'react';
import { ArrowRight, Plus, Printer, ReceiptText, Trash2 } from 'lucide-react';
import { api, dateText, query, type Row } from './api';
import { money, priceInput, toPaise } from './money';
import type { AppContext } from './page';
import { Empty, ErrorBox, Field, Loading, Modal, Pager, SearchBox, Select, Submit, useLoad } from './ui';

export function Billing({ctx}:{ctx:AppContext}) {
  const [tab,setTab]=useState('Completed visits');
  return <><div className="page-heading"><div><h1>Billing</h1><p>Generate bills for completed visits and manage payments.</p></div></div><div className="tabs"><button className={tab==='Completed visits'?'active':''} onClick={()=>setTab('Completed visits')}>Completed visits</button><button className={tab==='Bills & payments'?'active':''} onClick={()=>setTab('Bills & payments')}>Bills & payments</button></div>{tab==='Completed visits'?<CompletedBillingVisits ctx={ctx}/>:<BillsList ctx={ctx}/>}</>;
}

export function CompletedBillingVisits({ctx}:{ctx:AppContext}) {
  const [day,setDay]=useState(ctx.catalog.today),[q,setQ]=useState(''),[page,setPage]=useState(1);
  const path='/billing-visits?'+query({start:day,end:day,q,page});
  const {data,error,loading,dataPath}=useLoad(path,ctx.refresh);
  const current=dataPath===path?data:null;
  return <section className="card"><div className="card-heading"><div><h2>Completed visits</h2><p>Completed visits for the selected date.</p></div></div><div className="list-toolbar wrap"><SearchBox value={q} onChange={value=>{setQ(value);setPage(1);}} placeholder="Search patient name or UHID…"/><Field label="Visit date"><input required type="date" value={day} onInput={e=>{setDay(e.currentTarget.value||ctx.catalog.today);setPage(1);}}/></Field></div><ErrorBox message={error}/>{loading&&!current?<Loading/>:current?.items.length?<><div className="table-scroll"><table><thead><tr><th>Patient</th><th>Visit date</th><th>Doctor</th><th>Visit type</th><th>Billing</th><th/></tr></thead><tbody>{current.items.map((visit:Row)=><tr key={visit.id}><td><strong>{visit.patient_name}</strong><small className="cell-sub">{visit.uhid}</small></td><td>{dateText(visit.visit_date)}</td><td>{visit.doctor_name}</td><td>{visit.visit_type}</td><td>{visit.bill_id?'Bill generated':'Not billed'}</td><td><button className="btn secondary compact" aria-label={`${visit.bill_id?'View bill':'Generate bill'} for ${visit.patient_name}`} onClick={()=>visit.bill_id?ctx.openBill(visit.bill_id):ctx.openBilling(visit.id)}><ReceiptText size={14}/>{visit.bill_id?'View bill':'Generate bill'}</button></td></tr>)}</tbody></table></div><Pager data={current} page={page} setPage={setPage}/></>:!error&&<Empty title="No completed visits" text="Completed OPD visits appear here, ready for billing. Change the date or search to see other visits."/>}</section>;
}

function BillsList({ctx}:{ctx:AppContext}) {
  const [day,setDay]=useState(ctx.catalog.today),[status,setStatus]=useState(''),[q,setQ]=useState(''),[page,setPage]=useState(1);
  const path='/bills?'+query({start:day,end:day,status,q,page});
  const {data,error,loading,dataPath}=useLoad(path,ctx.refresh);
  const current=dataPath===path?data:null;
  return <>
    <section className="card"><div className="list-toolbar wrap"><SearchBox value={q} onChange={value=>{setQ(value);setPage(1);}} placeholder="Search patient name or UHID…"/><Field label="Bill date"><input required type="date" value={day} onInput={e=>{setDay(e.currentTarget.value||ctx.catalog.today);setPage(1);}}/></Field><Select aria-label="Payment status filter" value={status} onChange={e=>{setStatus(e.target.value);setPage(1);}}><option value="">All payment statuses</option>{['Unpaid','Part paid','Paid'].map(value=><option key={value}>{value}</option>)}</Select></div>
    <ErrorBox message={error}/>{loading&&!current?<Loading/>:current?.items.length?<><div className="table-scroll"><table><thead><tr><th>Bill</th><th>Patient</th><th>Doctor</th><th className="money-cell">Total</th><th className="money-cell">Paid</th><th className="money-cell">Balance</th><th>Status</th><th/></tr></thead><tbody>{current.items.map((bill:Row)=><tr key={bill.id}><td><strong>{bill.number}</strong><small className="cell-sub">{dateText(bill.bill_date)}</small></td><td><strong>{bill.snapshot.patient.name}</strong><small className="cell-sub">{bill.snapshot.patient.uhid}</small></td><td>{bill.snapshot.doctor_name}</td><td className="money-cell">{money(bill.total_paise)}</td><td className="money-cell">{money(bill.paid_paise)}</td><td className="money-cell">{money(bill.balance_paise)}</td><td>{bill.payment_status}</td><td><button className="text-btn" onClick={()=>ctx.openBill(bill.id)}>Open<ArrowRight size={14}/></button></td></tr>)}</tbody></table></div><Pager data={current} page={page} setPage={setPage}/></>:!error&&<Empty title="No bills for this selection" text="Generate a bill from Completed visits, or select another date."/>}</section>
  </>;
}

export function BillDialog({visitId,billId,ctx,close}:{visitId?:number;billId?:number;ctx:AppContext;close:()=>void}) {
  const [saved,setSaved]=useState<Row|null>(null);
  const {data,error,loading}=useLoad(billId?`/bills/${billId}`:`/visits/${visitId}/billing`,ctx.refresh);
  const remote=billId?data:data?.bill;
  const bill=saved&&(!remote||saved.version>remote.version)?saved:remote;
  const changed=(value:Row)=>{setSaved(value);ctx.changed();};
  return <Modal title={bill?bill.number:'Generate bill'} subtitle={bill?`${bill.snapshot.patient.name} · ${bill.payment_status}`:'Consultation fee and additional charges'} onClose={close} wide guard={!bill}>
    <ErrorBox message={error}/>{!data&&!saved?loading&&<Loading/>:bill?<BillView bill={bill} ctx={ctx} saved={changed}/>:data?.visit.status!=='Completed'?<div className="form-body"><p>Complete this visit before generating a bill.</p></div>:<BillDraft quote={data} ctx={ctx} saved={changed}/>}
  </Modal>;
}

export function BillDraft({quote,ctx,saved,bill,cancel}:{quote:Row;ctx:AppContext;saved:(bill:Row)=>void;bill?:Row;cancel?:()=>void}) {
  const [source,setSource]=useState(quote),[extras,setExtras]=useState<Row[]>((bill?.lines||[]).filter((line:Row)=>line.kind==='Additional charge').map((line:Row)=>({...line,quantity:String(line.quantity),price:priceInput(line.unit_price_paise)}))),[reason,setReason]=useState(''),[note,setNote]=useState(bill?.note||''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const key=useRef(crypto.randomUUID());
  const visit=source.visit;
  const priced=extras.map(line=>({description:String(line.description),...(line.charge_id?{charge_id:line.charge_id,charge_version:line.charge_version}:{}),unit_price_paise:toPaise(line.price),quantity:Number(line.quantity)}));
  const valid=source.consultation_fee_paise!=null&&priced.every(line=>line.description.trim()&&line.unit_price_paise!=null&&line.unit_price_paise>0&&Number.isInteger(line.quantity)&&line.quantity>=1&&line.quantity<=999);
  const total=(source.consultation_fee_paise||0)+priced.reduce((sum,line)=>sum+(line.unit_price_paise||0)*(Number.isInteger(line.quantity)?line.quantity:0),0);
  const edit=(index:number,field:string,value:string)=>setExtras(rows=>rows.map((line,i)=>i===index?{...line,[field]:value}:line));
  return <form onSubmit={async e=>{e.preventDefault();if(!valid)return;setBusy(true);setError('');try{saved(await api(bill?`/bills/${bill.id}`:'/bills',bill?'PATCH':'POST',{...(bill?{version:bill.version,reason}:{visit_id:visit.id,visit_version:visit.version,doctor_version:source.doctor_version}),extras:priced.map(line=>({...line,description:line.description.trim()})),note},key.current));ctx.notify(bill?'Bill updated':'Bill generated');}catch(e:any){setError(e.message);}finally{setBusy(false);}}}>
    <div className="form-body"><ErrorBox message={error}/>{error&&<button type="button" className="text-btn" onClick={async()=>{try{if(bill){saved(await api(`/bills/${bill.id}`));return;}const latest=await api(`/visits/${visit.id}/billing`);if(latest.bill)saved(latest.bill);else setSource(latest);setError('');}catch(e:any){setError(e.message);}}}>{bill?'Reload saved bill':'Reload latest visit and fees'}</button>}
      <div className="bill-patient-summary"><strong>{visit.patient_name}</strong><span>{visit.uhid} · {visit.doctor_name} · {visit.visit_type} visit</span></div>
      <div className="bill-consultation"><span>Doctor consultation fee</span><strong>{money(source.consultation_fee_paise)}</strong></div>
      {source.consultation_fee_paise==null&&<div className="warning-box">Master must set the {visit.visit_type==='Follow-up'?'follow-up':'new-visit'} consultation fee in Settings → Doctors before generating this bill.</div>}
      <div className="section-heading spaced-top"><h3>Additional charges</h3><button type="button" className="text-btn" disabled={extras.length>=50} onClick={()=>setExtras(rows=>[...rows,{description:'',quantity:'1',price:''}])}><Plus size={15}/>Add charge</button></div>
      <Field label="Saved billing charge"><Select value="" disabled={extras.length>=50} onChange={e=>{const charge=(ctx.catalog.billing_charges||[]).find((item:Row)=>String(item.id)===e.target.value);if(charge)setExtras(rows=>[...rows,{charge_id:charge.id,charge_version:charge.version,description:charge.name,quantity:'1',price:priceInput(charge.price_paise)}]);}}><option value="">Select a charge from master data</option>{(ctx.catalog.billing_charges||[]).filter((item:Row)=>item.active).map((item:Row)=><option key={item.id} value={item.id}>{item.name} · {money(item.price_paise)}</option>)}</Select></Field>
      {!extras.length&&<p className="muted">No additional charges.</p>}
      {extras.map((line,index)=><div className="bill-extra-row" key={index}><Field label={`Charge ${index+1}`} required><input required readOnly={!!line.charge_id} maxLength={200} value={line.description} onChange={e=>edit(index,'description',e.target.value)} placeholder="Charge description"/></Field><Field label={`Quantity ${index+1}`} required><input type="number" required min={1} max={999} step={1} value={line.quantity} onChange={e=>edit(index,'quantity',e.target.value)}/></Field><Field label={`Unit price ${index+1} (₹)`} required><input type="number" required min="0.01" max="1000000" step="0.01" readOnly={!!line.charge_id} value={line.price} onChange={e=>edit(index,'price',e.target.value)}/></Field><button type="button" className="icon-btn" aria-label={`Remove charge ${index+1}`} onClick={()=>setExtras(rows=>rows.filter((_,i)=>i!==index))}><Trash2 size={16}/></button></div>)}
      {bill&&<Field label="Reason for edit" hint="Saved with this revision for review."><textarea rows={2} maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/></Field>}<Field label="Bill note"><textarea rows={2} maxLength={1000} value={note} onChange={e=>setNote(e.target.value)}/></Field>
      {bill&&total<bill.paid_paise&&<div className="warning-box">Total must be at least {money(bill.paid_paise)}, the amount already received.</div>}<div className="bill-draft-total"><span>Total</span><strong>{money(total)}</strong></div><p className="muted">{bill?'Consultation fee and existing payments stay unchanged. The total must cover payments received.':'Review charges before generating; record full or partial payments afterwards.'}</p>
    </div><div className="form-actions">{cancel&&<button type="button" className="btn secondary" onClick={cancel}>Cancel</button>}<button className="btn primary" disabled={busy||!valid||total>1_000_000_000||total<(bill?.paid_paise||0)}><ReceiptText size={16}/>{busy?'Saving…':bill?'Save bill changes':'Generate bill'}</button></div>
  </form>;
}

function BillView({bill,ctx,saved,historical=false}:{bill:Row;ctx:AppContext;saved:(bill:Row)=>void;historical?:boolean}) {
  const details=bill.snapshot;
  const [editing,setEditing]=useState(false),[historyOpen,setHistoryOpen]=useState(false);
  if(historyOpen)return <BillHistory bill={bill} ctx={ctx} close={()=>setHistoryOpen(false)}/>;
  if(editing)return <BillDraft key={bill.version} bill={bill} quote={{visit:{id:bill.visit_id,patient_name:details.patient.name,uhid:details.patient.uhid,doctor_name:details.doctor_name,visit_type:details.visit_type},consultation_fee_paise:bill.lines.find((line:Row)=>line.kind==='Consultation')?.unit_price_paise}} ctx={ctx} saved={value=>{saved(value);setEditing(false);}} cancel={()=>setEditing(false)}/>;
  return <>{historical&&<div className="info-box bill-history-notice">Historical revision v{bill.bill_revision}. Amounts and payments are shown as recorded at this revision.</div>}<div className="form-body bill-print-surface">
    <header className="bill-document-header"><div><h2>{details.hospital.hospital_name}</h2><p>{details.hospital.address}</p><p>{details.hospital.phone}</p></div><div><h3>OPD bill · v{bill.bill_revision||1}</h3><strong>{bill.number}</strong><p>{dateText(bill.bill_date)}</p></div></header>
    <div className="bill-document-parties"><div><strong>{details.patient.name}</strong><p>UHID: {details.patient.uhid}</p><p>{details.patient.address}</p><p>{details.patient.phone}</p></div><div><strong>{details.doctor_name}</strong><p>{details.department_name}</p><p>{details.visit_type} · Visit {bill.visit_id} · Token {details.token}</p><p>Visit date: {dateText(details.visit_date)}</p></div></div>
    <div className="table-scroll"><table className="bill-lines"><thead><tr><th>Description</th><th className="money-cell">Qty</th><th className="money-cell">Unit price</th><th className="money-cell">Amount</th></tr></thead><tbody>{bill.lines.map((line:Row,i:number)=><tr key={i}><td>{line.description}</td><td className="money-cell">{line.quantity}</td><td className="money-cell">{money(line.unit_price_paise)}</td><td className="money-cell">{money(line.amount_paise)}</td></tr>)}</tbody></table></div>
    <dl className="bill-totals"><div><dt>Total</dt><dd>{money(bill.total_paise)}</dd></div><div><dt>Payments received</dt><dd>{money(bill.paid_paise)}</dd></div><div><dt>Balance due</dt><dd>{money(bill.balance_paise)}</dd></div></dl>
    {bill.note&&<p className="bill-note">{bill.note}</p>}
    {bill.payments.length>0&&<><h3>Payments</h3><div className="bill-payment-history">{bill.payments.map((payment:Row)=><div key={payment.id}><span>{dateText(payment.created_at,true,ctx.catalog.settings.timezone)} · {payment.method}{payment.reference?` · ${payment.reference}`:''}<small>Recorded by {payment.receiver_name}</small></span><strong>{money(payment.amount_paise)}</strong></div>)}</div></>}
    <p className="bill-issued-by">Issued by {details.issued_by} · {bill.payment_status}</p>
  </div>
  {!historical&&bill.balance_paise>0&&<PaymentForm bill={bill} ctx={ctx} saved={saved}/>}
  <div className="form-actions bill-screen-actions">{!historical&&<><button className="btn secondary" onClick={()=>setEditing(true)}>Edit bill</button><button className="btn secondary" onClick={()=>setHistoryOpen(true)}>Version history · v{bill.bill_revision||1}</button></>}<button className="btn secondary" onClick={()=>window.print()}><Printer size={16}/>Print {historical?`v${bill.bill_revision}`:'bill'}</button></div>{historyOpen&&<BillHistory bill={bill} ctx={ctx} close={()=>setHistoryOpen(false)}/>}</>;
}

export function PaymentForm({bill,ctx,saved}:{bill:Row;ctx:AppContext;saved:(bill:Row)=>void}) {
  const [amount,setAmount]=useState(priceInput(bill.balance_paise)),[method,setMethod]=useState('Cash'),[reference,setReference]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const key=useRef(crypto.randomUUID());
  const paise=toPaise(amount);
  return <form className="bill-payment-form" onSubmit={async e=>{e.preventDefault();if(paise==null||paise<=0||paise>bill.balance_paise)return;setBusy(true);setError('');try{saved(await api(`/bills/${bill.id}/payments`,'POST',{version:bill.version,amount_paise:paise,method,reference},key.current));key.current=crypto.randomUUID();setAmount('');setReference('');ctx.notify('Payment recorded');}catch(e:any){setError(e.message);if(e.status===409)ctx.changed();}finally{setBusy(false);}}}>
    <h3>Record payment</h3><p className="muted">Outstanding: {money(bill.balance_paise)}</p><ErrorBox message={error}/>
    <div className="form-grid"><Field label="Payment amount (₹)" required><input type="number" required min="0.01" step="0.01" max={priceInput(bill.balance_paise)} value={amount} onChange={e=>setAmount(e.target.value)}/></Field><Field label="Payment method"><Select value={method} onChange={e=>setMethod(e.target.value)}>{['Cash','UPI','Card','Bank transfer','Other'].map(value=><option key={value}>{value}</option>)}</Select></Field></div>
    <Field label="Payment reference"><input maxLength={150} value={reference} onChange={e=>setReference(e.target.value)} placeholder="Optional transaction or receipt reference"/></Field>
    <div className="bill-payment-buttons"><button type="button" className="text-btn" onClick={()=>setAmount(priceInput(bill.balance_paise))}>Use full balance</button><button className="btn primary" disabled={busy||paise==null||paise<=0||paise>bill.balance_paise}>{busy?'Recording…':'Record payment'}</button></div>
  </form>;
}

function BillHistory({bill,ctx,close}:{bill:Row;ctx:AppContext;close:()=>void}) {
  const {data,error,loading}=useLoad(`/bills/${bill.id}/revisions`,bill.bill_revision);
  const [selected,setSelected]=useState<Row|null>(null),[busy,setBusy]=useState(false),[loadError,setLoadError]=useState('');
  return <Modal title={`${bill.number} · Version history`} subtitle="Saved bill revisions are read-only. The highest version is the latest bill." onClose={close} wide guard={false}>
    {selected?<><div className="form-body"><button type="button" className="text-btn" onClick={()=>setSelected(null)}>Back to version history</button><p className="muted">v{selected.revision} · {dateText(selected.recorded_at,true,ctx.catalog.settings.timezone)} · {selected.actor_name}</p>{selected.reason&&<p>{selected.reason}</p>}</div><BillView bill={selected.bill} ctx={ctx} saved={()=>{}} historical/></>:<div className="form-body"><ErrorBox message={error||loadError}/>{loading&&!data?<Loading/>:<div className="bill-revision-list">{data?.items.map((revision:Row)=><div className="bill-revision-row" key={revision.revision}><div><strong>v{revision.revision}{revision.revision===bill.bill_revision?' · Latest':''}</strong><small>{dateText(revision.recorded_at,true,ctx.catalog.settings.timezone)} · {revision.actor_name}</small><p>{revision.reason||'No reason recorded'}</p></div><strong>{money(revision.total_paise)}</strong><button type="button" className="btn secondary compact" disabled={busy} onClick={async()=>{setBusy(true);setLoadError('');try{setSelected(await api(`/bills/${bill.id}/revisions/${revision.revision}`));}catch(e:any){setLoadError(e.message);}finally{setBusy(false);}}}>View v{revision.revision}</button></div>)}</div>}</div>}
  </Modal>;
}
