'use client';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { AlertCircle, ArrowLeft, ArrowRight, Check, ChevronDown, Eye, EyeOff, Search, X } from 'lucide-react';
import { api, type Row } from './api';

export function useLoad(path: string, refresh: number = 0) {
  const [data, setData] = useState<any>(null), [error, setError] = useState(''), [loading, setLoading] = useState(true);
  const [dataPath, setDataPath] = useState('');
  useEffect(() => { let active = true; setLoading(true); setError('');
    api(path).then(x => { if (active) { setData(x); setDataPath(path); } }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, refresh]);
  return { data, error, loading, dataPath };
}
export function Badge({ value }: { value: string }) {
  const style = ['Completed','Attended','Active','Confirmed'].includes(value) ? 'green' : ['Cancelled','No Show','Overdue','Inactive'].includes(value) ? 'red' : ['Waiting','On Hold','Unknown'].includes(value) ? 'amber' : 'blue';
  return <span className={`badge ${style}`}><i />{value}</span>;
}
export function Avatar({ name, small = false }: {name: string; small?: boolean}) { return <span className={`avatar ${small ? 'small' : ''}`}>{name.split(' ').filter(Boolean).map(x=>x[0]).slice(0,2).join('').toUpperCase() || '?'}</span>; }
export function ErrorBox({ message }: {message?: string}) { return message ? <div role="alert" className="error-box"><AlertCircle size={17}/><span>{message}</span></div> : null; }
export function Empty({ title = 'Nothing here yet', text = 'Records will appear here once they are added.', action }: {title?: string; text?: string; action?: ReactNode}) {
  return <div className="empty"><div className="empty-symbol"><Search size={25}/></div><h3>{title}</h3><p>{text}</p>{action}</div>;
}
export function Loading() { return <div className="loading"><span className="spinner"/>Loading records…</div>; }
export function Field({ label, required, children, hint, wide }: {label: string; required?: boolean; children: ReactNode; hint?: string; wide?: boolean}) { return <label className={`field ${wide ? 'wide' : ''}`}><span>{label}{required && <b> *</b>}</span>{children}{hint && <small>{hint}</small>}</label>; }
export function Select({ children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) { return <span className="select-wrap"><select {...props}>{children}</select><ChevronDown size={14}/></span>; }
export function SearchBox({ value, onChange, placeholder='Search by name, UHID or phone…' }: {value:string; onChange:(v:string)=>void; placeholder?:string}) { return <div className="search-box"><Search size={18} aria-hidden="true"/><input type="text" autoComplete="off" spellCheck={false} aria-label={placeholder} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder}/>{value && <button type="button" className="search-clear" onClick={()=>onChange('')} aria-label="Clear search"><X size={14}/></button>}</div>; }
export function Pager({ data, page, setPage }: {data: Row | null; page:number; setPage:(v:number)=>void}) {
  if (!data) return null;
  const size = data.items?.length || 0, total = data.total || 0;
  return <div className="pager"><span>{total ? `${(page-1)*(data.kind ? 30 : data.page_size || 30)+1}–${Math.min((page-1)*(data.kind ? 30 : data.page_size || 30)+size,total)} of ${total} records` : '0 records'}</span><div><button className="btn secondary compact" disabled={page===1} onClick={()=>setPage(page-1)}><ArrowLeft size={14}/>Previous</button><span className="page-number">{page}</span><button className="btn secondary compact" disabled={!size || size<(data.page_size || 30) || page*(data.page_size || 30)>=total} onClick={()=>setPage(page+1)}>Next<ArrowRight size={14}/></button></div></div>;
}
export function Modal({ title, subtitle, children, onClose, wide=false, guard=true, drawer=false }: {title:string; subtitle?:string; children:ReactNode; onClose:()=>void; wide?:boolean; guard?:boolean; drawer?:boolean}) {
  const dirty = useRef(false), ref=useRef<HTMLDivElement>(null), closeRef=useRef(onClose), titleId=useId();
  closeRef.current=onClose;
  const close = () => { if (!guard || !dirty.current || window.confirm('Discard unsaved changes?')) closeRef.current(); };
  useEffect(()=>{
    const old=document.activeElement as HTMLElement;
    const bodyOverflow=document.body.style.overflow; document.body.style.overflow='hidden';
    const first = ref.current?.querySelector<HTMLElement>('input,select,textarea,button'); first?.focus();
    const listener = (e:KeyboardEvent)=>{
      const dialogs = document.querySelectorAll('[role="dialog"]');
      if (dialogs[dialogs.length-1] !== ref.current) return;
      if(e.key==='Escape') { e.preventDefault(); if (!guard || !dirty.current || window.confirm('Discard unsaved changes?')) closeRef.current(); }
      if(e.key==='Tab') {const els=Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]')||[]).filter(x=>x.offsetParent!==null); const first=els[0],last=els[els.length-1]; if(e.shiftKey && document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}
    };
    const unload=(e:BeforeUnloadEvent)=>{if(dirty.current&&guard)e.preventDefault();};
    window.addEventListener('keydown',listener);window.addEventListener('beforeunload',unload);
    return ()=>{document.body.style.overflow=bodyOverflow;window.removeEventListener('keydown',listener);window.removeEventListener('beforeunload',unload);old?.focus();};
  },[guard]);
  return <div className={`modal-backdrop ${drawer?'drawer-backdrop':''}`} onMouseDown={e=>{if(e.target===e.currentTarget)close();}}><div ref={ref} className={`modal ${wide?'wide-modal':''} ${drawer?'side-drawer':''}`} role="dialog" aria-modal="true" aria-labelledby={titleId} onInput={()=>{dirty.current=true;}} onChange={()=>{dirty.current=true;}}><div className="modal-head"><div><h2 id={titleId}>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div><button className="icon-btn" aria-label="Close dialog" onClick={close}><X size={20}/></button></div>{children}</div></div>;
}
export function Submit({ busy, children='Save changes' }: {busy:boolean;children?:ReactNode}) { return <button type="submit" className="btn primary" disabled={busy}>{busy?<span className="spinner"/>:<Check size={16}/>} {busy?'Saving…':children}</button>; }

export function PasswordInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
 const [visible,setVisible]=useState(false);
 return <span className="password-input"><input {...props} type={visible?'text':'password'}/><button type="button" className="password-toggle" aria-label={visible?'Hide password':'Show password'} aria-pressed={visible} disabled={props.disabled} onClick={e=>{e.preventDefault();setVisible(value=>!value);}}>{visible?<EyeOff size={18}/>:<Eye size={18}/>}</button></span>;
}
