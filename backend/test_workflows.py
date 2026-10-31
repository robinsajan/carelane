"""Behavior tests use disposable SQLite files or isolated PostgreSQL test schemas."""
import concurrent.futures
import os
import psycopg
from psycopg import sql
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

# Offline tests must import successfully without configured Neon credentials.
os.environ.setdefault('local_db', 'False' if os.environ.get('OPD_TEST_POSTGRES') == '1' else 'True')
from backend import main as m


@pytest.fixture
def client(tmp_path, monkeypatch):
    use_postgres = os.environ.get('OPD_TEST_POSTGRES') == '1'
    url = m.DATABASE_URL if use_postgres else ''
    if use_postgres and not url:
        pytest.fail('PostgreSQL integration testing requires DATABASE_URL.')
    schema = 'opd_test_' + uuid.uuid4().hex
    monkeypatch.setattr(m, 'DATABASE_URL', url)
    monkeypatch.setattr(m, 'SETUP_PATH', tmp_path / 'test.setup-key')
    monkeypatch.setattr(m, 'DB_PATH', tmp_path / 'test.sqlite3')
    if use_postgres:
        with psycopg.connect(url, connect_timeout=15) as db:
            db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        monkeypatch.setattr(m, 'DATABASE_SCHEMA', schema)
    try:
        with TestClient(m.app, headers={'X-OPD-Request': '1'}) as c:
            assert c.get('/api/health').json()['setup_required']
            response = c.post('/api/auth/setup', json={'username': 'master', 'password': 'TestMaster!123456', 'name': 'Test Master',
                                                       'hospital_name': 'Test Hospital', 'setup_key': m.SETUP_PATH.read_text()})
            assert response.status_code == 200, response.text
            yield c
    finally:
        if use_postgres:
            # Drop only the random schema created by this fixture, never public.
            assert schema.startswith('opd_test_') and len(schema) == 41
            with psycopg.connect(url, connect_timeout=15) as db:
                db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))



def post(client, path, body, key=None):
    return client.post('/api'+path, json=body, headers={'Idempotency-Key': key or str(uuid.uuid4())})


def patient(client, name='Asha', phone='9876543210', **kwargs):
    body = {'first_name': name, 'surname': 'Test', 'gender': 'Female', 'age_value': 30, 'phone': phone, 'address': 'Test locality', **kwargs}
    r = post(client, '/patients', body)
    assert r.status_code == 200, r.text
    return r.json()


def assignment(client):
    dep = post(client, '/departments', {'name': 'General medicine', 'code': 'GEN'}).json()
    dr = post(client, '/doctors', {'name': 'Dr Test', 'code': 'DR1', 'department_id': dep['id']}).json()
    return dep, dr


def visit(client, p, dep, dr, **kwargs):
    body = {'patient_id': p['id'], 'department_id': dep['id'], 'doctor_id': dr['id'],
            'complaints': [{'text': 'Fever', 'duration': '2 days'}], **kwargs}
    r = post(client, '/visits', body)
    assert r.status_code == 200, r.text
    return r.json()


def follow(client, p, dep, dr, **kwargs):
    today = client.get('/api/catalog').json()['today']
    body = {'patient_id': p['id'], 'department_id': dep['id'], 'doctor_id': dr['id'], 'due_date': today,
            'reminder_local': today+'T00:00', **kwargs}
    r = post(client, '/followups', body)
    assert r.status_code == 200, r.text
    return r.json(), body


def test_setup_and_csrf(client):
    assert not client.get('/api/health').json()['setup_required']
    r = client.post('/api/auth/setup', json={'username':'another','password':'TestMaster!123456','name':'Other Master','hospital_name':'Other','setup_key':m.SETUP_PATH.read_text()})
    assert r.status_code == 409
    assert client.post('/api/auth/logout', headers={'X-OPD-Request':'0'}).status_code == 403
    uid = client.get('/api/auth/me').json()['id']
    r = client.patch(f'/api/staff/{uid}', json={'name':'Master','active':False,'version':1})
    assert r.status_code == 400


def test_registration_rules_and_idempotency(client):
    body = {'first_name':'Asha','gender':'Female','age_value':30,'phone':'9876543210','address':'Test locality'}
    for field in ['age_value','address']:
        bad = body.copy();bad.pop(field)
        assert post(client,'/patients',bad).status_code == 422
    bad = {**body,'address':' '}
    assert post(client,'/patients',bad).status_code == 422
    key = str(uuid.uuid4())
    a = post(client,'/patients',body,key)
    b = post(client,'/patients',body,key)
    assert a.json()['id'] == b.json()['id']
    assert len(a.json()['uhid']) == 8 and a.json()['uhid'].isalnum()
    assert post(client,'/patients',{**body,'first_name':'Changed'},key).status_code == 409
    assert post(client,'/patients',{**body,'first_name':'Family member'}).status_code == 200
    assert post(client,'/patients',{**body,'first_name':'Family member','duplicate_ack':True}).status_code == 200
    assert post(client,'/patients',{**body,'first_name':'NoPhone','phone':'','no_mobile':True}).status_code == 200
    future = (datetime.now()+timedelta(days=2)).date().isoformat()
    assert post(client,'/patients',{**body,'dob':future}).status_code == 422


def test_registration_accepts_date_of_birth_or_age(client):
    body = {'first_name': 'BirthDateOnly', 'gender': 'Female', 'no_mobile': True, 'address': 'Test locality'}
    assert post(client, '/patients', body).status_code == 422
    assert post(client, '/patients', {**body, 'age_value': None}).status_code == 422
    birth = datetime.now().date().isoformat()
    result = post(client, '/patients', {**body, 'dob': birth})
    assert result.status_code == 200
    assert result.json()['dob'] == birth
    assert result.json()['age_value'] == 0
    assert result.json()['age_unit'] == 'Days'
    assert post(client, '/patients', {**body, 'first_name': 'AgeOnly', 'age_value': 0}).status_code == 200


def test_patient_update_conflict_and_search(client):
    p = patient(client)
    body = {k:p[k] for k in ['first_name','middle_name','surname','gender','age_value','age_unit','dob','approximate','phone','no_mobile','address','data','active','version']}
    body['address']='Updated locality'
    assert client.patch(f"/api/patients/{p['id']}",json=body).status_code == 200
    assert client.patch(f"/api/patients/{p['id']}",json=body).status_code == 409
    for q in [p['uhid'],p['phone'],p['first_name']]:
        assert client.get('/api/patients',params={'q':q}).json()['total'] == 1


def test_partial_name_search_across_middle_names(client):
    p=patient(client,name='Ananya',middle_name='Ganesh',surname='Patil')
    for term in ['An Pat', 'Ananya Patil', 'pat an', '  ANANYA   PAT  ', 'Gan Pat']:
        result=client.get('/api/patients',params={'q':term})
        assert result.status_code==200
        assert result.json()['total']==1, term
        assert result.json()['items'][0]['id']==p['id']
    assert client.get('/api/patients',params={'q':'An Missing'}).json()['total']==0
    assert client.get('/api/patients',params={'q':'%'}).json()['total']==0


def test_single_name_field_preserves_legacy_matching_and_visit_display(client):
    p=patient(client,name='Ananya',middle_name='Ganesh',surname='Patil',phone='',no_mobile=True)
    duplicate=post(client,'/patients',{'first_name':'Ananya Ganesh Patil','gender':'Female','age_value':30,'no_mobile':True,'address':'Test locality'})
    assert duplicate.status_code==409
    dep,dr=assignment(client)
    v=visit(client,p,dep,dr)
    assert v['patient_name']=='Ananya Ganesh Patil'
    long_name='A'*80+' '+'B'*80
    new=patient(client,name=long_name,surname='',phone='9876543211')
    assert new['name']==long_name


def test_registration_matching_uses_only_names_not_shared_phone(client):
    original=patient(client,name='Ananya',surname='Patil')
    shared=post(client,'/patients',{'first_name':'Different Person','gender':'Male','age_value':45,'phone':original['phone'],'address':'Test locality'})
    assert shared.status_code==200
    same_name=post(client,'/patients',{'first_name':'Ananya Patil','gender':'Female','age_value':55,'phone':'9876543212','address':'Other locality'})
    assert same_name.status_code==409
    checked=post(client,'/patients/check-duplicates',{'first_name':'Different Name','gender':'Male','age_value':45,'phone':original['phone'],'address':'Test locality'})
    assert checked.json()==[]
    assert client.get('/api/patients',params={'q':original['phone'],'name_only':True}).json()['total']==0
    assert client.get('/api/patients',params={'q':original['uhid'],'name_only':True}).json()['total']==0
    assert client.get('/api/patients',params={'q':'An Pat','name_only':True}).json()['items'][0]['id']==original['id']


def test_history_visit_snapshot_and_queue(client):
    p=patient(client);dep,dr=assignment(client)
    h = post(client,f"/patients/{p['id']}/history",{'category':'Allergies','state':'Information reported','content':'Penicillin'}).json()
    v=visit(client,p,dep,dr)
    assert v['token'] == 1 and v['history_ids'] == [h['id']]
    assert post(client,f"/patients/{p['id']}/history",{'category':'Allergies','state':'None reported','previous_id':h['id']}).status_code == 200
    assert post(client,f"/patients/{p['id']}/history",{'category':'Allergies','state':'Unknown','previous_id':h['id']}).status_code == 409
    snap=client.get(f"/api/visits/{v['id']}").json()['history']
    assert snap[0]['content']=='Penicillin'
    body={'version':v['version'],'status':'Cancelled'}
    assert client.patch(f"/api/visits/{v['id']}",json=body).status_code == 400
    body['reason']='Patient request'
    cancelled=client.patch(f"/api/visits/{v['id']}",json=body)
    assert cancelled.status_code == 200
    v2=visit(client,p,dep,dr,complaints=[{'text':'Headache'}])
    assert v2['token']==2 and v2['complaints'][0]['text']=='Headache'
    assert client.patch(f"/api/visits/{v2['id']}",json={'version':1,'status':'Being Attended'}).status_code==200
    assert client.patch(f"/api/visits/{v2['id']}",json={'version':1,'status':'Completed'}).status_code==409
    report=client.get('/api/reports',params={'kind':'waiting'}).json()
    assert report['items'][0]['waiting_minutes'] is not None


def test_concurrent_tokens_and_duplicate_visit(client):
    p=patient(client);dep,dr=assignment(client)
    cookie=client.cookies.get('opd_session')
    def create(i):
        with TestClient(m.app,headers={'X-OPD-Request':'1'}) as c:
            c.cookies.set('opd_session',cookie)
            return visit(c,p,dep,dr,duplicate_ack=True)['token']
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        tokens=list(pool.map(create,range(10)))
    assert sorted(tokens)==list(range(1,11))
    assert post(client,'/visits',{'patient_id':p['id'],'doctor_id':dr['id'],'department_id':dep['id'],'complaints':[{'text':'Fever'}]}).status_code==409


def test_transfer_requires_decision_and_preserves_allocation(client):
    p=patient(client);dep,dr=assignment(client)
    other=post(client,'/doctors',{'name':'Dr Other','code':'DR2','department_id':dep['id']}).json()
    v=visit(client,p,dep,dr)
    body={'version':1,'status':'Waiting','doctor_id':other['id'],'department_id':dep['id'],'reason':'Patient request'}
    assert client.patch(f"/api/visits/{v['id']}",json=body).status_code==400
    settings=client.get('/api/catalog').json()['settings'];settings['transfer_policy']='Next token'
    assert client.patch('/api/settings',json=settings).status_code==200
    moved=client.patch(f"/api/visits/{v['id']}",json=body)
    assert moved.status_code==200 and moved.json()['doctor_id']==other['id']
    assert visit(client,p,dep,dr)['token']==2


def test_followup_reminders_contacts_and_attendance(client):
    p=patient(client);dep,dr=assignment(client)
    f,body=follow(client,p,dep,dr)
    assert len(client.get('/api/reminders').json())==1
    assert post(client,f"/reminders/{f['id']}",{'revision':1,'action':'snooze','minutes':30}).status_code==200
    assert client.get('/api/reminders').json()==[]
    updated={**body,'version':1,'reason':'Changed reminder time','reminder_local':body['due_date']+'T00:01'}
    r=client.patch(f"/api/followups/{f['id']}",json=updated)
    assert r.status_code==200,r.text
    assert len(client.get('/api/reminders').json())==1
    f=r.json()
    assert post(client,f"/followups/{f['id']}/contacts",{'version':f['version'],'outcome':'No answer','note':'Call attempt'}).status_code==200
    detail=client.get(f"/api/followups/{f['id']}").json()
    assert detail['followup']['status']=='Scheduled' and len(detail['contacts'])==1
    f=detail['followup']
    v=visit(client,p,dep,dr,visit_type='Follow-up',followup_id=f['id'],followup_version=f['version'])
    detail=client.get(f"/api/followups/{f['id']}").json()
    assert detail['followup']['status']=='Attended' and detail['followup']['attendance_visit_id']==v['id']
    assert client.get('/api/reminders').json()==[]
    assert post(client,'/visits',{'patient_id':p['id'],'department_id':dep['id'],'doctor_id':dr['id'],'visit_type':'Follow-up','complaints':[{'text':'New complaint'}],'followup_id':f['id'],'followup_version':f['version'],'duplicate_ack':True}).status_code==409


def test_visit_followup_indicator_persists_and_clears_on_cancellation(client):
    p = patient(client); dep, dr = assignment(client)
    v = visit(client, p, dep, dr)
    assert v['followup_id'] is None
    f, body = follow(client, p, dep, dr, origin_visit_id=v['id'])
    assert client.get('/api/visits').json()['items'][0]['followup_id'] == f['id']
    assert client.get('/api/dashboard').json()['queue'][0]['followup_id'] == f['id']
    assert client.get(f"/api/visits/{v['id']}").json()['visit']['followup_id'] == f['id']
    assert client.patch(f"/api/followups/{f['id']}", json={**body, 'version': f['version'],
        'reason': 'Patient request', 'status': 'Cancelled'}).status_code == 200
    assert client.get('/api/visits').json()['items'][0]['followup_id'] is None


def test_followup_selected_date_includes_all_statuses_and_excludes_other_dates(client):
    p=patient(client); dep,dr=assignment(client)
    day=client.get('/api/catalog').json()['today']
    f,body=follow(client,p,dep,dr)
    client.patch(f"/api/followups/{f['id']}",json={**body,'version':1,'reason':'Patient request','status':'Cancelled'}).raise_for_status()
    next_day=(datetime.fromisoformat(day)+timedelta(days=1)).date().isoformat()
    future,_=follow(client,p,dep,dr,due_date=next_day,reminder_local=next_day+'T09:00')
    rows=client.get('/api/followups',params={'view':'All','due_date':day}).json()
    assert rows['total']==1 and rows['items'][0]['id']==f['id']
    assert rows['items'][0]['status']=='Cancelled'
    rows=client.get('/api/followups',params={'due_date':next_day}).json()
    assert rows['total']==1 and rows['items'][0]['id']==future['id']


def test_daily_doctor_queue_counts_are_independent_and_not_paginated(client):
    p=patient(client); dep,dr=assignment(client)
    other=post(client,'/doctors',{'name':'Dr Second','code':'DR2','department_id':dep['id']}).json()
    empty=post(client,'/doctors',{'name':'Dr Empty','code':'DR3','department_id':dep['id']}).json()
    for _ in range(31):
        visit(client,p,dep,dr,duplicate_ack=True)
    for state in ['Being Attended','Completed','Cancelled']:
        v=visit(client,p,dep,dr,duplicate_ack=True)
        client.patch(f"/api/visits/{v['id']}",json={'version':1,'status':state,'reason':'Test attendance'}).raise_for_status()
    second=visit(client,p,dep,other,duplicate_ack=True)
    assert second['token']==1
    response=client.get('/api/queues').json()
    queues={q['id']:q for q in response['items']}
    assert response['total_visits']==35
    assert queues[dr['id']]['counts']['Waiting']==31
    assert queues[dr['id']]['total']==34
    assert queues[dr['id']]['counts']['Being Attended']==1
    assert queues[dr['id']]['counts']['Completed']==1
    assert queues[dr['id']]['counts']['Cancelled']==1
    assert [v['token'] for v in queues[dr['id']]['waiting']]==[1,2,3]
    assert queues[dr['id']]['attending'][0]['token']==32
    assert queues[other['id']]['waiting'][0]['token']==1
    assert queues[empty['id']]['total']==0
    tomorrow=(datetime.fromisoformat(response['day'])+timedelta(days=1)).date().isoformat()
    assert client.get('/api/queues',params={'day':tomorrow}).json()['total_visits']==0
    assert client.get('/api/queues',params={'department_id':99999}).json()['items']==[]


@pytest.mark.parametrize('initial_status', ['Waiting', 'Being Attended'])
def test_doctor_card_cancellation_and_return_keep_visit_and_token(client, initial_status):
    p=patient(client); dep,dr=assignment(client)
    v=visit(client,p,dep,dr)
    if initial_status=='Being Attended':
        v=client.patch(f"/api/visits/{v['id']}",json={'version':v['version'],'status':initial_status}).json()
    cancelled=client.patch(f"/api/visits/{v['id']}",json={'version':v['version'],'status':'Cancelled','reason':'Patient request'})
    cancelled.raise_for_status()
    row=client.get('/api/queues').json()['items'][0]
    assert row['counts']['Cancelled']==1 and row['cancelled'][0]['id']==v['id']
    assert row['waiting']==[] and row['attending']==[]
    restored=client.patch(f"/api/visits/{v['id']}",json={'version':cancelled.json()['version'],'status':'Waiting','reason':'Returned to waiting queue'})
    restored.raise_for_status()
    assert restored.json()['token']==v['token'] and restored.json()['id']==v['id']
    row=client.get('/api/queues').json()['items'][0]
    assert row['total']==1 and row['counts']['Waiting']==1 and row['counts']['Cancelled']==0
    assert row['cancelled']==[] and row['waiting'][0]['id']==v['id']
    events=client.get(f"/api/visits/{v['id']}").json()['events']
    assert events[0]['status']=='Waiting' and events[1]['status']=='Cancelled'


def test_followup_date_only_and_cancel(client):
    p=patient(client);dep,dr=assignment(client)
    day=client.get('/api/catalog').json()['today']
    f,body=follow(client,p,dep,dr)
    assert client.get('/api/followups',params={'view':'Overdue'}).json()['total']==0
    assert client.get('/api/followups',params={'view':'Due Today'}).json()['total']==1
    assert client.patch(f"/api/followups/{f['id']}",json={**body,'version':1,'reason':'Patient request','status':'Cancelled'}).status_code==200
    assert client.get('/api/reminders').json()==[]
    assert post(client,'/followups',{**body,'due_time':'08:00','reminder_local':day+'T09:00'}).status_code==400


def test_merge_preserves_history_and_alias(client):
    p=patient(client);other=patient(client,name='Other',phone='9876543211');dep,dr=assignment(client)
    v=visit(client,p,dep,dr);f,_=follow(client,p,dep,dr)
    body={'source_id':p['id'],'target_id':other['id'],'source_version':1,'target_version':1,'reason':'Confirmed duplicate record'}
    preview=post(client,'/patients/merge/preview',body)
    assert preview.json()['counts']['visits']==1
    assert post(client,'/patients/merge/confirm',body).status_code==200
    assert client.get(f"/api/patients/{p['id']}").json()['redirect_to']==other['id']
    detail=client.get(f"/api/patients/{other['id']}").json()
    assert len(detail['visits'])==1 and len(detail['followups'])==1 and p['uhid'] in detail['aliases']
    assert client.get('/api/patients',params={'q':p['uhid']}).json()['items'][0]['id']==other['id']


def test_admin_permissions_password_and_revocation(client):
    admin=post(client,'/staff',{'name':'Reception','username':'reception','password':'Temporary!123456'}).json()
    cookie=client.cookies.get('opd_session')
    with TestClient(m.app,headers={'X-OPD-Request':'1'}) as other:
        assert other.post('/api/auth/login',json={'username':'reception','password':'Temporary!123456'}).status_code==200
        assert other.get('/api/catalog').status_code==403
        assert other.post('/api/auth/password',json={'current_password':'Temporary!123456','new_password':'ChangedPassword!123456'}).status_code==200
        assert other.get('/api/catalog').status_code==200
        assert other.get('/api/audit').status_code==403
        assert post(other,'/doctors',{'name':'Dr No','code':'NO','department_id':1}).status_code==403
        assert client.patch(f"/api/staff/{admin['id']}",json={'name':'Reception','active':False,'version':2}).status_code==200
        assert other.get('/api/auth/me').status_code==401


def test_no_exports_or_finance_and_reports_reconcile(client):
    p=patient(client);dep,dr=assignment(client);visit(client,p,dep,dr)
    dashboard=client.get('/api/dashboard').json()
    assert dashboard['registrations']==1 and dashboard['total_visits']==1
    assert client.get('/api/reports',params={'kind':'visits'}).json()['total']==1
    assert client.get('/api/reports',params={'kind':'doctors'}).json()['items'][0]['patients']==1
    for route in ['/api/export','/api/billing','/api/uploads','/api/reports/export']:
        assert client.get(route).status_code==404


def test_login_rate_limit(client):
    for _ in range(5):
        assert client.post('/api/auth/login',json={'username':'master','password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'username':'master','password':'TestMaster!123456'}).status_code==429


def test_unauthenticated_and_reopen_persistence(client):
    p=patient(client);dep,dr=assignment(client);f,_=follow(client,p,dep,dr)
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/patients').status_code==401
    m.init_db()
    assert client.post('/api/auth/login',json={'username':'master','password':'TestMaster!123456'}).status_code==200
    assert client.get('/api/reminders').json()[0]['id']==f['id']


def test_daily_doctor_tokens_and_inactive_masters(client, monkeypatch):
    p=patient(client);dep,dr=assignment(client)
    first=visit(client,p,dep,dr)
    original=m.local_now
    monkeypatch.setattr(m,'local_now',lambda db:original(db)+timedelta(days=1))
    second=visit(client,p,dep,dr)
    assert first['token']==second['token']==1 and first['visit_date']!=second['visit_date']
    r=client.patch(f"/api/doctors/{dr['id']}",json={'name':dr['name'],'code':dr['code'],'department_id':dep['id'],'version':dr['version'],'active':False})
    assert r.status_code==200
    assert post(client,'/visits',{'patient_id':p['id'],'doctor_id':dr['id'],'department_id':dep['id'],'complaints':[{'text':'New complaint'}]}).status_code==400
    assert client.get(f"/api/visits/{first['id']}").json()['visit']['doctor_name']==dr['name']


def test_dob_age_and_pagination(client):
    day=client.get('/api/catalog').json()['today']
    p=patient(client,dob=day,age_value=99)
    assert p['age_value']==0 and p['age_unit']=='Days' and p['approximate']==0
    for i in range(21):
        patient(client,name=f'Person{i}',phone=f'98000000{i:02d}')
    a=client.get('/api/patients',params={'page':1}).json()
    b=client.get('/api/patients',params={'page':2}).json()
    assert a['total']==22 and len(a['items'])==20 and len(b['items'])==2
    assert set(x['id'] for x in a['items']).isdisjoint(x['id'] for x in b['items'])


def test_backup_restore_copy(client, tmp_path, monkeypatch):
    if m.DATABASE_URL:
        pytest.skip("SQLite backup format is specific to offline mode.")
    from backend import manage
    import sys
    p=patient(client);dep,dr=assignment(client);visit(client,p,dep,dr)
    backup=tmp_path/'backup.sqlite3'
    restored=tmp_path/'restored.sqlite3'
    monkeypatch.setattr(sys,'argv',['manage','backup',str(backup)])
    manage.main()
    monkeypatch.setattr(sys,'argv',['manage','restore-copy',str(backup),str(restored)])
    manage.main()
    import sqlite3
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT count(*) FROM patients').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM visits').fetchone()[0]==1
    monkeypatch.setattr(sys,'argv',['manage','restore-copy',str(backup),str(m.DB_PATH)])
    with pytest.raises(SystemExit):
        manage.main()


def test_daily_notifications_start_at_nine_and_repeat_next_day(client, monkeypatch):
    from zoneinfo import ZoneInfo
    day=client.get('/api/catalog').json()['today']
    p=patient(client);dep,dr=assignment(client)
    f,_=follow(client,p,dep,dr)
    zone=ZoneInfo('Asia/Kolkata')
    monkeypatch.setattr(m,'local_now',lambda db:datetime.fromisoformat(day+'T08:59:00').replace(tzinfo=zone))
    assert client.get('/api/daily-reminders').json()==[]
    monkeypatch.setattr(m,'local_now',lambda db:datetime.fromisoformat(day+'T09:00:00').replace(tzinfo=zone))
    assert client.get('/api/daily-reminders').json()[0]['id']==f['id']
    assert post(client,f"/daily-reminders/{f['id']}",{'revision':1,'action':'acknowledge'}).status_code==200
    assert client.get('/api/daily-reminders').json()==[]
    next_day=(datetime.fromisoformat(day)+timedelta(days=1)).date().isoformat()
    monkeypatch.setattr(m,'local_now',lambda db:datetime.fromisoformat(next_day+'T09:00:00').replace(tzinfo=zone))
    assert client.get('/api/daily-reminders').json()[0]['id']==f['id']
    assert post(client,f"/daily-reminders/{f['id']}",{'revision':1,'action':'snooze','minutes':30}).status_code==200
    assert client.get('/api/daily-reminders').json()==[]


def test_doctor_day_disable_enable_expiry_and_visit_guard(client,monkeypatch):
    p=patient(client);dep,dr=assignment(client);v=visit(client,p,dep,dr)
    day=client.get('/api/catalog').json()['today']
    response=client.patch(f"/api/doctors/{dr['id']}/availability",json={'version':dr['version'],'disabled':True})
    assert response.status_code==200,response.text
    expiry=response.json()['disabled_until']
    from zoneinfo import ZoneInfo
    local_expiry=datetime.fromisoformat(expiry).astimezone(ZoneInfo('Asia/Kolkata'))
    with m.connect() as db:
        expected_day=datetime.fromisoformat(day).date()+(timedelta(days=1) if m.local_now(db).hour>=8 else timedelta())
    assert local_expiry.hour==8 and local_expiry.date()==expected_day
    assert client.get('/api/queues').json()['items']==[]
    assert client.get('/api/visits').json()['total']==1
    assert client.get('/api/doctor-availability').json()['items'][0]['disabled_until']==expiry
    result=post(client,'/visits',{'patient_id':p['id'],'department_id':dep['id'],'doctor_id':dr['id'],'visit_type':'New','complaints':[{'text':'Fever'}],'duplicate_ack':True})
    assert result.status_code==409
    assert client.patch(f"/api/doctors/{dr['id']}/availability",json={'version':dr['version'],'disabled':False}).status_code==409
    dr=client.get('/api/catalog').json()['doctors'][0]
    assert client.patch(f"/api/doctors/{dr['id']}/availability",json={'version':dr['version'],'disabled':False}).status_code==200
    assert len(client.get('/api/queues').json()['items'])==1
    dr=client.get('/api/catalog').json()['doctors'][0]
    client.patch(f"/api/doctors/{dr['id']}/availability",json={'version':dr['version'],'disabled':True}).raise_for_status()
    with m.connect() as db:
        db.execute('UPDATE sessions SET expires=?', ((datetime.fromisoformat(expiry)+timedelta(days=1)).isoformat(timespec='seconds'),))
    before=datetime.fromisoformat(expiry)-timedelta(seconds=1)
    monkeypatch.setattr(m,'now',lambda:before.isoformat(timespec='seconds'))
    monkeypatch.setattr(m,'local_now',lambda db:before.astimezone(ZoneInfo('Asia/Kolkata')))
    assert client.get('/api/queues').json()['items']==[]
    after=datetime.fromisoformat(expiry)
    monkeypatch.setattr(m,'now',lambda:after.isoformat(timespec='seconds'))
    monkeypatch.setattr(m,'local_now',lambda db:after.astimezone(ZoneInfo('Asia/Kolkata')))
    assert len(client.get('/api/queues').json()['items'])==1
    assert client.get('/api/catalog').json()['doctors'][0]['disabled_until'] is None


def test_doctor_reset_uses_next_eight_am_even_when_disabled_before_dawn(client,monkeypatch):
    from zoneinfo import ZoneInfo
    zone=ZoneInfo('Asia/Kolkata')
    dep,dr=assignment(client)
    day=client.get('/api/catalog').json()['today']
    for clock,days in [('02:00:00',0),('07:59:59',0),('08:00:00',1),('23:59:59',1)]:
        local=datetime.fromisoformat(day+'T'+clock).replace(tzinfo=zone)
        monkeypatch.setattr(m,'local_now',lambda db:local)
        monkeypatch.setattr(m,'now',lambda:local.astimezone(timezone.utc).isoformat(timespec='seconds'))
        with m.connect() as db:
            db.execute('UPDATE sessions SET expires=?',((local+timedelta(days=3)).isoformat(timespec='seconds'),))
        dr=client.get('/api/catalog').json()['doctors'][0]
        result=client.patch(f"/api/doctors/{dr['id']}/availability",json={'version':dr['version'],'disabled':True})
        assert result.status_code==200,result.text
        expiry=datetime.fromisoformat(result.json()['disabled_until']).astimezone(zone)
        assert expiry==local.replace(hour=8,minute=0,second=0)+timedelta(days=days)
        dr=client.get('/api/catalog').json()['doctors'][0]
        assert client.patch(f"/api/doctors/{dr['id']}/availability",json={'version':dr['version'],'disabled':False}).status_code==200


def test_password_complexity_enforced_for_creation_change_and_reset(client):
    weak=['abcdefghijkl1!','Abcdefghijkl!','Abcdefghijkl1','Abc1!','Abcdefghijk1 ']
    for password in weak:
        assert m.password_policy_error(password)
        assert post(client,'/staff',{'name':'Reception','username':'weaktest','password':password}).status_code==400
        assert client.post('/api/auth/password',json={'current_password':'TestMaster!123456','new_password':password}).status_code in (400,422)
    admin=post(client,'/staff',{'name':'Reception','username':'strictadmin','password':'Temporary!123456'}).json()
    response=client.patch(f"/api/staff/{admin['id']}",json={'version':admin['version'],'name':admin['name'],'active':True,'new_password':'Nouppercase123'})
    assert response.status_code==400
    saved=next(row for row in client.get('/api/catalog').json()['staff'] if row['id']==admin['id'])
    assert saved['version']==admin['version']
    assert m.password_policy_error('StrictPassword1!') is None
    assert m.password_policy_error('StrictPassword1'+' '*10) is not None


def test_database_reads_keep_one_snapshot_while_another_request_writes(client):
    with m.connect() as reader:
        reader.execute('BEGIN')
        original=reader.execute("SELECT name FROM users WHERE role='Master'").fetchone()[0]
        with m.connect() as writer:
            writer.execute('BEGIN IMMEDIATE')
            writer.execute("UPDATE users SET name=? WHERE role='Master'",('Updated test name',))
        assert reader.execute("SELECT name FROM users WHERE role='Master'").fetchone()[0]==original
    with m.connect() as reader:
        assert reader.execute("SELECT name FROM users WHERE role='Master'").fetchone()[0]=='Updated test name'

def test_department_color_inherits_to_doctors_and_queue(client):
    dep, dr = assignment(client)
    assert dep['color'] == '#DBEAFE'
    payload = {**{k: dep[k] for k in ('name', 'code', 'description', 'active', 'version')}, 'color': '#EDE9FE'}
    response = client.patch(f"/api/departments/{dep['id']}", json=payload)
    assert response.status_code == 200, response.text
    changed = response.json()
    catalog = client.get('/api/catalog').json()
    assert catalog['doctors'][0]['department_color'] == '#EDE9FE'
    queue = client.get('/api/queues', params={'day': catalog['today']}).json()
    assert queue['items'][0]['department_color'] == '#EDE9FE'
    p = patient(client)
    v = visit(client, p, dep, dr)
    assert client.get(f"/api/visits/{v['id']}").json()['visit']['department_color'] == '#EDE9FE'
    payload['color'] = '#000000'
    payload['version'] = changed['version']
    assert client.patch(f"/api/departments/{dep['id']}", json=payload).status_code == 422
    del payload['color']
    assert client.patch(f"/api/departments/{dep['id']}", json=payload).json()['color'] == '#EDE9FE'


def test_next_seven_days_followups_count_and_boundaries(client):
    p = patient(client)
    dep, dr = assignment(client)
    day = datetime.fromisoformat(client.get('/api/catalog').json()['today'])
    included = []
    for offset in [0, 1, 3, 7, 8]:
        due = (day + timedelta(days=offset)).date().isoformat()
        item, body = follow(client, p, dep, dr, due_date=due, reminder_local=due+'T09:00')
        if offset == 3:
            client.patch(f"/api/followups/{item['id']}", json={**body, 'version': 1, 'reason': 'Patient cancelled', 'status': 'Cancelled'}).raise_for_status()
        elif offset in [1, 7]:
            included.append(item['id'])
    params = {'view': 'Next 7 days'}
    count = client.get('/api/followups', params={**params, 'count_only': True})
    assert count.status_code == 200
    assert count.json() == {'total': 2}
    result = client.get('/api/followups', params=params).json()
    assert result['total'] == 2
    assert [item['id'] for item in result['items']] == included


def test_service_bill_without_visit(client):
    p=patient(client)
    body={'patient_id':p['id'],'extras':[{'description':'X-ray chest','quantity':1,'unit_price_paise':45000}]}
    key=str(uuid.uuid4())
    response=post(client,'/service-bills',body,key)
    assert response.status_code==200,response.text
    bill=response.json()
    assert bill['visit_id'] is None
    assert bill['number'].startswith('BILL-')
    assert bill['total_paise']==45000
    assert all(line['kind']=='Additional charge' for line in bill['lines'])
    assert post(client,'/service-bills',body,key).json()['id']==bill['id']
    assert client.get('/api/visits').json()['total']==0
    assert client.get('/api/bills').json()['items'][0]['id']==bill['id']
    assert post(client,'/service-bills',{'patient_id':p['id'],'extras':[]}).status_code==422
    assert post(client,'/service-bills',{'patient_id':99999,'extras':body['extras']}).status_code==404
    paid=post(client,f"/bills/{bill['id']}/payments",{'version':bill['version'],'amount_paise':10000,'method':'Cash','reference':''})
    assert paid.status_code==200,paid.text
    updated=paid.json()
    edited=client.patch(f"/api/bills/{bill['id']}",headers={'Idempotency-Key':str(uuid.uuid4())},json={'version':updated['version'],'extras':[{'description':'X-ray chest','quantity':1,'unit_price_paise':50000}],'note':'Service bill edit'})
    assert edited.status_code==200,edited.text
    assert edited.json()['balance_paise']==40000
    assert len(client.get(f"/api/bills/{bill['id']}/revisions").json()['items'])==2
    empty=client.patch(f"/api/bills/{bill['id']}",headers={'Idempotency-Key':str(uuid.uuid4())},json={'version':edited.json()['version'],'extras':[]})
    assert empty.status_code==400
