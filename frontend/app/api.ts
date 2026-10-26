export type Row = Record<string, any>;
export class ApiError extends Error {
  status: number; detail: any;
  constructor(message: string, status: number, detail?: any) { super(message); this.status = status; this.detail = detail; }
}
export async function api(path: string, method = 'GET', body?: unknown, key?: string): Promise<any> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method, credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-OPD-Request': '1', ...(key ? { 'Idempotency-Key': key } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch { throw new ApiError('Cannot reach the hospital server. Check your network and retry.', 0); }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = result.detail;
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((x: Row) => `${x.loc.slice(1).join(' ')}: ${x.msg}`).join('; ') : detail?.message || 'The request could not be completed.';
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('opd-session-expired'));
    throw new ApiError(message, response.status, detail);
  }
  return result;
}
export const query = (values: Row) => new URLSearchParams(Object.fromEntries(Object.entries(values).filter(([, v]) => v !== undefined && v !== null).map(([k,v]) => [k, String(v)]))).toString();
export function dateText(value: string | null, time = false, zone = 'Asia/Kolkata') {
  if (!value) return '—';
  const d = new Date(value.length === 10 ? value + 'T12:00:00' : value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric', ...(time ? { hour: '2-digit', minute: '2-digit' } : {}), timeZone: zone }).format(d);
}
export function hospitalDate(zone = 'Asia/Kolkata') { return new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()); }
export function localInput(value: string, zone = 'Asia/Kolkata') {
  const parts = new Intl.DateTimeFormat('sv-SE', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
  return parts.replace(' ', 'T');
}
