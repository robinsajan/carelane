'use client';

import { Check, Circle } from 'lucide-react';

export const passwordChecks=(value:string)=>[
  {label:'At least 12 characters',met:value.length>=12&&value.length<=128},
  {label:'One uppercase letter (A–Z)',met:/[A-Z]/.test(value)},
  {label:'One number (0–9)',met:/[0-9]/.test(value)},
  {label:'One symbol, such as ! @ #',met:/[^\p{L}\p{N}\s]/u.test(value)},
];
export const validPassword=(value:string)=>passwordChecks(value).every(check=>check.met);

export function PasswordRules({value}:{value:string}) {
  return <ul className="password-rules" aria-label="Password requirements">{passwordChecks(value).map(check=><li key={check.label} data-met={check.met}>{check.met?<Check size={13} aria-hidden="true"/>:<Circle size={11} aria-hidden="true"/>}<span>{check.label}</span><span className="sr-only">{check.met?' — met':' — not met'}</span></li>)}</ul>;
}
