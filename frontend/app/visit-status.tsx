'use client';

import { useState } from 'react';
import { Check, X } from 'lucide-react';
import { api, type Row } from './api';
import type { AppContext } from './page';
import { Select } from './ui';

const statuses = ['Waiting', 'Being Attended', 'Completed', 'Cancelled'];

export function InlineVisitStatus({ visit, ctx }: { visit: Row; ctx: AppContext }) {
  const [confirmed, setConfirmed] = useState<Row | null>(null);
  const [draft, setDraft] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const current = confirmed && confirmed.version > visit.version ? confirmed : visit;

  const save = async (status: string, note: string) => {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const updated = await api(`/visits/${current.id}`, 'PATCH', {
        version: current.version, status, reason: note,
      });
      setConfirmed(updated);
      setDraft('');
      setReason('');
      ctx.notify(`Visit marked ${status.toLowerCase()}`);
      ctx.changed();
    } catch (e: any) {
      setError(e.message);
      if (e.status === 409) ctx.changed();
    } finally {
      setBusy(false);
    }
  };

  const choose = (status: string) => {
    setError('');
    if (status === current.status) { setDraft(''); setReason(''); return; }
    if (status === 'Cancelled' || ['Completed', 'Cancelled', 'No Show'].includes(current.status)) {
      setDraft(status);
      setReason('');
    } else {
      setDraft('');
      void save(status, '');
    }
  };

  return <div className="inline-visit-status">
    <Select aria-label={`Status for ${visit.patient_name}, visit ${visit.id}`}
      value={draft || (statuses.includes(current.status) ? current.status : '')}
      disabled={busy} onChange={e => choose(e.target.value)}>
      {!statuses.includes(current.status) && <option value="" disabled>{current.status} — change status</option>}
      {statuses.map(status => <option key={status}>{status}</option>)}
    </Select>
    {busy && <small role="status">Saving status…</small>}
    {draft && <div className="inline-status-reason">
      <label htmlFor={`visit-reason-${visit.id}`}>{draft === 'Cancelled' ? 'Cancellation reason' : 'Reason for correction'}</label>
      <input id={`visit-reason-${visit.id}`} value={reason} disabled={busy}
        maxLength={1000} placeholder="Enter a reason" onChange={e => setReason(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && reason.trim().length >= 3) { e.preventDefault(); void save(draft, reason.trim()); } }} />
      <div>
        <button type="button" className="btn primary compact" disabled={busy || reason.trim().length < 3}
          onClick={() => void save(draft, reason.trim())}><Check size={12}/>Save status</button>
        <button type="button" className="icon-btn" disabled={busy} aria-label="Discard status change"
          onClick={() => { setDraft(''); setReason(''); setError(''); }}><X size={14}/></button>
      </div>
    </div>}
    {error && <small className="inline-status-error" role="alert">{error}</small>}
  </div>;
}
