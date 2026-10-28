"""Generate isolated fictional preview data. Never seeds the real hospital database."""
import os
from datetime import datetime, timedelta
from pathlib import Path
import secrets
import uuid

PREVIEW = Path(__file__).resolve().parent / 'data' / 'preview.sqlite3'
if __name__ == '__main__':
    if PREVIEW.exists():
        raise SystemExit('Preview database already exists; it has not been modified.')
    os.environ['OPD_DATABASE'] = str(PREVIEW)
    os.environ['local_db'] = 'True'
    from fastapi.testclient import TestClient
    from backend import main as m

    m.DATABASE_URL = ''  # Preview generation must never write to configured Neon.
    password = 'Preview1!' + secrets.token_urlsafe(18)
    with TestClient(m.app, headers={'X-OPD-Request':'1'}) as client:
        def post(path, body):
            response = client.post('/api'+path, json=body, headers={'Idempotency-Key':str(uuid.uuid4())})
            response.raise_for_status()
            return response.json()
        post('/auth/setup', {'username':'preview','password':password,'name':'Demo Administrator', 'hospital_name':'Carelane Demo Hospital','setup_key':m.SETUP_PATH.read_text()})
        departments = [post('/departments', {'name':n,'code':c}) for n,c in [('General Medicine','GEN'),('Orthopaedics','ORTHO'),('Paediatrics','PED')]]
        doctors = [post('/doctors', {'name':n,'code':f'DR{i+1}','department_id':departments[i]['id'],'designation':d}) for i,(n,d) in enumerate([('Dr. Meera Kulkarni','MD · General Medicine'),('Dr. Arjun Deshmukh','MS · Orthopaedics'),('Dr. Priya Shah','MD · Paediatrics')])]
        names = [('Ananya','Patil','Female',34),('Rahul','Joshi','Male',46),('Saanvi','Desai','Female',8),('Vikram','Shinde','Male',52),('Neha','Kulkarni','Female',27),('Aarav','More','Male',11),('Ishita','Naik','Female',31),('Aditya','Kadam','Male',42),('Maya','Jadhav','Female',63),('Rohan','Sawant','Male',29)]
        day = client.get('/api/catalog').json()['today']
        for i,(first,last,gender,age) in enumerate(names):
            p = post('/patients', {'first_name':first,'surname':last,'gender':gender,'age_value':age,'phone':f'90000000{i:02d}', 'address':'Fictional demo locality, Maharashtra','data':{'city':'Demo City','state':'Maharashtra'}})
            if i == 0:
                post(f"/patients/{p['id']}/history",{'category':'Allergies','state':'Information reported','content':'Patient reports a penicillin allergy','source':'Patient'})
            dr,dep = doctors[i%3],departments[i%3]
            v=post('/visits',{'patient_id':p['id'],'doctor_id':dr['id'],'department_id':dep['id'],'visit_type':'Follow-up' if i%3==0 else 'New','complaints':[{'text':['Fever','Joint pain','Cough'][i%3],'duration':'2 days'}]})
            if i<4:
                client.patch(f"/api/visits/{v['id']}",json={'version':1,'status':['Completed','Completed','Being Attended','Called'][i]}).raise_for_status()
            due = (datetime.fromisoformat(day)+timedelta(days=(i%5)-1)).date().isoformat()
            if i<6:
                post('/followups',{'patient_id':p['id'],'origin_visit_id':v['id'],'doctor_id':dr['id'],'department_id':dep['id'],'due_date':due,'due_time':'','reminder_local':due+'T00:00','note':'Fictional record for interface preview only.'})
        # Populate a small historical activity series, preserving each visit's immutable token allocation.
        with m.connect() as db:
            for i in range(1,7):
                previous=(datetime.fromisoformat(day)-timedelta(days=i)).date().isoformat()
                for j in range([3,5,4,7,3,6][i-1]):
                    dr,dep=doctors[j%3],departments[j%3]
                    token=m.next_token(db,dr['id'],previous)
                    arrival=previous+'T04:00:00+00:00'
                    vid=db.execute("INSERT INTO visits(patient_id,doctor_id,department_id,visit_date,arrival_at,visit_type,complaints,status,token,created_by,created_at,updated_at) VALUES(?,?,?,?,?,'New',?,'Completed',?,1,?,?)",(j%10+1,dr['id'],dep['id'],previous,arrival,'[{"text":"Demo complaint","duration":"1 day"}]',token,arrival,arrival)).lastrowid
                    db.execute('INSERT INTO token_allocations(doctor_id,day,token,visit_id) VALUES(?,?,?,?)',(dr['id'],previous,token,vid))
                    db.execute('INSERT INTO visit_events(visit_id,status,note,actor,created_at) VALUES(?,?,?,?,?)',(vid,'Completed','Synthetic historical visit',1,arrival))
    access = PREVIEW.parent / 'preview-access.txt'
    access.write_text('Username: preview\nPassword: '+password+'\nFictional preview database only.\n',encoding='utf-8')
    print(f'Fictional preview created. Local credentials: {access}')
