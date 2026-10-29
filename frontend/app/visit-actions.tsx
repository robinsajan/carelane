'use client';

import { CalendarCheck, CalendarClock, Edit3, ReceiptText } from 'lucide-react';
import type { Row } from './api';
import type { AppContext } from './page';

export function VisitActions({ visit, ctx }: { visit: Row; ctx: AppContext }) {
  const hasFollowup = Boolean(visit.followup_id);
  return <div className="visit-row-actions">
    <button type="button" className="btn secondary compact edit-visit-btn" title="Edit visit"
      aria-label={`Edit visit for ${visit.patient_name}`} onClick={() => ctx.openVisit(visit.id)}>
      <Edit3 size={14}/><span>Edit</span>
    </button>
    <button type="button" className={`btn secondary compact${hasFollowup ? ' followup-set' : ''}`}
      title={hasFollowup ? 'View or edit existing follow-up' : 'Add follow-up in 7 days; edit before saving'}
      aria-label={`${hasFollowup ? 'View' : 'Add'} follow-up for ${visit.patient_name}`}
      onClick={() => hasFollowup ? ctx.openFollowup(visit.followup_id) : ctx.newFollowup({ id: visit.patient_id, name: visit.patient_name, uhid: visit.uhid, phone: visit.phone }, visit)}>
      {hasFollowup ? <CalendarCheck size={14}/> : <CalendarClock size={14}/>}{hasFollowup ? 'Follow-up set' : 'Follow-up'}
    </button>
    {visit.status==='Completed'&&<button type="button" className={`btn compact ${visit.bill_id?'secondary':'primary'}`} aria-label={`${visit.bill_id?'View bill':'Generate bill'} for ${visit.patient_name}`} onClick={()=>visit.bill_id?ctx.openBill(visit.bill_id):ctx.openBilling(visit.id)}><ReceiptText size={14}/>{visit.bill_id?'View bill':'Generate bill'}</button>}
  </div>;
}
