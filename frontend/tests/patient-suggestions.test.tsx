import { PasswordForm } from '../app/page';
import { Dashboard } from '../app/page';
import { Billing, BillDraft, PaymentForm } from '../app/billing';
import { toPaise } from '../app/money';
import assert from 'node:assert/strict';
import { after, afterEach, before, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React from 'react';
import type { AppContext } from '../app/page';
import { PatientForm } from '../app/patients';
import { InlineVisitStatus } from '../app/visit-status';
import { VisitActions } from '../app/visit-actions';
import { Queue } from '../app/visits';
import { DoctorQueuePatient, DoctorAvailability } from '../app/doctor-queues';
import { FollowupForm, FollowupsPanel } from '../app/followups';

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost:3000' });
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true },
  document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true },
  HTMLElement: { value: dom.window.HTMLElement, configurable: true },
  Event: { value: dom.window.Event, configurable: true },
  FormData: { value: dom.window.FormData, configurable: true },
  IS_REACT_ACT_ENVIRONMENT: { value: true, writable: true, configurable: true },
});

let render: typeof import('@testing-library/react').render;
let screen: typeof import('@testing-library/react').screen;
let waitFor: typeof import('@testing-library/react').waitFor;
let cleanup: typeof import('@testing-library/react').cleanup;
let fireEvent: typeof import('@testing-library/react').fireEvent;
let userEvent: typeof import('@testing-library/user-event').default;
const originalFetch = globalThis.fetch;
const existing = {
  id: 42, uhid: 'AB12CD34', name: 'Ananya Patil', first_name: 'Ananya', middle_name: '', surname: 'Patil',
  gender: 'Female', age_value: 34, age_unit: 'Years', dob: null, approximate: true,
  age_recorded_on: '2026-10-23', phone: '9000000001', no_mobile: false,
  address: 'Fictional existing patient address', data: { city: 'Test City', emergency_name: 'Test Caregiver' },
  active: true, version: 7,
};
const ctx = { catalog: { today: '2026-10-23', settings: { timezone: 'Asia/Kolkata' }, lookups: [] } } as unknown as AppContext;
let requests: { path: string; method: string; body: any }[] = [];

before(async () => {
  ({ render, screen, waitFor, cleanup, fireEvent } = await import('@testing-library/react'));
  userEvent = (await import('@testing-library/user-event')).default;
});
beforeEach(() => {
  requests = [];
  globalThis.fetch = async (input, init) => {
    const path = String(input), method = init?.method || 'GET', body = init?.body ? JSON.parse(String(init.body)) : null;
    requests.push({ path, method, body });
    if (method === 'GET') return Response.json({ items: [existing], total: 1, page: 1 });
    if (method === 'PATCH' && path === '/api/patients/42') return Response.json({ ...existing, ...body, version: 8 });
    throw new Error(`Unexpected request: ${method} ${path}`);
  };
});
afterEach(() => { cleanup(); globalThis.fetch = originalFetch; });
after(() => dom.window.close());

async function selectExisting() {
  const user = userEvent.setup({ document: dom.window.document });
  await user.type(screen.getByRole('combobox', { name: /^Name\s*\*$/ }), 'Ananya');
  const option = await screen.findByRole('option', { name: /Ananya Patil.*AB12CD34/ });
  await user.click(option);
  return user;
}

test('name suggestions populate all details and Create visit reuses the existing UHID without saving a new patient', async () => {
  const saved: any[][] = [];
  render(<PatientForm ctx={ctx} close={() => {}} saved={(...args) => saved.push(args)} />);
  const user = await selectExisting();
  assert.equal((screen.getByPlaceholderText('Patient full name') as HTMLInputElement).value, 'Ananya Patil');
  assert.equal(screen.queryByLabelText('Surname'), null);
  assert.equal(screen.queryByLabelText('Middle name'), null);
  assert.equal((screen.getByLabelText(/^Gender\s*\*$/) as HTMLSelectElement).value, 'Female');
  assert.equal((screen.getByPlaceholderText('10-digit mobile number') as HTMLInputElement).value, existing.phone);
  assert.equal((screen.getByPlaceholderText('House / street / locality') as HTMLTextAreaElement).value, existing.address);
  assert.equal((screen.getByLabelText('City') as HTMLInputElement).value, 'Test City');
  assert.equal((screen.getByLabelText('Emergency contact name') as HTMLInputElement).value, 'Test Caregiver');
  await user.click(screen.getByRole('button', { name: 'Create visit' }));
  await waitFor(() => assert.equal(saved.length, 1));
  assert.equal(saved[0][0].id, 42);
  assert.equal(saved[0][0].uhid, 'AB12CD34');
  assert.equal(saved[0][1], true);
  assert.equal(saved[0][2], true);
  assert.ok(requests.every(r => r.method === 'GET'), 'Reusing an unchanged patient must not register or update them');
  assert.ok(requests.some(r => r.path.includes('name_only=true')), 'Registration lookup must request name-only matching');
});

test('edits after selection update the existing versioned patient before creating a visit', async () => {
  const saved: any[][] = [];
  render(<PatientForm ctx={ctx} close={() => {}} saved={(...args) => saved.push(args)} />);
  const user = await selectExisting();
  const address = screen.getByPlaceholderText('House / street / locality');
  await user.clear(address);
  await user.type(address, 'Updated fictional address');
  await user.click(screen.getByRole('button', { name: 'Save & create visit' }));
  await waitFor(() => assert.equal(saved.length, 1));
  const writes = requests.filter(r => r.method !== 'GET');
  assert.equal(writes.length, 1);
  assert.equal(writes[0].method, 'PATCH');
  assert.equal(writes[0].path, '/api/patients/42');
  assert.equal(writes[0].body.version, 7);
  assert.equal(writes[0].body.first_name, 'Ananya Patil');
  assert.equal(writes[0].body.middle_name, '');
  assert.equal(writes[0].body.surname, '');
  assert.equal(writes[0].body.address, 'Updated fictional address');
  assert.equal(saved[0][0].uhid, existing.uhid);
  assert.equal(saved[0][1], true);
});

test('keyboard selection works and clearing the selected record returns to new registration', async () => {
  render(<PatientForm ctx={ctx} close={() => {}} saved={() => {}} />);
  const user = userEvent.setup({ document: dom.window.document });
  const name = screen.getByRole('combobox', { name: /^Name\s*\*$/ });
  await user.type(name, 'Ananya');
  await screen.findByRole('option', { name: /Ananya Patil.*AB12CD34/ });
  await user.keyboard('{ArrowDown}{Enter}');
  assert.ok(screen.getByText('Existing patient selected'));
  await user.click(screen.getByRole('button', { name: 'Choose another / new patient' }));
  assert.equal((screen.getByPlaceholderText('Patient full name') as HTMLInputElement).value, '');
  assert.equal((screen.getByPlaceholderText('House / street / locality') as HTMLTextAreaElement).value, '');
  assert.ok(screen.getByRole('button', { name: 'Save patient' }));
  assert.equal(screen.queryByText('Existing patient selected'), null);
});

test('typing a surname fragment in Name shows existing patients', async () => {
  render(<PatientForm ctx={ctx} close={() => {}} saved={() => {}} />);
  const user = userEvent.setup({ document: dom.window.document });
  await user.type(screen.getByPlaceholderText('Patient full name'), 'Pat');
  assert.ok(await screen.findByRole('option', { name: /Ananya Patil.*AB12CD34/ }));
  assert.ok(requests.some(r => r.path.includes('q=Pat')));
});

test('suggestions stay visible when staff move from Name to another field', async () => {
  render(<PatientForm ctx={ctx} close={() => {}} saved={() => {}} />);
  const user = userEvent.setup({ document: dom.window.document });
  await user.type(screen.getByRole('combobox', { name: /^Name\s*\*$/ }), 'Ananya');
  await screen.findByRole('option', { name: /Ananya Patil.*AB12CD34/ });
  await user.click(screen.getByPlaceholderText('Age'));
  assert.ok(screen.getByRole('option', { name: /Ananya Patil.*AB12CD34/ }));
});

const queueVisit = { id: 17, patient_name: 'Fictional Patient', status: 'Waiting', version: 4 };
const statusCtx = { ...ctx, changed: () => {}, notify: () => {} } as AppContext;

test('main-page status completes a visit directly without opening a dialog', async () => {
  globalThis.fetch = async (input, init) => {
    requests.push({ path: String(input), method: init!.method!, body: JSON.parse(String(init!.body)) });
    return Response.json({ ...queueVisit, status: 'Completed', version: 5 });
  };
  render(<InlineVisitStatus visit={queueVisit} ctx={statusCtx} />);
  const user = userEvent.setup({ document: dom.window.document });
  await user.selectOptions(screen.getByRole('combobox'), 'Completed');
  await waitFor(() => assert.equal((screen.getByRole('combobox') as HTMLSelectElement).value, 'Completed'));
  assert.deepEqual(requests[0], { path: '/api/visits/17', method: 'PATCH', body: { version: 4, status: 'Completed', reason: '' } });
  assert.equal(screen.queryByRole('dialog'), null);
});

test('main-page cancellation collects its required reason inline before saving', async () => {
  globalThis.fetch = async (input, init) => {
    requests.push({ path: String(input), method: init!.method!, body: JSON.parse(String(init!.body)) });
    return Response.json({ ...queueVisit, status: 'Cancelled', version: 5 });
  };
  render(<InlineVisitStatus visit={queueVisit} ctx={statusCtx} />);
  const user = userEvent.setup({ document: dom.window.document });
  await user.selectOptions(screen.getByRole('combobox'), 'Cancelled');
  assert.equal(requests.length, 0);
  assert.equal((screen.getByRole('button', { name: 'Save status' }) as HTMLButtonElement).disabled, true);
  await user.type(screen.getByLabelText('Cancellation reason'), 'Patient request');
  await user.click(screen.getByRole('button', { name: 'Save status' }));
  await waitFor(() => assert.equal(requests.length, 1));
  assert.equal(requests[0].body.reason, 'Patient request');
  assert.equal(requests[0].body.status, 'Cancelled');
  assert.equal(screen.queryByRole('dialog'), null);
});

test('a stale main-page status update shows the conflict and keeps the saved status', async () => {
  globalThis.fetch = async () => Response.json({ detail: 'Another staff member changed this record. Refresh before editing.' }, { status: 409 });
  render(<InlineVisitStatus visit={queueVisit} ctx={statusCtx} />);
  const user = userEvent.setup({ document: dom.window.document });
  await user.selectOptions(screen.getByRole('combobox'), 'Completed');
  assert.ok(await screen.findByRole('alert'));
  assert.equal((screen.getByRole('combobox') as HTMLSelectElement).value, 'Waiting');
});

test('queue actions keep edit and follow-up attached to the correct patient and visit', async () => {
  const edits: number[] = [], followups: any[][] = [];
  const visit = { ...queueVisit, patient_id: 42, patient_name: existing.name, uhid: existing.uhid, phone: existing.phone };
  const actionCtx = { ...statusCtx, openVisit: (id: number) => edits.push(id), newFollowup: (...args: any[]) => followups.push(args) };
  render(<VisitActions visit={visit} ctx={actionCtx} />);
  const user = userEvent.setup({ document: dom.window.document });
  assert.equal(screen.queryByRole('button', { name: /Manage/ }), null);
  await user.click(screen.getByRole('button', { name: `Edit visit for ${existing.name}` }));
  await user.click(screen.getByRole('button', { name: `Add follow-up for ${existing.name}` }));
  assert.deepEqual(edits, [17]);
  assert.equal(followups[0][0].id, 42);
  assert.equal(followups[0][0].uhid, existing.uhid);
  assert.equal(followups[0][1].id, 17);
});

test('a saved follow-up changes the row action and opens the existing record', async () => {
  const opened: number[] = [];
  const actionCtx = { ...statusCtx, openFollowup: (id: number) => opened.push(id),
    newFollowup: () => assert.fail('Must open the saved follow-up') };
  const { rerender } = render(<VisitActions visit={queueVisit} ctx={actionCtx} />);
  assert.ok(screen.getByRole('button', { name: 'Add follow-up for Fictional Patient' }));
  rerender(<VisitActions visit={{ ...queueVisit, followup_id: 91 }} ctx={actionCtx} />);
  const button = screen.getByRole('button', { name: 'View follow-up for Fictional Patient' });
  assert.equal(button.textContent, 'Follow-up set');
  assert.ok(button.classList.contains('followup-set'));
  const user = userEvent.setup({ document: dom.window.document });
  await user.click(button);
  assert.deepEqual(opened, [91]);
});

test('follow-up popup defaults to seven days and allows a quick date edit before saving', async () => {
  const visit = { ...queueVisit, patient_id: 42, doctor_id: 11, department_id: 21, visit_date: '2026-10-28' };
  const followCtx = { ...statusCtx, catalog: { ...ctx.catalog,
    departments: [{ id: 21, name: 'Test department', active: true }],
    doctors: [{ id: 11, name: 'Dr Test', department_id: 21, active: true }], staff: [],
    settings: { timezone: 'Asia/Kolkata', reminder_time: '10:15' },
  } };
  let saved = 0;
  globalThis.fetch = async (input, init) => {
    if ((init?.method || 'GET') === 'GET') return Response.json({ items: [], total: 0 });
    requests.push({ path: String(input), method: init!.method!, body: JSON.parse(String(init!.body)) });
    return Response.json({ id: 9 });
  };
  render(<FollowupForm patient={existing} visit={visit} ctx={followCtx} close={() => {}} saved={() => saved++} />);
  const date = screen.getByLabelText(/Follow-up date/);
  const reminder = screen.getByLabelText(/^Daily notification/);
  assert.equal((date as HTMLInputElement).value, '2026-11-04');
  assert.equal((reminder as HTMLInputElement).value, '9:00 AM daily');
  fireEvent.input(date, { target: { value: '2026-11-06' } });
  assert.equal((reminder as HTMLInputElement).value, '9:00 AM daily');
  const user = userEvent.setup({ document: dom.window.document });
  await user.click(screen.getByRole('button', { name: 'Schedule follow-up' }));
  await waitFor(() => assert.equal(saved, 1));
  assert.equal(requests[0].body.patient_id, 42);
  assert.equal(requests[0].body.origin_visit_id, 17);
  assert.equal(requests[0].body.doctor_id, 11);
  assert.equal(requests[0].body.due_date, '2026-11-06');
});

test('OPD follow-ups panel defaults to today and filters by the selected date', async () => {
  const opened: number[] = [];
  let closed = 0;
  globalThis.fetch = async (input) => {
    const path = String(input);
    requests.push({ path, method: 'GET', body: null });
    const selected = new URL(path, 'http://localhost').searchParams.get('due_date');
    return Response.json({ items: selected === '2026-10-23' ? [{ id: 91, patient_name: 'Fictional Return', uhid: 'TEST1234', doctor_name: 'Dr Test', department_name: 'General', status: 'Scheduled' }] : [], total: selected === '2026-10-23' ? 1 : 0, page: 1 });
  };
  render(<FollowupsPanel ctx={{ ...statusCtx, openFollowup: id => opened.push(id) }} close={() => closed++} />);
  assert.equal((screen.getByLabelText('Follow-up date') as HTMLInputElement).value, '2026-10-23');
  assert.ok(await screen.findByText('Fictional Return'));
  assert.ok(requests[0].path.includes('due_date=2026-10-23'));
  fireEvent.input(screen.getByLabelText('Follow-up date'), { target: { value: '2026-10-25' } });
  assert.ok(await screen.findByText('No follow-ups for this date'));
  assert.equal(screen.queryByText('Fictional Return'), null);
  const user = userEvent.setup({ document: dom.window.document });
  await user.click(screen.getByRole('button', { name: /^Today$/ }));
  await user.click(await screen.findByRole('button', { name: /Fictional Return/ }));
  assert.deepEqual(opened, [91]);
  assert.equal(closed, 1);
});

test('OPD starts with separate doctor queues and opens only the selected doctor and status', async () => {
  const queueCtx = { ...statusCtx, user: {role:'Master'}, catalog: { ...ctx.catalog,
    departments:[{id:21,name:'General',active:true}],
    doctors:[{id:11,name:'Dr First',department_id:21,active:true},{id:12,name:'Dr Second',department_id:21,active:true}],
  }, openFollowups:()=>{} };
  globalThis.fetch = async (input) => {
    const path=String(input), url=new URL(path,'http://localhost');
    requests.push({path,method:'GET',body:null});
    if(url.pathname==='/api/queues') return Response.json({day:url.searchParams.get('day'), total_visits:3, items:[
      {id:11,name:'Dr First',active:true,department_name:'General',total:2,counts:{Waiting:2,'Being Attended':0,Completed:0,Cancelled:0},waiting:[{id:1,token:1,patient_name:'First Patient',uhid:'TEST0001'}],attending:[]},
      {id:12,name:'Dr Second',active:true,department_name:'General',total:1,counts:{Waiting:1,'Being Attended':0,Completed:0,Cancelled:0},waiting:[{id:2,token:1,patient_name:'Second Patient',uhid:'TEST0002'}],attending:[]},
    ]});
    return Response.json({items:[],total:0,page:1});
  };
  render(<Queue ctx={queueCtx}/>);
  assert.ok(await screen.findByRole('heading',{name:'Dr First'}));
  assert.ok(screen.getByRole('heading',{name:'Dr Second'}));
  assert.ok(screen.getByText('First Patient'));
  assert.ok(screen.getByText('Second Patient'));
  assert.equal(requests.some(r=>r.path.startsWith('/api/visits?')),false);
  const user=userEvent.setup({document:dom.window.document});
  await user.click(screen.getByRole('button',{name:'Open queue for Dr First'}));
  await user.click(screen.getByRole('button',{name:/^Being Attended$/}));
  assert.ok(await screen.findByText('No being attended patients'));
  const request=requests.find(r=>r.path.startsWith('/api/visits?')&&new URL(r.path,'http://localhost').searchParams.get('status')==='Being Attended')!;
  const params=new URL(request.path,'http://localhost').searchParams;
  assert.equal(params.get('doctor_id'),'11');
  assert.equal(params.get('status'),'Being Attended');
  await user.click(screen.getByRole('button',{name:/Doctor queues/}));
  assert.ok(await screen.findByText('Second Patient'));
  fireEvent.input(screen.getByLabelText('Visit date'),{target:{value:'2026-10-25'}});
  await waitFor(()=>assert.ok(requests.some(r=>r.path.startsWith('/api/queues?')&&r.path.includes('day=2026-10-25'))));
});

test('doctor card starts attendance and completes attended visits directly', async () => {
  globalThis.fetch=async(input,init)=>{
    const body=JSON.parse(String(init?.body));
    requests.push({path:String(input),method:init!.method!,body});
    return Response.json({...queueVisit,status:body.status,version:body.version+1});
  };
  const {rerender}=render(<DoctorQueuePatient visit={queueVisit} ctx={statusCtx}/>);
  const user=userEvent.setup({document:dom.window.document});
  await user.click(screen.getByRole('button',{name:'Attend Fictional Patient'}));
  assert.ok(await screen.findByText('Marked being attended'));
  assert.deepEqual(requests[0].body,{version:4,status:'Being Attended',reason:''});
  rerender(<DoctorQueuePatient visit={{...queueVisit,status:'Being Attended',version:5}} ctx={statusCtx}/>);
  await user.click(screen.getByRole('button',{name:'Complete visit for Fictional Patient'}));
  await waitFor(()=>assert.equal(requests.length,2));
  assert.deepEqual(requests[1].body,{version:5,status:'Completed',reason:''});
});

test('doctor card requires a cancellation reason and restores the same cancelled visit to waiting', async () => {
  globalThis.fetch=async(input,init)=>{
    const body=JSON.parse(String(init?.body));
    requests.push({path:String(input),method:init!.method!,body});
    return Response.json({...queueVisit,status:body.status,version:body.version+1});
  };
  const {rerender}=render(<DoctorQueuePatient visit={{...queueVisit,status:'Being Attended'}} ctx={statusCtx}/>);
  const user=userEvent.setup({document:dom.window.document});
  await user.click(screen.getByRole('button',{name:'Cancel visit for Fictional Patient'}));
  assert.equal(requests.length,0);
  assert.equal((screen.getByRole('button',{name:'Confirm cancellation'}) as HTMLButtonElement).disabled,true);
  await user.type(screen.getByLabelText('Cancellation reason'),'Patient request');
  await user.click(screen.getByRole('button',{name:'Confirm cancellation'}));
  assert.ok(await screen.findByText('Marked cancelled'));
  assert.deepEqual(requests[0].body,{version:4,status:'Cancelled',reason:'Patient request'});
  rerender(<DoctorQueuePatient visit={{...queueVisit,status:'Cancelled',version:5}} ctx={statusCtx}/>);
  await user.click(screen.getByRole('button',{name:'Return Fictional Patient to waiting'}));
  assert.ok(await screen.findByText('Marked waiting'));
  assert.deepEqual(requests[1],{path:'/api/visits/17',method:'PATCH',body:{version:5,status:'Waiting',reason:'Returned to waiting queue'}});
});

test('doctor card preserves the saved state and reports stale updates', async () => {
  let refreshed=0;
  globalThis.fetch=async()=>Response.json({detail:'Another staff member changed this record.'},{status:409});
  render(<DoctorQueuePatient visit={queueVisit} ctx={{...statusCtx,changed:()=>refreshed++}}/>);
  const user=userEvent.setup({document:dom.window.document});
  await user.click(screen.getByRole('button',{name:'Attend Fictional Patient'}));
  assert.ok(await screen.findByRole('alert'));
  assert.equal(refreshed,1);
  assert.ok(screen.getByRole('button',{name:'Attend Fictional Patient'}));
});

test('Complete view toggles from doctor overview to the full filtered OPD list and back', async () => {
  const toggleCtx={...statusCtx,user:{role:'Master'},catalog:{...ctx.catalog,departments:[{id:21,name:'General',active:true}],doctors:[{id:11,name:'Dr First',department_id:21,active:true}]},openFollowups:()=>{}};
  globalThis.fetch=async(input)=>{
    const path=String(input);requests.push({path,method:'GET',body:null});
    if(path.startsWith('/api/queues?'))return Response.json({day:'2026-10-23',total_visits:1,items:[{id:11,name:'Dr First',active:true,total:1,counts:{Waiting:1,'Being Attended':0},attending:[],waiting:[{...queueVisit,patient_name:'Queue Patient',token:1}]}]});
    return Response.json({items:[{...queueVisit,patient_id:42,token:1,uhid:'TEST1234',patient_name:'List Patient',doctor_name:'Dr First',department_name:'General',arrival_at:'2026-10-23T04:00:00Z',visit_type:'New'}],total:1,page:1});
  };
  render(<Queue ctx={toggleCtx}/>);
  const toggle=screen.getByRole('switch',{name:'Complete view'});
  assert.equal((toggle as HTMLInputElement).checked,false);
  assert.ok(await screen.findByText('Queue Patient'));
  const user=userEvent.setup({document:dom.window.document});
  await user.click(toggle);
  assert.ok(await screen.findByText('List Patient'));
  assert.ok(screen.getByRole('table'));
  assert.equal((toggle as HTMLInputElement).checked,true);
  const request=requests.find(r=>r.path.startsWith('/api/visits?'))!;
  assert.equal(new URL(request.path,'http://localhost').searchParams.get('doctor_id'),'0');
  assert.equal(new URL(request.path,'http://localhost').searchParams.get('day'),'2026-10-23');
  await user.click(screen.getByRole('button',{name:/^Completed$/}));
  await waitFor(()=>assert.ok(requests.some(r=>r.path.includes('status=Completed'))));
  await user.click(toggle);
  assert.ok(await screen.findByText('Queue Patient'));
  assert.equal(screen.queryByRole('table'),null);
});


test('money input converts decimal currency exactly and rejects invalid precision', () => {
  assert.equal(toPaise('125.55'),12555);
  assert.equal(toPaise('0'),0);
  for (const value of ['-1','1.001','1e3','NaN','']) assert.equal(toPaise(value),null);
});

test('bill draft submits additional charges in integer paise', async () => {
  const user=userEvent.setup({document:dom.window.document});
  globalThis.fetch=async(input,init)=>{requests.push({path:String(input),method:init?.method||'GET',body:JSON.parse(String(init?.body))});return Response.json({id:9});};
  render(<BillDraft quote={{visit:{id:4,version:2,patient_name:'Asha',uhid:'AB12CD34',doctor_name:'Dr Test',visit_type:'New'},doctor_version:3,consultation_fee_paise:50000}} ctx={{...ctx,notify:()=>{}}} saved={()=>{}}/>);
  await user.click(screen.getByRole('button',{name:'Add charge'}));
  await user.type(screen.getByLabelText(/Charge 1/),'Dressing');
  await user.clear(screen.getByLabelText(/Quantity 1/));await user.type(screen.getByLabelText(/Quantity 1/),'2');
  await user.type(screen.getByLabelText(/Unit price 1/),'12.55');
  await user.click(screen.getByRole('button',{name:'Generate bill'}));
  await waitFor(()=>assert.equal(requests.length,1));
  assert.deepEqual(requests[0].body.extras,[{description:'Dressing',quantity:2,unit_price_paise:1255}]);
  assert.equal(requests[0].body.doctor_version,3);
});

test('unset consultation fee blocks bill generation',()=>{
  render(<BillDraft quote={{visit:{id:4,patient_name:'Asha',visit_type:'Follow-up'},consultation_fee_paise:null}} ctx={ctx} saved={()=>{}}/>);
  assert.equal((screen.getByRole('button',{name:'Generate bill'}) as HTMLButtonElement).disabled,true);
  assert.match(screen.getByText(/Master must set/).textContent||'',/follow-up/);
});

test('partial payment submits exact amount and blocks overpayment',async()=>{
  const user=userEvent.setup({document:dom.window.document});
  globalThis.fetch=async(input,init)=>{requests.push({path:String(input),method:init?.method||'GET',body:JSON.parse(String(init?.body))});return Response.json({id:9});};
  render(<PaymentForm bill={{id:9,version:2,balance_paise:30000}} ctx={{...ctx,notify:()=>{}}} saved={()=>{}}/>);
  const amount=screen.getByLabelText(/Payment amount/);
  await user.clear(amount);await user.type(amount,'301');
  assert.equal((screen.getByRole('button',{name:'Record payment'}) as HTMLButtonElement).disabled,true);
  await user.clear(amount);await user.type(amount,'125.55');
  await user.selectOptions(screen.getByLabelText('Payment method'),'UPI');
  await user.click(screen.getByRole('button',{name:'Record payment'}));
  await waitFor(()=>assert.equal(requests.length,1));
  assert.deepEqual(requests[0].body,{version:2,amount_paise:12555,method:'UPI',reference:''});
});


test('saved charge selection fills its price and submits catalog identity',async()=>{
 const user=userEvent.setup({document:dom.window.document});
 globalThis.fetch=async(input,init)=>{requests.push({path:String(input),method:init?.method||'GET',body:JSON.parse(String(init?.body))});return Response.json({id:9});};
 render(<BillDraft quote={{visit:{id:4,version:2,patient_name:'Asha',visit_type:'New'},doctor_version:3,consultation_fee_paise:50000}} ctx={{...ctx,catalog:{...ctx.catalog,billing_charges:[{id:7,name:'Dressing',price_paise:12550,version:2,active:1},{id:8,name:'Inactive charge',price_paise:100,version:1,active:0}]},notify:()=>{}}} saved={()=>{}}/>);
 assert.equal(screen.queryByRole('option',{name:/Inactive charge/}),null);
 await user.selectOptions(screen.getByLabelText('Saved billing charge'),'7');
 assert.equal((screen.getByLabelText(/Charge 1/) as HTMLInputElement).value,'Dressing');
 assert.equal((screen.getByLabelText(/Unit price 1/) as HTMLInputElement).value,'125.50');
 assert.equal((screen.getByLabelText(/Unit price 1/) as HTMLInputElement).readOnly,true);
 await user.click(screen.getByRole('button',{name:'Generate bill'}));
 await waitFor(()=>assert.equal(requests.length,1));
 assert.deepEqual(requests[0].body.extras,[{description:'Dressing',quantity:1,unit_price_paise:12550,charge_id:7,charge_version:2}]);
});


test('Billing defaults to completed visits and opens generation or existing bill per row',async()=>{
 const user=userEvent.setup({document:dom.window.document});let generated=0,opened=0;
 globalThis.fetch=async(input,init)=>{requests.push({path:String(input),method:init?.method||'GET',body:null});if(String(input).startsWith('/api/bills?'))return Response.json({items:[],total:0,page:1});return Response.json({items:[{id:4,patient_name:'Asha',uhid:'AB12CD34',doctor_name:'Dr Test',visit_date:'2026-10-25',visit_type:'New',bill_id:null},{id:5,patient_name:'Ananya',uhid:'CD12AB34',doctor_name:'Dr Test',visit_date:'2026-10-25',visit_type:'Follow-up',bill_id:9}],total:2,page:1});};
 render(<Billing ctx={{...ctx,openBilling:id=>{generated=id;},openBill:id=>{opened=id;}}}/>);
 await user.click(await screen.findByRole('button',{name:'Generate bill for Asha'}));
 assert.equal(generated,4);
 await user.click(screen.getByRole('button',{name:'View bill for Ananya'}));assert.equal(opened,9);
 assert.match(requests[0].path,/billing-visits/);
 assert.match(requests[0].path,/start=2026-10-23/);
 assert.match(requests[0].path,/end=2026-10-23/);
 assert.equal(document.querySelectorAll('input[type="date"]').length,1);
 fireEvent.input(screen.getByLabelText('Visit date'),{target:{value:'2026-10-24'}});
 await waitFor(()=>assert.ok(requests.some(r=>r.path.includes('start=2026-10-24')&&r.path.includes('end=2026-10-24'))));
 await user.click(screen.getByRole('button',{name:'Bills & payments'}));
 await waitFor(()=>assert.ok(requests.some(r=>r.path.startsWith('/api/bills?'))));
});


test('editing a bill loads existing charges and saves a versioned correction',async()=>{
 const user=userEvent.setup({document:dom.window.document});
 globalThis.fetch=async(input,init)=>{requests.push({path:String(input),method:init?.method||'GET',body:JSON.parse(String(init?.body))});return Response.json({id:9});};
 render(<BillDraft bill={{id:9,version:3,paid_paise:60000,note:'Original',lines:[{kind:'Additional charge',description:'Dressing',quantity:2,unit_price_paise:10000}]}} quote={{visit:{id:4,patient_name:'Asha',visit_type:'New'},consultation_fee_paise:50000}} ctx={{...ctx,notify:()=>{}}} saved={()=>{}}/>);
 await user.click(screen.getByRole('button',{name:'Remove charge 1'}));
 assert.equal((screen.getByRole('button',{name:'Save bill changes'}) as HTMLButtonElement).disabled,true);
 await user.click(screen.getByRole('button',{name:'Add charge'}));
 await user.type(screen.getByLabelText(/Charge 1/),'Materials');
 await user.type(screen.getByLabelText(/Unit price 1/),'200');
 await user.click(screen.getByRole('button',{name:'Save bill changes'}));
 await waitFor(()=>assert.equal(requests.length,1));
 assert.equal(requests[0].method,'PATCH');assert.equal(requests[0].path,'/api/bills/9');assert.equal(requests[0].body.version,3);
 assert.deepEqual(requests[0].body.extras,[{description:'Materials',quantity:1,unit_price_paise:20000}]);
});


test('OPD header offers registration and visit creation directly',async()=>{
 const user=userEvent.setup({document:dom.window.document});let registered=0,visits=0;
 globalThis.fetch=async()=>Response.json({doctors:[],totals:{waiting:0,attending:0,available:0},total_visits:0});
 render(<Queue ctx={{...ctx,user:{role:'Master'},catalog:{...ctx.catalog,doctors:[],departments:[]},newVisit:()=>{visits++;}}} register={()=>{registered++;}}/>);
 await user.click(screen.getByRole('button',{name:'Register patient'}));
 await user.click(screen.getByRole('button',{name:'Create OPD visit'}));
 assert.equal(registered,1);assert.equal(visits,1);
});


test('Dashboard combines analytics and reports without reception actions',async()=>{
 globalThis.fetch=async(input)=>String(input).startsWith('/api/dashboard')?Response.json({date:'2026-10-26',statuses:{Waiting:2,Completed:3},total_visits:5,followups_today:1,overdue:0,trend:[{date:'2026-10-26',visits:5}]}):Response.json({items:[],total:0,page:1});
 render(<Dashboard ctx={{...ctx,catalog:{...ctx.catalog,doctors:[],departments:[],staff:[],lookups:[]}}}/>);
 assert.ok(await screen.findByText('5 total this week'));
 assert.ok(screen.getByRole('heading',{name:'Dashboard'}));
 assert.ok(screen.getByRole('heading',{name:'Reports'}));
 assert.ok(screen.getByRole('button',{name:'OPD visit register'}));
 assert.equal(screen.queryByRole('button',{name:'Register patient'}),null);
 assert.equal(screen.queryByRole('button',{name:'Create visit'}),null);
});


test('doctor availability popup disables and enables through versioned actions',async()=>{
 const user=userEvent.setup({document:dom.window.document});let disabled=false,version=1;
 globalThis.fetch=async(input,init)=>{const path=String(input);if(init?.method==='PATCH'){const body=JSON.parse(String(init.body));requests.push({path,method:'PATCH',body});disabled=body.disabled;version++;return Response.json({ok:true});}return Response.json({items:[{id:11,name:'Dr Test',active:1,department_name:'General',version,disabled_until:disabled?'2026-10-27T02:30:00+00:00':null}]});};
 render(<DoctorAvailability ctx={{...ctx,refresh:0,changed:()=>{},notify:()=>{}}} close={()=>{}}/>);
 await user.click(await screen.findByRole('button',{name:'Disable for today Dr Test'}));
 await user.click(await screen.findByRole('button',{name:'Enable Dr Test'}));
 await screen.findByRole('button',{name:'Disable for today Dr Test'});
 assert.deepEqual(requests.map(r=>r.body),[{version:1,disabled:true},{version:2,disabled:false}]);
});


test('new password requirements update live and block submission until all checks and confirmation pass',async()=>{
 const user=userEvent.setup({document:dom.window.document});let saved=0;
 globalThis.fetch=async(input,init)=>{requests.push({path:String(input),method:init?.method||'GET',body:JSON.parse(String(init?.body))});return Response.json({ok:true});};
 render(<PasswordForm done={()=>{saved++;}}/>);
 const password=screen.getByLabelText(/^New password/),confirm=screen.getByLabelText(/^Confirm new password/),button=screen.getByRole('button',{name:'Update password'});
 await user.type(screen.getByLabelText(/^Current password/),'ExistingPassword');
 await user.type(password,'abcdefghijkl');
 assert.equal(document.querySelectorAll('.password-rules li[data-met="true"]').length,1);
 assert.equal((button as HTMLButtonElement).disabled,true);
 await user.type(password,'A1!');
 assert.equal(document.querySelectorAll('.password-rules li[data-met="true"]').length,4);
 assert.equal((button as HTMLButtonElement).disabled,true);
 await user.type(confirm,'abcdefghijklA1!');
 assert.equal((button as HTMLButtonElement).disabled,false);
 await user.click(button);await waitFor(()=>assert.equal(saved,1));assert.equal(requests[0].body.new_password,'abcdefghijklA1!');
});

test('department palette offers accessible pastel choices and updates selection', async () => {
  const { DepartmentColorPicker, DepartmentBadge } = await import('../app/department-colors');
  let selected = '';
  const view = render(<DepartmentColorPicker value="#DBEAFE" onChange={value=>{selected=value;}}/>);
  assert.equal(screen.getAllByRole('radio').length, 8);
  fireEvent.click(screen.getByRole('radio', {name:'Lavender'}));
  assert.equal(selected, '#EDE9FE');
  view.rerender(<DepartmentColorPicker value={selected} onChange={()=>{}}/>);
  assert.equal((screen.getByRole('radio', {name:'Lavender'}) as HTMLInputElement).checked, true);
  cleanup();
  render(<DepartmentBadge name="General medicine" color={selected}/>);
  assert.equal(screen.getByText('General medicine').style.backgroundColor, 'rgb(237, 233, 254)');
});
