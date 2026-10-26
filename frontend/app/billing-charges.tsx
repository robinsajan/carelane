'use client';

import { useState } from 'react';
import { Edit3, Plus } from 'lucide-react';
import { api, type Row } from './api';
import { money, priceInput, toPaise } from './money';
import type { AppContext } from './page';
import { Badge, Empty, ErrorBox, Field, Modal, Submit } from './ui';

export function BillingCharges({ctx}:{ctx:AppContext}) {
  const [editing,setEditing]=useState<Row|null>(null);
  const rows=ctx.catalog.billing_charges||[];
  return <section className="card"><div className="card-heading"><div><h2>Billing charges</h2><p>Set reusable charges and unit prices. Inactive charges retain their bill history.</p></div><button className="btn primary" onClick={()=>setEditing({})}><Plus size={16}/>Add charge</button></div>
    {rows.length?<div className="table-scroll"><table><thead><tr><th>Charge</th><th className="money-cell">Unit price</th><th>Status</th><th/></tr></thead><tbody>{rows.map((row:Row)=><tr key={row.id}><td>{row.name}</td><td className="money-cell">{money(row.price_paise)}</td><td><Badge value={row.active?'Active':'Inactive'}/></td><td><button className="icon-btn" aria-label={`Edit charge ${row.name}`} onClick={()=>setEditing(row)}><Edit3 size={16}/></button></td></tr>)}</tbody></table></div>:<Empty title="No billing charges yet" text="Add charges such as dressing or injection for staff to select on bills."/>}
    {editing&&<ChargeForm key={editing.id||'new'} row={editing} ctx={ctx} close={()=>setEditing(null)}/>}
  </section>;
}

function ChargeForm({row,ctx,close}:{row:Row;ctx:AppContext;close:()=>void}) {
  const [name,setName]=useState(row.name||''),[price,setPrice]=useState(priceInput(row.price_paise)),[active,setActive]=useState(row.active!==false&&row.active!==0),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const paise=toPaise(price);
  return <Modal title={`${row.id?'Edit':'Add'} billing charge`} onClose={close}><form onSubmit={async e=>{e.preventDefault();if(paise==null||paise<=0)return;setBusy(true);setError('');try{await api('/billing-charges'+(row.id?`/${row.id}`:''),row.id?'PATCH':'POST',{name,price_paise:paise,active,...(row.id?{version:row.version}:{})});ctx.changed();ctx.notify('Billing charge saved');close();}catch(e:any){setError(e.message);}finally{setBusy(false);}}}><div className="form-body"><ErrorBox message={error}/><Field label="Charge name" required><input required minLength={2} maxLength={200} value={name} onChange={e=>setName(e.target.value)}/></Field><Field label="Unit price (₹)" required><input type="number" required min="0.01" max="1000000" step="0.01" value={price} onChange={e=>setPrice(e.target.value)}/></Field><label className="check-label"><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/>Active</label></div><div className="form-actions"><button type="button" className="btn secondary" onClick={close}>Cancel</button><Submit busy={busy}>{row.id?'Save changes':'Add charge'}</Submit></div></form></Modal>;
}
