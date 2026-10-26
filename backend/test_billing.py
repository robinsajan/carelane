"""Billing checks use disposable fixture databases, never hospital data."""
import concurrent.futures
import uuid

from fastapi.testclient import TestClient

from backend import main as m
from backend.test_workflows import client, post, patient, assignment, visit


def priced_setup(client, visit_type='New'):
    p=patient(client); dep,doctor=assignment(client)
    doctor=client.patch(f"/api/doctors/{doctor['id']}",json={**{k:doctor[k] for k in ('name','code','department_id','version')},'consultation_fee_paise':50000,'followup_fee_paise':30000}).json()
    v=visit(client,p,dep,doctor,visit_type=visit_type)
    completed=client.patch(f"/api/visits/{v['id']}",json={'version':v['version'],'status':'Completed'})
    completed.raise_for_status()
    return p,dep,doctor,completed.json()


def bill_body(client,v,extras=None):
    quote=client.get(f"/api/visits/{v['id']}/billing").json()
    return {'visit_id':v['id'],'visit_version':quote['visit']['version'],'doctor_version':quote['doctor_version'],'extras':extras or []}


def test_bill_requires_completed_visit_configured_fee_and_current_quote(client):
    p=patient(client); dep,dr=assignment(client); v=visit(client,p,dep,dr)
    assert post(client,'/bills',bill_body(client,v)).status_code==409
    v=client.patch(f"/api/visits/{v['id']}",json={'version':1,'status':'Completed'}).json()
    assert post(client,'/bills',bill_body(client,v)).status_code==400
    previous=bill_body(client,v)
    response=client.patch(f"/api/doctors/{dr['id']}",json={**{k:dr[k] for k in ('name','code','department_id','version')},'consultation_fee_paise':50000,'followup_fee_paise':30000})
    assert response.status_code==200,response.text
    assert post(client,'/bills',previous).status_code==409
    result=post(client,'/bills',bill_body(client,v))
    assert result.status_code==200,result.text


def test_bill_exact_amounts_idempotency_duplicate_guard_and_immutable_snapshot(client):
    p,dep,dr,v=priced_setup(client)
    body=bill_body(client,v,[{'description':'Dressing','quantity':2,'unit_price_paise':12550},{'description':'Material','quantity':1,'unit_price_paise':995}])
    key=str(uuid.uuid4())
    result=post(client,'/bills',body,key)
    assert result.status_code==200,result.text
    bill=result.json()
    assert bill['total_paise']==76095 and bill['balance_paise']==76095
    assert bill['payment_status']=='Unpaid' and len(bill['lines'])==3
    assert bill['number'].startswith('OPD-')
    assert post(client,'/bills',body,key).json()['id']==bill['id']
    assert post(client,'/bills',body).status_code==409
    assert client.get('/api/visits').json()['items'][0]['bill_id']==bill['id']
    # A later fee edit cannot rewrite an issued bill.
    response=client.patch(f"/api/doctors/{dr['id']}",json={'name':'Renamed Doctor','code':dr['code'],'department_id':dep['id'],'version':dr['version'],'consultation_fee_paise':99900})
    assert response.status_code==200,response.text
    assert response.json()['followup_fee_paise']==30000
    saved=client.get(f"/api/bills/{bill['id']}").json()
    assert saved['total_paise']==76095 and saved['snapshot']['doctor_name']=='Dr Test'
    assert client.patch(f"/api/visits/{v['id']}",json={'version':v['version'],'status':'Cancelled','reason':'Patient request'}).status_code==409
    with m.connect() as db:
        assert db.execute('SELECT count(*) FROM bills').fetchone()[0]==1


def test_followup_pricing_zero_fee_and_reject_invalid_money(client):
    p,dep,dr,v=priced_setup(client,'Follow-up')
    assert post(client,'/bills',bill_body(client,v)).json()['total_paise']==30000
    assert client.patch(f"/api/doctors/{dr['id']}",json={'name':dr['name'],'code':dr['code'],'department_id':dep['id'],'version':dr['version'],'consultation_fee_paise':-1}).status_code==422
    other=visit(client,p,dep,dr,duplicate_ack=True)
    other=client.patch(f"/api/visits/{other['id']}",json={'version':1,'status':'Completed'}).json()
    body=bill_body(client,other)
    for amount in [-1,0,12.5,True]:
        assert post(client,'/bills',{**body,'extras':[{'description':'Extra','quantity':1,'unit_price_paise':amount}]}).status_code==422
    response=client.patch(f"/api/doctors/{dr['id']}",json={'name':dr['name'],'code':dr['code'],'department_id':dep['id'],'version':dr['version'],'consultation_fee_paise':0})
    assert response.status_code==200,response.text
    free=post(client,'/bills',bill_body(client,other)).json()
    assert free['total_paise']==0 and free['payment_status']=='Paid'


def test_partial_full_payments_and_replays_never_overpay(client):
    p,dep,dr,v=priced_setup(client)
    bill=post(client,'/bills',bill_body(client,v)).json()
    payment={'version':1,'amount_paise':20000,'method':'Cash','reference':'Counter'}
    key=str(uuid.uuid4())
    result=post(client,f"/bills/{bill['id']}/payments",payment,key)
    assert result.status_code==200,result.text
    partial=result.json()
    assert partial['paid_paise']==20000 and partial['balance_paise']==30000 and partial['payment_status']=='Part paid'
    assert len(post(client,f"/bills/{bill['id']}/payments",payment,key).json()['payments'])==1
    assert post(client,f"/bills/{bill['id']}/payments",{**payment,'version':2,'amount_paise':30001}).status_code==409
    assert post(client,f"/bills/{bill['id']}/payments",payment).status_code==409
    paid=post(client,f"/bills/{bill['id']}/payments",{'version':2,'amount_paise':30000,'method':'UPI','reference':'TX-TEST'}).json()
    assert paid['balance_paise']==0 and paid['payment_status']=='Paid' and len(paid['payments'])==2
    assert sum(row['amount_paise'] for row in paid['payments'])==paid['total_paise']
    assert post(client,f"/bills/{bill['id']}/payments",{'version':3,'amount_paise':1,'method':'Cash'}).status_code==409
    assert client.get('/api/bills',params={'status':'Paid','q':p['uhid']}).json()['total']==1
    assert client.get('/api/bills',params={'status':'Unpaid'}).json()['total']==0


def test_concurrent_bill_generation_and_payments_are_serialized(client):
    p,dep,dr,v=priced_setup(client)
    body=bill_body(client,v)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:post(client,'/bills',body),range(2)))
    assert sorted(response.status_code for response in results)==[200,409]
    bill=next(response.json() for response in results if response.status_code==200)
    payment={'version':1,'amount_paise':40000,'method':'Cash'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:post(client,f"/bills/{bill['id']}/payments",payment),range(2)))
    assert sorted(response.status_code for response in results)==[200,409]
    saved=client.get(f"/api/bills/{bill['id']}").json()
    assert saved['paid_paise']==40000 and saved['balance_paise']==10000


def test_admin_can_bill_and_record_payment_but_cannot_set_fees(client):
    p,dep,dr,v=priced_setup(client)
    post(client,'/staff',{'name':'Reception','username':'billingadmin','password':'Temporary!123456'})
    with TestClient(m.app,headers={'X-OPD-Request':'1'}) as other:
        other.post('/api/auth/login',json={'username':'billingadmin','password':'Temporary!123456'}).raise_for_status()
        other.post('/api/auth/password',json={'current_password':'Temporary!123456','new_password':'ChangedPassword!123456'}).raise_for_status()
        assert post(other,'/billing-charges',{'name':'Not allowed','price_paise':100}).status_code==403
        assert other.patch(f"/api/doctors/{dr['id']}",json={**{k:dr[k] for k in ('name','code','department_id','version')},'consultation_fee_paise':1}).status_code==403
        response=post(other,'/bills',bill_body(other,v))
        assert response.status_code==200,response.text
        bill=response.json()
        assert post(other,f"/bills/{bill['id']}/payments",{'version':1,'amount_paise':50000,'method':'Card'}).status_code==200
        other.post('/api/auth/logout').raise_for_status()
        assert other.get(f"/api/bills/{bill['id']}").status_code==401
    m.init_db()
    assert client.get(f"/api/bills/{bill['id']}").json()['balance_paise']==0


def test_master_charge_catalog_prices_versions_and_snapshots(client):
    p,dep,dr,v=priced_setup(client)
    charge=post(client,'/billing-charges',{'name':'Dressing','price_paise':12550}).json()
    assert charge['price_paise']==12550
    assert client.get('/api/catalog').json()['billing_charges'][0]['id']==charge['id']
    extra={'description':charge['name'],'quantity':2,'unit_price_paise':12550,'charge_id':charge['id'],'charge_version':charge['version']}
    assert post(client,'/bills',bill_body(client,v,[{**extra,'unit_price_paise':1}])).status_code==409
    bill=post(client,'/bills',bill_body(client,v,[extra])).json()
    assert bill['total_paise']==75100
    update={'name':'Dressing','price_paise':15000,'active':True,'version':charge['version']}
    updated=client.patch(f"/api/billing-charges/{charge['id']}",json=update)
    assert updated.status_code==200,updated.text
    assert client.patch(f"/api/billing-charges/{charge['id']}",json=update).status_code==409
    assert client.get(f"/api/bills/{bill['id']}").json()['total_paise']==75100
    other=visit(client,p,dep,dr,duplicate_ack=True)
    other=client.patch(f"/api/visits/{other['id']}",json={'version':1,'status':'Completed'}).json()
    assert post(client,'/bills',bill_body(client,other,[extra])).status_code==409
    charge=updated.json()
    assert client.patch(f"/api/billing-charges/{charge['id']}",json={**update,'version':charge['version'],'active':False}).status_code==200
    extra.update(charge_version=charge['version']+1,unit_price_paise=15000)
    assert post(client,'/bills',bill_body(client,other,[extra])).status_code==409
    assert post(client,'/billing-charges',{'name':'Invalid','price_paise':-1}).status_code==422


def test_billing_completed_visit_list_includes_unbilled_and_billed_only(client):
    p,dep,dr,v=priced_setup(client)
    waiting=visit(client,p,dep,dr,duplicate_ack=True)
    result=client.get('/api/billing-visits').json()
    assert result['total']==1 and result['items'][0]['id']==v['id']
    assert result['items'][0]['bill_id'] is None
    bill=post(client,'/bills',bill_body(client,v)).json()
    assert client.get('/api/billing-visits').json()['items'][0]['bill_id']==bill['id']
    assert client.get('/api/billing-visits',params={'q':p['uhid']}).json()['total']==1
    assert client.get('/api/billing-visits',params={'end':'2000-01-01'}).json()['total']==0
    assert client.get('/api/billing-visits',params={'start':'2030-01-01','end':'2000-01-01'}).status_code==400


def test_edit_bill_preserves_identity_payments_and_rejects_stale_or_underpaid_total(client):
    p,dep,dr,v=priced_setup(client)
    bill=post(client,'/bills',bill_body(client,v)).json()
    path=f"/api/bills/{bill['id']}"
    body={'version':1,'extras':[{'description':'Dressing','quantity':2,'unit_price_paise':10000}],'note':'Corrected charges'}
    headers={'Idempotency-Key':str(uuid.uuid4())}
    response=client.patch(path,json=body,headers=headers)
    assert response.status_code==200,response.text
    edited=response.json()
    assert edited['total_paise']==70000 and edited['version']==2
    assert edited['number']==bill['number'] and edited['snapshot']==bill['snapshot']
    assert client.patch(path,json=body,headers=headers).json()['version']==2
    assert client.patch(path,json=body,headers={'Idempotency-Key':str(uuid.uuid4())}).status_code==409
    paid=post(client,f"/bills/{bill['id']}/payments",{'version':2,'amount_paise':60000,'method':'Cash'}).json()
    response=client.patch(path,json={'version':paid['version'],'extras':[]},headers={'Idempotency-Key':str(uuid.uuid4())})
    assert response.status_code==409
    response=client.patch(path,json={**body,'version':paid['version'],'note':'Note correction'},headers={'Idempotency-Key':str(uuid.uuid4())})
    assert response.status_code==200,response.text
    assert response.json()['paid_paise']==60000 and response.json()['balance_paise']==10000
    with m.connect() as db:
        assert db.execute("SELECT count(*) FROM audits WHERE action='Edited bill'").fetchone()[0]==2
