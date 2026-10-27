"""Hospital OPD API with Neon PostgreSQL and an explicit SQLite offline/test mode."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from dotenv import load_dotenv
if __package__:
    from . import postgres
else:
    import postgres

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / '.env', override=False)
load_dotenv(ROOT / '.env', override=False)
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
DATABASE_SCHEMA = os.environ.get('OPD_DATABASE_SCHEMA', 'public')
if DATABASE_URL and not DATABASE_URL.startswith(('postgresql://', 'postgres://')):
    raise RuntimeError('DATABASE_URL must be a PostgreSQL connection URL.')
DB_PATH = Path(os.environ.get('OPD_DATABASE', ROOT / 'data' / 'opd.sqlite3'))
SETUP_PATH = DB_PATH.with_suffix('.setup-key')
STATES = ['Waiting', 'Called', 'Being Attended', 'On Hold', 'Completed', 'Cancelled', 'No Show']
HISTORY_CATEGORIES = ['Conditions', 'Allergies', 'Medications', 'Surgeries', 'Hospitalizations', 'Family history', 'Lifestyle']
DEFAULT_SETTINGS = {'hospital_name': 'Hospital OPD', 'address': '', 'phone': '', 'timezone': 'Asia/Kolkata',
                    'transfer_policy': 'Unspecified', 'reminder_time': '', 'language': 'English'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def fail(message, status=400):
    raise HTTPException(status, message)


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def connect():
    if DATABASE_URL:
        return postgres.connect(DATABASE_URL, DATABASE_SCHEMA)
    db = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    return db


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        if not DATABASE_URL:
            db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO schema_version VALUES(1);
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE, name TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('Admin','Master')), password TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
          must_change INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_master ON users(role) WHERE role='Master';
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY, failures INTEGER NOT NULL, blocked_until TEXT);
        CREATE TABLE IF NOT EXISTS departments(id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE, code TEXT NOT NULL COLLATE NOCASE UNIQUE,
          description TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS doctors(id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL COLLATE NOCASE UNIQUE,
          department_id INTEGER NOT NULL REFERENCES departments(id), designation TEXT NOT NULL DEFAULT '', contact TEXT NOT NULL DEFAULT '',
          active INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS lookups(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
          version INTEGER NOT NULL DEFAULT 1, UNIQUE(kind,name));
        CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY, uhid TEXT NOT NULL UNIQUE CHECK(length(uhid)=8), first_name TEXT NOT NULL,
          middle_name TEXT NOT NULL DEFAULT '', surname TEXT NOT NULL DEFAULT '', gender TEXT NOT NULL, age_value INTEGER NOT NULL CHECK(age_value>=0),
          age_unit TEXT NOT NULL, dob TEXT, approximate INTEGER NOT NULL DEFAULT 1, age_recorded_on TEXT NOT NULL,
          phone TEXT NOT NULL DEFAULT '', no_mobile INTEGER NOT NULL DEFAULT 0, address TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}',
          active INTEGER NOT NULL DEFAULT 1, merged_into INTEGER REFERENCES patients(id), version INTEGER NOT NULL DEFAULT 1,
          created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS patient_phone ON patients(phone);
        CREATE INDEX IF NOT EXISTS patient_name ON patients(first_name,surname);
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id), category TEXT NOT NULL,
          state TEXT NOT NULL, content TEXT NOT NULL, source TEXT NOT NULL, source_details TEXT NOT NULL DEFAULT '',
          actor INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS visits(id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id), doctor_id INTEGER NOT NULL REFERENCES doctors(id),
          department_id INTEGER NOT NULL REFERENCES departments(id), visit_date TEXT NOT NULL, arrival_at TEXT NOT NULL, visit_type TEXT NOT NULL,
          complaints TEXT NOT NULL, remarks TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Waiting', token INTEGER NOT NULL,
          history_ids TEXT NOT NULL DEFAULT '[]', version INTEGER NOT NULL DEFAULT 1, created_by INTEGER NOT NULL REFERENCES users(id),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS token_counters(doctor_id INTEGER NOT NULL REFERENCES doctors(id), day TEXT NOT NULL,
          value INTEGER NOT NULL, PRIMARY KEY(doctor_id,day));
        CREATE TABLE IF NOT EXISTS token_allocations(id INTEGER PRIMARY KEY, doctor_id INTEGER NOT NULL REFERENCES doctors(id), day TEXT NOT NULL,
          token INTEGER NOT NULL, visit_id INTEGER NOT NULL REFERENCES visits(id), UNIQUE(doctor_id,day,token));
        CREATE TABLE IF NOT EXISTS visit_events(id INTEGER PRIMARY KEY, visit_id INTEGER NOT NULL REFERENCES visits(id),
          status TEXT NOT NULL, note TEXT NOT NULL, actor INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS visit_day ON visits(visit_date,doctor_id,status);
        CREATE TABLE IF NOT EXISTS doctor_day_availability(doctor_id INTEGER PRIMARY KEY REFERENCES doctors(id), disabled_until TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS billing_charges(id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            price_paise INTEGER NOT NULL CHECK(price_paise>0), active INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS bills(id INTEGER PRIMARY KEY AUTOINCREMENT, visit_id INTEGER NOT NULL UNIQUE REFERENCES visits(id),
          bill_date TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'INR', snapshot TEXT NOT NULL, lines TEXT NOT NULL,
          total_paise INTEGER NOT NULL CHECK(total_paise>=0), note TEXT NOT NULL DEFAULT '',
          version INTEGER NOT NULL DEFAULT 1, created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bill_revisions(bill_id INTEGER NOT NULL REFERENCES bills(id), revision INTEGER NOT NULL CHECK(revision>0),
          document TEXT NOT NULL, actor INTEGER NOT NULL REFERENCES users(id), actor_name TEXT NOT NULL,
          reason TEXT NOT NULL DEFAULT '', recorded_at TEXT NOT NULL, PRIMARY KEY(bill_id,revision));
        CREATE TABLE IF NOT EXISTS bill_payments(id INTEGER PRIMARY KEY AUTOINCREMENT, bill_id INTEGER NOT NULL REFERENCES bills(id),
          amount_paise INTEGER NOT NULL CHECK(amount_paise>0), method TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '',
          received_by INTEGER NOT NULL REFERENCES users(id), receiver_name TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS bill_payment_bill ON bill_payments(bill_id,id);
        CREATE INDEX IF NOT EXISTS bill_date_index ON bills(bill_date,id);
        CREATE TABLE IF NOT EXISTS followups(id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id),
          origin_visit_id INTEGER REFERENCES visits(id), doctor_id INTEGER NOT NULL REFERENCES doctors(id), department_id INTEGER NOT NULL REFERENCES departments(id),
          due_date TEXT NOT NULL, due_time TEXT NOT NULL DEFAULT '', reminder_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
          assigned_to INTEGER REFERENCES users(id), status TEXT NOT NULL DEFAULT 'Scheduled', attendance_visit_id INTEGER UNIQUE REFERENCES visits(id),
          schedule_revision INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1, created_by INTEGER NOT NULL REFERENCES users(id),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS daily_reminder_ack(followup_id INTEGER NOT NULL REFERENCES followups(id), revision INTEGER NOT NULL,
          user_id INTEGER NOT NULL REFERENCES users(id), day TEXT NOT NULL, snooze_until TEXT, acknowledged INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(followup_id,revision,user_id,day));
        CREATE INDEX IF NOT EXISTS followup_due ON followups(status,due_date,reminder_at);
        CREATE INDEX IF NOT EXISTS followup_origin ON followups(origin_visit_id,status,id);
        CREATE TABLE IF NOT EXISTS followup_events(id INTEGER PRIMARY KEY, followup_id INTEGER NOT NULL REFERENCES followups(id),
          kind TEXT NOT NULL, detail TEXT NOT NULL, actor INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY, followup_id INTEGER NOT NULL REFERENCES followups(id),
          outcome TEXT NOT NULL, note TEXT NOT NULL, actor INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reminder_ack(followup_id INTEGER NOT NULL REFERENCES followups(id), revision INTEGER NOT NULL,
          user_id INTEGER NOT NULL REFERENCES users(id), snooze_until TEXT, acknowledged INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(followup_id,revision,user_id));
        CREATE TABLE IF NOT EXISTS audits(id INTEGER PRIMARY KEY, actor INTEGER REFERENCES users(id), action TEXT NOT NULL,
          entity TEXT NOT NULL, entity_id INTEGER, detail TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS idempotency(user_id INTEGER NOT NULL, key TEXT NOT NULL, path TEXT NOT NULL, digest TEXT NOT NULL,
          result TEXT NOT NULL, PRIMARY KEY(user_id,key));
        ''')
        if 'color' not in (db.columns('departments') if DATABASE_URL else {row['name'] for row in db.execute('PRAGMA table_info(departments)')}):
            db.execute("ALTER TABLE departments ADD COLUMN color TEXT NOT NULL DEFAULT '#DBEAFE'")
        doctor_columns = db.columns('doctors') if DATABASE_URL else {row['name'] for row in db.execute('PRAGMA table_info(doctors)')}
        for column in ('consultation_fee_paise', 'followup_fee_paise'):
            if column not in doctor_columns:
                db.execute(f'ALTER TABLE doctors ADD COLUMN {column} INTEGER CHECK({column} IS NULL OR {column}>=0)')
        if 'version' not in (db.columns('bills') if DATABASE_URL else {row['name'] for row in db.execute('PRAGMA table_info(bills)')}):
            db.execute('ALTER TABLE bills ADD COLUMN version INTEGER NOT NULL DEFAULT 1')
        db.execute('INSERT OR IGNORE INTO settings(id,data) VALUES(1,?)', (dump(DEFAULT_SETTINGS),))
        # Existing bills become an honest baseline; historical contents cannot be invented.
        for row in db.execute('SELECT id,created_by FROM bills b WHERE NOT EXISTS (SELECT 1 FROM bill_revisions r WHERE r.bill_id=b.id)').fetchall():
            actor = record(db, 'users', row['created_by'])
            save_bill_revision(db, row['id'], {'id': actor['id'], 'name': 'System migration'}, 'Existing bill baseline; earlier revisions were not stored.')
        if DATABASE_URL:
            db.execute("""CREATE OR REPLACE FUNCTION reject_bill_revision_change() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Bill revisions are immutable'; END; $$""")
            db.execute('CREATE OR REPLACE TRIGGER bill_revisions_immutable BEFORE UPDATE OR DELETE ON bill_revisions FOR EACH ROW EXECUTE FUNCTION reject_bill_revision_change()')
        else:
            for action in ('UPDATE', 'DELETE'):
                db.execute(f"CREATE TRIGGER IF NOT EXISTS bill_revisions_no_{action.lower()} BEFORE {action} ON bill_revisions BEGIN SELECT RAISE(ABORT, 'Bill revisions are immutable'); END")
        lookup_defaults = []
        for kind, values in {'visit_type': ['New', 'Follow-up'], 'complaint': ['Fever', 'Cough', 'Headache', 'Abdominal pain'],
                             'referral': ['Walk-in', 'Doctor referral'], 'cancel_reason': ['Patient request', 'Doctor unavailable'],
                             'reschedule_reason': ['Patient request', 'Doctor unavailable'],
                             'contact_outcome': ['No answer', 'Contacted', 'Confirmed', 'Requested reschedule', 'Other']}.items():
            for value in values:
                lookup_defaults.append((kind, value))
        db.executemany('INSERT OR IGNORE INTO lookups(kind,name) VALUES(?,?)', lookup_defaults)
        if not db.execute("SELECT 1 FROM users WHERE role='Master'").fetchone() and not SETUP_PATH.exists():
            SETUP_PATH.write_text(secrets.token_urlsafe(24), encoding='utf-8')


@asynccontextmanager
async def lifespan(app):
    postgres.acquire_application()
    try:
        init_db()
        yield
    finally:
        postgres.release_application()


app = FastAPI(title='Hospital OPD API', version='1.0.0', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def security(request: Request, call_next):
    if request.method in ('POST', 'PATCH', 'PUT', 'DELETE') and request.headers.get('x-opd-request') != '1':
        return JSONResponse({'detail': 'Missing application request header.'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


@app.exception_handler(psycopg.IntegrityError)
@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse({'detail': 'This conflicts with an existing record. Refresh and check unique names/codes.'}, status_code=409)


def database(request: Request):
    db = connect()
    try:
        db.execute('BEGIN IMMEDIATE' if request.method not in ('GET', 'HEAD') else 'BEGIN')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_settings(db):
    if isinstance(db, postgres.Connection) and db.settings_cache is not None:
        return dict(db.settings_cache)
    row = db.execute('SELECT * FROM settings WHERE id=1').fetchone()
    settings = {**json.loads(row['data']), 'version': row['version']}
    if isinstance(db, postgres.Connection):
        db.settings_cache = settings
    return dict(settings)


def local_now(db):
    return datetime.now(ZoneInfo(get_settings(db)['timezone']))


def today(db):
    return local_now(db).date().isoformat()


def audit(db, user, action, entity, entity_id=None, detail=''):
    db.execute('INSERT INTO audits(actor,action,entity,entity_id,detail,created_at) VALUES(?,?,?,?,?,?)',
               (user['id'] if user else None, action, entity, entity_id, detail, now()))


def record(db, table, key):
    row = db.execute(f'SELECT * FROM {table} WHERE id=?', (key,)).fetchone()
    if not row:
        fail('Record not found.', 404)
    return dict(row)


def check_version(row, version):
    if row['version'] != version:
        fail('Another staff member changed this record. Refresh before editing.', 409)


def password_policy_error(password):
    if not (12 <= len(password) <= 128 and re.search(r'[A-Z]', password) and re.search(r'[0-9]', password)
            and any(not c.isalnum() and not c.isspace() for c in password)):
        return 'Password must contain 12–128 characters, at least one uppercase letter, one number and one symbol.'
    return None


def password_hash(password):
    error = password_policy_error(password)
    if error:
        fail(error)
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest


def password_matches(password, encoded):
    salt, expected = encoded.split(':')
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)


def public_user(row):
    return {k: row[k] for k in ('id', 'name', 'username', 'role', 'active', 'must_change', 'version')}


def current_user(request: Request, db=Depends(database)):
    token = request.cookies.get('opd_session', '')
    digest = hashlib.sha256(token.encode()).hexdigest()
    row = db.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1', (digest, now())).fetchone()
    if not row:
        fail('Please sign in to continue.', 401)
    if row['must_change'] and request.url.path not in ('/api/auth/me', '/api/auth/password', '/api/auth/logout'):
        fail('Please change your temporary password first.', 403)
    return dict(row)


def master(user=Depends(current_user)):
    if user['role'] != 'Master':
        fail('Master access is required.', 403)
    return user


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Credentials(StrictModel):
    username: str = Field(min_length=3, max_length=80, pattern=r'^[A-Za-z0-9._-]+$')
    password: str = Field(min_length=1, max_length=128)


class Setup(Credentials):
    name: str = Field(min_length=2, max_length=100)
    hospital_name: str = Field(min_length=2, max_length=120)
    setup_key: str


class PasswordChange(StrictModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)


def set_session(db, user_id, response):
    token = secrets.token_urlsafe(40)
    db.execute('DELETE FROM sessions WHERE expires<?', (now(),))
    db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user_id,
               (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat(timespec='seconds')))
    response.set_cookie('opd_session', token, httponly=True, samesite='strict', secure=os.environ.get('OPD_SECURE_COOKIE') == '1', max_age=28800, path='/')


@app.get('/api/health')
def health(db=Depends(database)):
    return {'ok': True, 'database': 'postgresql' if DATABASE_URL else 'sqlite', 'setup_required': not bool(db.execute("SELECT 1 FROM users WHERE role='Master'").fetchone())}


@app.post('/api/auth/setup')
def setup(body: Setup, response: Response, db=Depends(database)):
    if db.execute("SELECT 1 FROM users WHERE role='Master'").fetchone():
        fail('Setup has already been completed.', 409)
    if not SETUP_PATH.exists() or not hmac.compare_digest(body.setup_key, SETUP_PATH.read_text().strip()):
        fail('Invalid setup key. Read the key on the local server.', 403)
    if len(body.password) < 12:
        fail('Use a password of at least 12 characters.')
    uid = db.execute("INSERT INTO users(username,name,role,password,created_at) VALUES(?,?,'Master',?,?)",
                     (body.username, body.name, password_hash(body.password), now())).lastrowid
    settings = get_settings(db)
    settings.pop('version')
    settings['hospital_name'] = body.hospital_name
    db.execute('UPDATE settings SET data=?,version=version+1 WHERE id=1', (dump(settings),))
    audit(db, {'id': uid}, 'Initial setup', 'user', uid)
    set_session(db, uid, response)
    # Presence of the Master in the database makes the on-disk key unusable after setup.
    return public_user(record(db, 'users', uid))


@app.post('/api/auth/login')
def login(body: Credentials, request: Request, response: Response, db=Depends(database)):
    key = hashlib.sha256(body.username.lower().encode()).hexdigest()
    attempt = db.execute('SELECT * FROM login_attempts WHERE key=?', (key,)).fetchone()
    if attempt and attempt['blocked_until'] and attempt['blocked_until'] > now():
        fail('Too many attempts. Try again in 15 minutes.', 429)
    row = db.execute('SELECT * FROM users WHERE LOWER(username)=LOWER(?)', (body.username,)).fetchone()
    if not row or not row['active'] or not password_matches(body.password, row['password']):
        failures = (attempt['failures'] if attempt and (not attempt['blocked_until'] or attempt['blocked_until'] > now()) else 0) + 1
        blocked = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(timespec='seconds') if failures >= 5 else None
        db.execute('INSERT INTO login_attempts VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET failures=excluded.failures,blocked_until=excluded.blocked_until', (key, failures, blocked))
        db.commit()  # Failed authentication attempts must survive the error rollback.
        fail('Invalid username or password.', 401)
    db.execute('DELETE FROM login_attempts WHERE key=?', (key,))
    set_session(db, row['id'], response)
    audit(db, row, 'Signed in', 'user', row['id'])
    return public_user(row)


@app.get('/api/auth/me')
def me(user=Depends(current_user)):
    return public_user(user)


@app.post('/api/auth/logout')
def logout(request: Request, response: Response, user=Depends(current_user), db=Depends(database)):
    db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(request.cookies.get('opd_session', '').encode()).hexdigest(),))
    response.delete_cookie('opd_session', path='/')
    return {'ok': True}


@app.post('/api/auth/password')
def change_password(body: PasswordChange, response: Response, user=Depends(current_user), db=Depends(database)):
    if not password_matches(body.current_password, user['password']):
        fail('Current password is incorrect.', 403)
    db.execute('UPDATE users SET password=?,must_change=0,version=version+1 WHERE id=?', (password_hash(body.new_password), user['id']))
    db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
    set_session(db, user['id'], response)
    audit(db, user, 'Changed password', 'user', user['id'])
    return {'ok': True}


def replay(db, user, request, body):
    key = request.headers.get('idempotency-key', '')
    if not key or len(key) > 100:
        fail('A valid submission key is required.')
    digest = hashlib.sha256(dump(body).encode()).hexdigest()
    row = db.execute('SELECT * FROM idempotency WHERE user_id=? AND key=?', (user['id'], key)).fetchone()
    if row:
        if row['path'] != request.url.path or row['digest'] != digest:
            fail('Submission key was used for different data.', 409)
        return key, digest, json.loads(row['result'])
    return key, digest, None


def save_replay(db, user, request, key, digest, result):
    db.execute('INSERT INTO idempotency VALUES(?,?,?,?,?)', (user['id'], key, request.url.path, digest, dump(result)))
    return result


class PatientInput(StrictModel):
    first_name: str = Field(min_length=1, max_length=240)
    middle_name: str = Field(default='', max_length=80)
    surname: str = Field(default='', max_length=80)
    gender: str = Field(min_length=1, max_length=40)
    age_value: int = Field(ge=0, le=150)
    age_unit: str = 'Years'
    dob: str | None = None
    approximate: bool = True
    phone: str = Field(default='', max_length=20)
    no_mobile: bool = False
    address: str = Field(min_length=3, max_length=500)
    data: dict[str, str] = Field(default_factory=dict)
    active: bool = True
    version: int | None = None
    duplicate_ack: bool = False

    @model_validator(mode='after')
    def validate_patient(self):
        if self.gender not in ['Male', 'Female', 'Other', 'Unknown', 'Prefer not to say']:
            raise ValueError('Select a valid gender.')
        if self.age_unit not in ['Years', 'Months', 'Days']:
            raise ValueError('Select a valid age unit.')
        if not self.no_mobile and not re.fullmatch(r'\d{10}', self.phone):
            raise ValueError('Enter a 10-digit phone or select No mobile.')
        if self.no_mobile:
            self.phone = ''
        if self.dob:
            date.fromisoformat(self.dob)
            self.approximate = False
        allowed = {'additional_phone', 'email', 'area', 'landmark', 'city', 'state', 'pincode', 'emergency_name', 'emergency_relationship', 'emergency_phone', 'blood_group', 'referral', 'remarks'}
        if set(self.data) - allowed or any(len(v) > 1000 for v in self.data.values()):
            raise ValueError('Invalid additional patient details.')
        for key in ('additional_phone', 'emergency_phone'):
            if self.data.get(key) and not re.fullmatch(r'\d{10}', self.data[key]):
                raise ValueError('Additional and emergency phones must contain 10 digits.')
        if self.data.get('pincode') and not re.fullmatch(r'\d{6}', self.data['pincode']):
            raise ValueError('Pincode must contain 6 digits.')
        if self.data.get('email') and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', self.data['email']):
            raise ValueError('Enter a valid email address.')
        return self


def patient_json(row):
    item = dict(row)
    item['data'] = json.loads(item['data'])
    item['name'] = ' '.join(filter(None, [item['first_name'], item['middle_name'], item['surname']]))
    return item


def valid_patient(db, pid):
    row = record(db, 'patients', pid)
    if row['merged_into']:
        fail(f"This patient was merged into patient {row['merged_into']}. Open the surviving record.", 409)
    if not row['active']:
        fail('Reactivate this patient before creating new records.', 409)
    return row


def normalize_age(db, body):
    if body.dob:
        birth = date.fromisoformat(body.dob)
        current = local_now(db).date()
        if birth > current or birth.year < current.year - 150:
            fail('Enter a valid past date of birth.', 422)
        years = current.year - birth.year - ((current.month, current.day) < (birth.month, birth.day))
        months = (current.year-birth.year)*12 + current.month-birth.month - (current.day < birth.day)
        if years >= 1:
            body.age_value, body.age_unit = years, 'Years'
        elif months >= 1:
            body.age_value, body.age_unit = months, 'Months'
        else:
            body.age_value, body.age_unit = (current-birth).days, 'Days'
        body.approximate = False


def duplicates(db, body, exclude=0):
    full_name = ' '.join(filter(None, [body.first_name, body.middle_name, body.surname]))
    rows = db.execute('''SELECT * FROM patients WHERE merged_into IS NULL AND id<>? AND
      lower(trim(first_name||' '||CASE WHEN middle_name='' THEN '' ELSE middle_name||' ' END||surname))=lower(?) LIMIT 10''',
                      (exclude, full_name)).fetchall()
    return [patient_json(x) for x in rows]


@app.get('/api/patients')
def patients(q: str = '', page: int = 1, include_inactive: bool = False, name_only: bool = False, user=Depends(current_user), db=Depends(database)):
    page = max(1, page)
    text = ' '.join(q[:100].split())
    def pattern(value):
        return '%' + value.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
    search = pattern(text)
    tokens = text.split()
    # Name parts can be partial, reordered, or separated by a stored middle name.
    name_clause = ' AND '.join("(first_name||' '||middle_name||' '||surname) LIKE ? ESCAPE '!'" for _ in tokens) or '1=1'
    where = f"merged_into IS NULL AND (?=1 OR active=1) AND (uhid LIKE ? ESCAPE '!' OR ({name_clause}) OR phone LIKE ? ESCAPE '!' OR id IN (SELECT merged_into FROM patients WHERE uhid LIKE ? ESCAPE '!'))"
    args = (int(include_inactive), search, *(pattern(token) for token in tokens), search, search)
    if name_only:
        where = f'merged_into IS NULL AND (?=1 OR active=1) AND ({name_clause})'
        args = (int(include_inactive), *(pattern(token) for token in tokens))
    total = db.execute(f'SELECT count(*) FROM patients WHERE {where}', args).fetchone()[0]
    rows = db.execute(f'SELECT * FROM patients WHERE {where} ORDER BY id DESC LIMIT 20 OFFSET ?', (*args, (page-1)*20)).fetchall()
    return {'items': [patient_json(x) for x in rows], 'total': total, 'page': page}


@app.post('/api/patients/check-duplicates')
def check_duplicates(body: PatientInput, user=Depends(current_user), db=Depends(database)):
    return duplicates(db, body)


@app.post('/api/patients')
def create_patient(body: PatientInput, request: Request, user=Depends(current_user), db=Depends(database)):
    key, digest, result = replay(db, user, request, body.model_dump())
    if result is not None:
        return result
    normalize_age(db, body)
    matches = duplicates(db, body)
    if matches and not body.duplicate_ack:
        raise HTTPException(409, {'message': 'Possible existing patients. Review before creating another record.', 'duplicates': matches})
    uhid = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
    while db.execute('SELECT 1 FROM patients WHERE uhid=?', (uhid,)).fetchone():
        uhid = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
    values = body.model_dump(exclude={'version', 'duplicate_ack'})
    values['data'] = dump(body.data)
    values.update(uhid=uhid, age_recorded_on=today(db), created_by=user['id'], created_at=now(), updated_at=now())
    cols = list(values)
    pid = db.execute(f"INSERT INTO patients({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", list(values.values())).lastrowid
    audit(db, user, 'Registered patient', 'patient', pid, 'Duplicate warning acknowledged' if matches else '')
    return save_replay(db, user, request, key, digest, patient_json(record(db, 'patients', pid)))


@app.patch('/api/patients/{pid}')
def edit_patient(pid: int, body: PatientInput, user=Depends(current_user), db=Depends(database)):
    old = record(db, 'patients', pid)
    if old['merged_into']:
        fail('Merged records cannot be edited.', 409)
    check_version(old, body.version)
    normalize_age(db, body)
    values = body.model_dump(exclude={'version', 'duplicate_ack'})
    values['data'] = dump(body.data)
    values.update(age_recorded_on=today(db), updated_at=now())
    db.execute(f"UPDATE patients SET {','.join(k+'=?' for k in values)},version=version+1 WHERE id=?", (*values.values(), pid))
    changed = [k for k in values if str(old.get(k)) != str(values[k]) and k not in ('updated_at', 'age_recorded_on')]
    audit(db, user, 'Updated patient', 'patient', pid, dump({'fields': changed, 'previous': {k: old.get(k) for k in changed}}))
    return patient_json(record(db, 'patients', pid))


@app.get('/api/patients/{pid}')
def patient_detail(pid: int, user=Depends(current_user), db=Depends(database)):
    patient = patient_json(record(db, 'patients', pid))
    if patient['merged_into']:
        return {'redirect_to': patient['merged_into']}
    history = db.execute('SELECT h.*,u.name AS actor_name FROM history h JOIN users u ON u.id=h.actor WHERE patient_id=? ORDER BY h.id DESC', (pid,)).fetchall()
    visits = db.execute(VISIT_SELECT + ' WHERE v.patient_id=? ORDER BY v.id DESC', (pid,)).fetchall()
    follows = db.execute(FOLLOW_SELECT + ' WHERE f.patient_id=? ORDER BY f.due_date DESC', (pid,)).fetchall()
    aliases = db.execute('SELECT uhid FROM patients WHERE merged_into=?', (pid,)).fetchall()
    return {'patient': patient, 'history': [dict(x) for x in history], 'visits': [visit_json(x) for x in visits],
            'followups': [dict(x) for x in follows], 'aliases': [x[0] for x in aliases]}


class HistoryInput(StrictModel):
    category: str
    state: str
    content: str = Field(default='', max_length=4000)
    source: str = 'Patient'
    source_details: str = Field(default='', max_length=200)
    previous_id: int | None = None


@app.post('/api/patients/{pid}/history')
def add_history(pid: int, body: HistoryInput, user=Depends(current_user), db=Depends(database)):
    valid_patient(db, pid)
    if body.category not in HISTORY_CATEGORIES or body.state not in ['Information reported', 'None reported', 'Unknown', 'Not asked'] or body.source not in ['Patient', 'Caregiver']:
        fail('Invalid reported history classification.')
    if body.state == 'Information reported' and not body.content:
        fail('Describe the reported information.')
    previous = db.execute('SELECT id FROM history WHERE patient_id=? AND category=? ORDER BY id DESC LIMIT 1', (pid, body.category)).fetchone()
    if (previous[0] if previous else None) != body.previous_id:
        fail('This history category changed. Refresh before adding your update.', 409)
    hid = db.execute('INSERT INTO history(patient_id,category,state,content,source,source_details,actor,created_at) VALUES(?,?,?,?,?,?,?,?)',
                     (pid, body.category, body.state, body.content if body.state == 'Information reported' else '', body.source, body.source_details, user['id'], now())).lastrowid
    audit(db, user, 'Added history revision', 'history', hid, f'Patient {pid}; {body.category}')
    return record(db, 'history', hid)


class MergeInput(StrictModel):
    source_id: int
    target_id: int
    source_version: int
    target_version: int
    reason: str = Field(min_length=5, max_length=500)


@app.post('/api/patients/merge/preview')
def merge_preview(body: MergeInput, user=Depends(master), db=Depends(database)):
    if body.source_id == body.target_id:
        fail('Choose two different patients.')
    source, target = record(db, 'patients', body.source_id), record(db, 'patients', body.target_id)
    if source['merged_into'] or target['merged_into']:
        fail('Choose unmerged patient records.')
    check_version(source, body.source_version)
    check_version(target, body.target_version)
    conflicts = {k: {'source': source[k], 'retained': target[k]} for k in ('first_name', 'surname', 'gender', 'dob', 'age_value', 'phone', 'address', 'data') if source[k] != target[k]}
    return {'source': patient_json(source), 'target': patient_json(target), 'conflicts': conflicts,
            'counts': {t: db.execute(f'SELECT count(*) FROM {t} WHERE patient_id=?', (body.source_id,)).fetchone()[0] for t in ('visits', 'history', 'followups')}}


@app.post('/api/patients/merge/confirm')
def merge_confirm(body: MergeInput, user=Depends(master), db=Depends(database)):
    preview = merge_preview(body, user, db)
    for table in ('visits', 'history', 'followups'):
        if table == 'history':
            db.execute('UPDATE history SET patient_id=? WHERE patient_id=?', (body.target_id, body.source_id))
        else:
            db.execute(f'UPDATE {table} SET patient_id=?,version=version+1,updated_at=? WHERE patient_id=?', (body.target_id, now(), body.source_id))
    db.execute('UPDATE patients SET merged_into=?,active=0,version=version+1,updated_at=? WHERE id=? OR merged_into=?', (body.target_id, now(), body.source_id, body.source_id))
    db.execute('UPDATE patients SET version=version+1,updated_at=? WHERE id=?', (now(), body.target_id))
    audit(db, user, 'Merged patient', 'patient', body.target_id, dump({'reason': body.reason, 'source_id': body.source_id, 'source_snapshot': preview['source'], 'conflicts': preview['conflicts']}))
    return {'id': body.target_id}


VISIT_SELECT = '''SELECT v.*,trim(p.first_name||' '||CASE WHEN p.middle_name='' THEN '' ELSE p.middle_name||' ' END||p.surname) AS patient_name,p.uhid,p.phone,
 (SELECT b.id FROM bills b WHERE b.visit_id=v.id) AS bill_id,
 (SELECT f.id FROM followups f WHERE f.origin_visit_id=v.id AND f.status!='Cancelled' ORDER BY f.id DESC LIMIT 1) AS followup_id,
 d.name AS doctor_name,dep.name AS department_name,dep.color AS department_color FROM visits v JOIN patients p ON p.id=v.patient_id
 JOIN doctors d ON d.id=v.doctor_id JOIN departments dep ON dep.id=v.department_id'''
FOLLOW_SELECT = '''SELECT f.*,trim(p.first_name||' '||CASE WHEN p.middle_name='' THEN '' ELSE p.middle_name||' ' END||p.surname) AS patient_name,p.uhid,p.phone,
 d.name AS doctor_name,dep.name AS department_name,dep.color AS department_color,u.name AS assigned_name,
 (SELECT outcome FROM contacts WHERE followup_id=f.id ORDER BY id DESC LIMIT 1) AS last_contact
 FROM followups f JOIN patients p ON p.id=f.patient_id JOIN doctors d ON d.id=f.doctor_id
 JOIN departments dep ON dep.id=f.department_id LEFT JOIN users u ON u.id=f.assigned_to'''


def visit_json(row):
    item = dict(row)
    item['complaints'] = json.loads(item['complaints'])
    item['history_ids'] = json.loads(item['history_ids'])
    return item


def doctor_valid(db, did, depid):
    dr = record(db, 'doctors', did)
    dep = record(db, 'departments', depid)
    if not dr['active'] or not dep['active'] or dr['department_id'] != depid:
        fail('Choose an active doctor in the selected active department.')


def next_token(db, doctor, day):
    db.execute('INSERT INTO token_counters VALUES(?,?,1) ON CONFLICT(doctor_id,day) DO UPDATE SET value=token_counters.value+1', (doctor, day))
    return db.execute('SELECT value FROM token_counters WHERE doctor_id=? AND day=?', (doctor, day)).fetchone()[0]


class Complaint(StrictModel):
    text: str = Field(min_length=1, max_length=500)
    duration: str = Field(default='', max_length=100)


class VisitInput(StrictModel):
    patient_id: int
    doctor_id: int
    department_id: int
    visit_type: str = 'New'
    complaints: list[Complaint] = Field(min_length=1, max_length=20)
    remarks: str = Field(default='', max_length=2000)
    duplicate_ack: bool = False
    followup_id: int | None = None
    followup_version: int | None = None


@app.get('/api/visits')
def visits(day: str = '', doctor_id: int = 0, department_id: int = 0, status: str = '', q: str = '', page: int = 1,
           user=Depends(current_user), db=Depends(database)):
    args = [day or today(db), doctor_id, doctor_id, department_id, department_id, status, status, f'%{q[:100]}%', f'%{q[:100]}%']
    where = " WHERE v.visit_date=? AND (?=0 OR v.doctor_id=?) AND (?=0 OR v.department_id=?) AND (?='' OR v.status=?) AND (trim(p.first_name||' '||CASE WHEN p.middle_name='' THEN '' ELSE p.middle_name||' ' END||p.surname) LIKE ? OR p.uhid LIKE ?)"
    total = db.execute('SELECT count(*) FROM ('+VISIT_SELECT+where+')', args).fetchone()[0]
    rows = db.execute(VISIT_SELECT+where+' ORDER BY v.arrival_at,v.id LIMIT 30 OFFSET ?', (*args, (max(1, page)-1)*30)).fetchall()
    return {'items': [visit_json(x) for x in rows], 'total': total, 'page': page}


@app.get('/api/billing-visits')
def billing_visits(start: str = '', end: str = '', q: str = '', page: int = 1,
                   user=Depends(current_user), db=Depends(database)):
    if start and end and start > end:
        fail('Start date must be before the end date.')
    where = " WHERE v.status='Completed' AND (?='' OR v.visit_date>=?) AND (?='' OR v.visit_date<=?) AND (trim(p.first_name||' '||p.middle_name||' '||p.surname) LIKE ? OR p.uhid LIKE ?)"
    args = [start, start, end, end, f'%{q[:100]}%', f'%{q[:100]}%']
    total = db.execute('SELECT count(*) FROM ('+VISIT_SELECT+where+')', args).fetchone()[0]
    rows = db.execute(VISIT_SELECT+where+' ORDER BY v.visit_date DESC,v.id DESC LIMIT 30 OFFSET ?', (*args, (max(1, page)-1)*30)).fetchall()
    return {'items': [visit_json(row) for row in rows], 'total': total, 'page': max(1, page)}


def available_doctors(db):
    rows = db.execute("""SELECT d.*,dep.name AS department_name,dep.color AS department_color,a.disabled_until FROM doctors d
      JOIN departments dep ON dep.id=d.department_id LEFT JOIN doctor_day_availability a ON a.doctor_id=d.id ORDER BY d.name""").fetchall()
    return [{**dict(row), 'disabled_until': row['disabled_until'] if row['disabled_until'] and row['disabled_until'] > now() else None} for row in rows]


@app.get('/api/doctor-availability')
def doctor_availability(user=Depends(current_user), db=Depends(database)):
    return {'items': available_doctors(db)}


class DoctorAvailabilityInput(StrictModel):
    version: int
    disabled: bool


@app.patch('/api/doctors/{did}/availability')
def set_doctor_availability(did: int, body: DoctorAvailabilityInput, user=Depends(current_user), db=Depends(database)):
    doctor = record(db, 'doctors', did)
    check_version(doctor, body.version)
    if not doctor['active']:
        fail('This doctor is inactive in Master setup. Master must activate the doctor first.', 409)
    local = local_now(db)
    reset = local.replace(hour=8,minute=0,second=0,microsecond=0)
    if reset <= local:
        reset += timedelta(days=1)
    expiry = reset.astimezone(timezone.utc).isoformat(timespec='seconds')
    if body.disabled:
        db.execute('INSERT INTO doctor_day_availability VALUES(?,?) ON CONFLICT(doctor_id) DO UPDATE SET disabled_until=excluded.disabled_until', (did, expiry))
    else:
        db.execute('DELETE FROM doctor_day_availability WHERE doctor_id=?', (did,))
    db.execute('UPDATE doctors SET version=version+1 WHERE id=?', (did,))
    audit(db, user, 'Disabled doctor for day' if body.disabled else 'Enabled doctor for day', 'doctor', did, dump({'disabled_until': expiry if body.disabled else None}))
    return {'ok': True, 'disabled_until': expiry if body.disabled else None}


@app.get('/api/queues')
def doctor_queues(day: str = '', department_id: int = 0, user=Depends(current_user), db=Depends(database)):
    queue_day = day or today(db)
    doctors = db.execute('''SELECT d.id,d.name,d.active,d.department_id,dep.name AS department_name,dep.color AS department_color
        FROM doctors d JOIN departments dep ON dep.id=d.department_id
        WHERE (?=0 OR d.department_id=?) AND ((d.active=1 AND dep.active=1) OR EXISTS
        (SELECT 1 FROM visits v WHERE v.doctor_id=d.id AND v.visit_date=?))
        ORDER BY dep.name COLLATE NOCASE,d.name COLLATE NOCASE''',
        (department_id, department_id, queue_day)).fetchall()
    if queue_day == today(db):
        hidden = {d['id'] for d in available_doctors(db) if d['disabled_until']}
        doctors = [d for d in doctors if d['id'] not in hidden]
    rows = db.execute(VISIT_SELECT + ' WHERE v.visit_date=? AND (?=0 OR v.department_id=?) ORDER BY v.arrival_at,v.id',
                      (queue_day, department_id, department_id)).fetchall()
    groups = {d['id']: {**dict(d), 'total': 0, 'counts': {state: 0 for state in STATES},
                        'waiting': [], 'attending': [], 'cancelled': []} for d in doctors}
    for row in rows:
        group = groups.get(row['doctor_id'])
        if group is None:
            continue
        group['total'] += 1
        group['counts'][row['status']] = group['counts'].get(row['status'], 0) + 1
        if row['status'] == 'Waiting' and len(group['waiting']) < 3:
            group['waiting'].append(visit_json(row))
        elif row['status'] == 'Being Attended' and len(group['attending']) < 2:
            group['attending'].append(visit_json(row))
        elif row['status'] == 'Cancelled' and len(group['cancelled']) < 3:
            group['cancelled'].append(visit_json(row))
    return {'day': queue_day, 'items': list(groups.values()),
            'total_visits': sum(group['total'] for group in groups.values())}


@app.post('/api/visits')
def create_visit(body: VisitInput, request: Request, user=Depends(current_user), db=Depends(database)):
    key, digest, result = replay(db, user, request, body.model_dump())
    if result is not None:
        return result
    valid_patient(db, body.patient_id)
    doctor_valid(db, body.doctor_id, body.department_id)
    unavailable = db.execute('SELECT disabled_until FROM doctor_day_availability WHERE doctor_id=? AND disabled_until>?', (body.doctor_id, now())).fetchone()
    if unavailable:
        fail('This doctor is disabled until the next 8 AM reset. Re-enable the doctor from Doctor queues before creating a visit.', 409)
    if not db.execute("SELECT 1 FROM lookups WHERE kind='visit_type' AND name=? AND active=1", (body.visit_type,)).fetchone():
        fail('Choose an active visit type.')
    day = today(db)
    existing = db.execute("SELECT id FROM visits WHERE patient_id=? AND doctor_id=? AND visit_date=? AND status NOT IN ('Completed','Cancelled','No Show')", (body.patient_id, body.doctor_id, day)).fetchone()
    if existing and not body.duplicate_ack:
        fail('An active visit already exists for this patient and doctor today. Review it, or explicitly acknowledge a separate visit.', 409)
    follow = None
    if body.followup_id:
        follow = record(db, 'followups', body.followup_id)
        check_version(follow, body.followup_version)
        if follow['patient_id'] != body.patient_id or follow['status'] != 'Scheduled' or follow['attendance_visit_id']:
            fail('This follow-up cannot be linked to another attendance.', 409)
        if body.visit_type != 'Follow-up':
            fail('A linked return visit must use Follow-up type.')
    token = next_token(db, body.doctor_id, day)
    history_ids = [x[0] for x in db.execute('SELECT max(id) FROM history WHERE patient_id=? GROUP BY category', (body.patient_id,))]
    vid = db.execute('''INSERT INTO visits(patient_id,doctor_id,department_id,visit_date,arrival_at,visit_type,complaints,remarks,token,history_ids,created_by,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', (body.patient_id, body.doctor_id, body.department_id, day, now(), body.visit_type,
        dump([c.model_dump() for c in body.complaints]), body.remarks, token, dump(history_ids), user['id'], now(), now())).lastrowid
    db.execute('INSERT INTO token_allocations(doctor_id,day,token,visit_id) VALUES(?,?,?,?)', (body.doctor_id, day, token, vid))
    db.execute('INSERT INTO visit_events(visit_id,status,note,actor,created_at) VALUES(?,?,?,?,?)', (vid, 'Waiting', 'Visit created', user['id'], now()))
    if follow:
        db.execute("UPDATE followups SET status='Attended',attendance_visit_id=?,version=version+1,updated_at=? WHERE id=?", (vid, now(), body.followup_id))
        follow_event(db, body.followup_id, 'Attended', f'Linked new visit {vid}', user)
    audit(db, user, 'Created visit', 'visit', vid, 'Separate visit warning acknowledged' if existing else '')
    return save_replay(db, user, request, key, digest, visit_json(db.execute(VISIT_SELECT+' WHERE v.id=?', (vid,)).fetchone()))


class VisitUpdate(StrictModel):
    version: int
    status: str
    reason: str = Field(default='', max_length=1000)
    doctor_id: int | None = None
    department_id: int | None = None
    complaints: list[Complaint] | None = Field(default=None, min_length=1, max_length=20)
    remarks: str | None = Field(default=None, max_length=2000)


@app.patch('/api/visits/{vid}')
def update_visit(vid: int, body: VisitUpdate, user=Depends(current_user), db=Depends(database)):
    old = record(db, 'visits', vid)
    check_version(old, body.version)
    if body.status not in STATES:
        fail('Invalid visit status.')
    if db.execute('SELECT 1 FROM bills WHERE visit_id=?', (vid,)).fetchone() and (
            body.status != 'Completed' or body.doctor_id not in (None, old['doctor_id']) or body.department_id not in (None, old['department_id'])):
        fail('A bill has been generated for this visit. Its completed status and doctor assignment cannot be changed.', 409)
    if (body.status in ('Cancelled', 'No Show') or old['status'] in ('Completed', 'Cancelled', 'No Show')) and len(body.reason) < 3:
        fail('Enter a reason for cancellation/no-show or correction to a closed visit.')
    doctor, dep, token = body.doctor_id or old['doctor_id'], body.department_id or old['department_id'], old['token']
    if doctor != old['doctor_id'] or dep != old['department_id']:
        doctor_valid(db, doctor, dep)
        if db.execute('SELECT 1 FROM doctor_day_availability WHERE doctor_id=? AND disabled_until>?', (doctor, now())).fetchone():
            fail('This doctor is temporarily disabled. Enable the doctor from Doctor queues before reassignment.', 409)
        if not body.reason:
            fail('Enter a reason for reassignment.')
        policy = get_settings(db)['transfer_policy']
        if policy == 'Unspecified':
            fail('Doctor transfer token policy is undecided. Master must choose it in Settings before transferring.')
        token = next_token(db, doctor, old['visit_date'])
        if policy == 'Preserve if available':
            used = db.execute('SELECT 1 FROM token_allocations WHERE doctor_id=? AND day=? AND token=?', (doctor, old['visit_date'], old['token'])).fetchone()
            if not used:
                token = old['token']
                db.execute('UPDATE token_counters SET value=max(value,?) WHERE doctor_id=? AND day=?', (token, doctor, old['visit_date']))
        db.execute('INSERT INTO token_allocations(doctor_id,day,token,visit_id) VALUES(?,?,?,?)', (doctor, old['visit_date'], token, vid))
    complaints = dump([c.model_dump() for c in body.complaints]) if body.complaints is not None else old['complaints']
    remarks = body.remarks if body.remarks is not None else old['remarks']
    db.execute('UPDATE visits SET status=?,doctor_id=?,department_id=?,token=?,complaints=?,remarks=?,version=version+1,updated_at=? WHERE id=?',
               (body.status, doctor, dep, token, complaints, remarks, now(), vid))
    detail = dump({'reason': body.reason, 'previous_status': old['status'], 'previous_doctor': old['doctor_id'], 'previous_token': old['token'],
                   'previous_complaints': json.loads(old['complaints']) if old['complaints'] != complaints else None,
                   'previous_remarks': old['remarks'] if old['remarks'] != remarks else None})
    db.execute('INSERT INTO visit_events(visit_id,status,note,actor,created_at) VALUES(?,?,?,?,?)', (vid, body.status, detail, user['id'], now()))
    audit(db, user, 'Updated visit', 'visit', vid, detail)
    return visit_json(db.execute(VISIT_SELECT+' WHERE v.id=?', (vid,)).fetchone())


@app.get('/api/visits/{vid}')
def visit_detail(vid: int, user=Depends(current_user), db=Depends(database)):
    visit = record(db, 'visits', vid)
    events = db.execute('SELECT e.*,u.name AS actor_name FROM visit_events e JOIN users u ON u.id=e.actor WHERE visit_id=? ORDER BY e.id DESC', (vid,)).fetchall()
    ids = json.loads(visit['history_ids'])
    history = [dict(x) for x in db.execute(f"SELECT * FROM history WHERE id IN ({','.join('?' for _ in ids)})", ids)] if ids else []
    return {'visit': visit_json(db.execute(VISIT_SELECT+' WHERE v.id=?', (vid,)).fetchone()), 'events': [dict(x) for x in events], 'history': history}


def bill_json(db, bid):
    bill = record(db, 'bills', bid)
    bill['bill_revision'] = db.execute('SELECT COALESCE(MAX(revision),0) FROM bill_revisions WHERE bill_id=?', (bid,)).fetchone()[0]
    bill['number'] = f"OPD-{bill['bill_date'].replace('-', '')}-{bill['id']:06d}"
    bill['snapshot'], bill['lines'] = json.loads(bill['snapshot']), json.loads(bill['lines'])
    bill['payments'] = [dict(row) for row in db.execute('SELECT * FROM bill_payments WHERE bill_id=? ORDER BY id', (bid,))]
    bill['paid_paise'] = sum(payment['amount_paise'] for payment in bill['payments'])
    bill['balance_paise'] = bill['total_paise'] - bill['paid_paise']
    bill['payment_status'] = 'Paid' if bill['balance_paise'] == 0 else 'Part paid' if bill['paid_paise'] else 'Unpaid'
    return bill


def save_bill_revision(db, bid, user, reason=''):
    document = bill_json(db, bid)
    revision = document['bill_revision'] + 1
    document['bill_revision'] = revision
    timestamp = now()
    db.execute('''INSERT INTO bill_revisions(bill_id,revision,document,actor,actor_name,reason,recorded_at)
        VALUES(?,?,?,?,?,?,?)''', (bid, revision, dump(document), user['id'], user['name'], reason, timestamp))
    return revision


@app.get('/api/bills/{bid}/revisions')
def bill_revisions(bid: int, user=Depends(current_user), db=Depends(database)):
    record(db, 'bills', bid)
    rows = db.execute('SELECT revision,actor,actor_name,reason,recorded_at,document FROM bill_revisions WHERE bill_id=? ORDER BY revision DESC', (bid,)).fetchall()
    return {'items': [{**{k: row[k] for k in ('revision', 'actor', 'actor_name', 'reason', 'recorded_at')},
                       'total_paise': json.loads(row['document'])['total_paise']} for row in rows]}


@app.get('/api/bills/{bid}/revisions/{revision}')
def bill_revision_detail(bid: int, revision: int, user=Depends(current_user), db=Depends(database)):
    row = db.execute('SELECT * FROM bill_revisions WHERE bill_id=? AND revision=?', (bid, revision)).fetchone()
    if not row:
        fail('Bill revision not found.', 404)
    return {'bill': json.loads(row['document']), 'revision': row['revision'], 'actor_name': row['actor_name'],
            'recorded_at': row['recorded_at'], 'reason': row['reason']}


@app.get('/api/visits/{vid}/billing')
def visit_billing(vid: int, user=Depends(current_user), db=Depends(database)):
    record(db, 'visits', vid)
    visit = visit_json(db.execute(VISIT_SELECT + ' WHERE v.id=?', (vid,)).fetchone())
    doctor = record(db, 'doctors', visit['doctor_id'])
    fee = doctor['followup_fee_paise'] if visit['visit_type'] == 'Follow-up' else doctor['consultation_fee_paise']
    return {'visit': visit, 'doctor_version': doctor['version'], 'consultation_fee_paise': fee,
            'bill': bill_json(db, visit['bill_id']) if visit['bill_id'] else None}


class BillExtra(StrictModel):
    charge_id: int | None = None
    charge_version: int | None = None
    description: str = Field(min_length=1, max_length=200)
    quantity: int = Field(default=1, strict=True, ge=1, le=999)
    unit_price_paise: int = Field(strict=True, ge=1, le=100_000_000)


class BillInput(StrictModel):
    visit_id: int
    visit_version: int
    doctor_version: int
    extras: list[BillExtra] = Field(default_factory=list, max_length=50)
    note: str = Field(default='', max_length=1000)


@app.post('/api/bills')
def create_bill(body: BillInput, request: Request, user=Depends(current_user), db=Depends(database)):
    key, digest, result = replay(db, user, request, body.model_dump())
    if result is not None:
        return result
    visit = record(db, 'visits', body.visit_id)
    if db.execute('SELECT 1 FROM bills WHERE visit_id=?', (visit['id'],)).fetchone():
        fail('A bill already exists for this visit. Open the existing bill.', 409)
    check_version(visit, body.visit_version)
    if visit['status'] != 'Completed':
        fail('Complete the visit before generating a bill.', 409)
    doctor = record(db, 'doctors', visit['doctor_id'])
    check_version(doctor, body.doctor_version)
    fee = doctor['followup_fee_paise'] if visit['visit_type'] == 'Follow-up' else doctor['consultation_fee_paise']
    if fee is None:
        fail('Master must configure this doctor’s consultation fee for this visit type before billing.')
    patient = patient_json(record(db, 'patients', visit['patient_id']))
    settings = get_settings(db)
    snapshot = {'hospital': {field: settings[field] for field in ('hospital_name', 'address', 'phone')},
                'patient': {field: patient[field] for field in ('name', 'uhid', 'address', 'phone', 'age_value', 'age_unit', 'gender')},
                'doctor_name': doctor['name'], 'department_name': record(db, 'departments', visit['department_id'])['name'],
                'visit_date': visit['visit_date'], 'visit_type': visit['visit_type'], 'token': visit['token'], 'issued_by': user['name']}
    lines = [{'description': f"{visit['visit_type']} consultation · {doctor['name']}", 'quantity': 1,
              'unit_price_paise': fee, 'amount_paise': fee, 'kind': 'Consultation'}]
    for extra in body.extras:
        if extra.charge_id is not None:
            charge = record(db, 'billing_charges', extra.charge_id)
            check_version(charge, extra.charge_version)
            if not charge['active']:
                fail('This billing charge is inactive. Remove it and select an active charge.', 409)
            if extra.unit_price_paise != charge['price_paise'] or extra.description != charge['name']:
                fail('This billing charge has changed. Remove it and select it again.', 409)
        if not extra.description.strip():
            fail('Enter a description for every additional charge.')
        lines.append({**extra.model_dump(), 'amount_paise': extra.quantity * extra.unit_price_paise, 'kind': 'Additional charge'})
    total = sum(line['amount_paise'] for line in lines)
    if total > 1_000_000_000:
        fail('Bill total exceeds the supported amount.')
    bid = db.execute('''INSERT INTO bills(visit_id,bill_date,snapshot,lines,total_paise,note,created_by,created_at)
        VALUES(?,?,?,?,?,?,?,?)''', (visit['id'], today(db), dump(snapshot), dump(lines), total, body.note, user['id'], now())).lastrowid
    save_bill_revision(db, bid, user, 'Bill generated')
    audit(db, user, 'Generated bill', 'bill', bid, dump({'visit_id': visit['id'], 'total_paise': total}))
    return save_replay(db, user, request, key, digest, bill_json(db, bid))


class BillUpdate(StrictModel):
    version: int
    reason: str = Field(default='', max_length=1000)
    extras: list[BillExtra] = Field(default_factory=list, max_length=50)
    note: str = Field(default='', max_length=1000)


@app.patch('/api/bills/{bid}')
def edit_bill(bid: int, body: BillUpdate, request: Request, user=Depends(current_user), db=Depends(database)):
    key, digest, result = replay(db, user, request, body.model_dump())
    if result is not None:
        return result
    old = bill_json(db, bid)
    check_version(old, body.version)
    lines = [line for line in old['lines'] if line['kind'] == 'Consultation']
    for extra in body.extras:
        if extra.charge_id is not None:
            retained = any(line.get('charge_id') == extra.charge_id and line.get('charge_version') == extra.charge_version
                           and line['description'] == extra.description and line['unit_price_paise'] == extra.unit_price_paise
                           for line in old['lines'] if line['kind'] == 'Additional charge')
            if not retained:
                charge = record(db, 'billing_charges', extra.charge_id)
                check_version(charge, extra.charge_version)
                if not charge['active'] or charge['name'] != extra.description or charge['price_paise'] != extra.unit_price_paise:
                    fail('This billing charge has changed. Remove it and select it again.', 409)
        lines.append({**extra.model_dump(), 'amount_paise': extra.quantity * extra.unit_price_paise, 'kind': 'Additional charge'})
    total = sum(line['amount_paise'] for line in lines)
    if total > 1_000_000_000:
        fail('Bill total exceeds the supported amount.')
    if total < old['paid_paise']:
        fail('Bill total cannot be less than payments already recorded.', 409)
    db.execute('UPDATE bills SET lines=?,total_paise=?,note=?,version=version+1 WHERE id=?',
               (dump(lines), total, body.note, bid))
    revision = save_bill_revision(db, bid, user, body.reason)
    audit(db, user, 'Edited bill', 'bill', bid, dump({'revision': revision, 'reason': body.reason, 'before': {'lines': old['lines'], 'total_paise': old['total_paise'], 'note': old['note']},
           'after': {'lines': lines, 'total_paise': total, 'note': body.note}}))
    return save_replay(db, user, request, key, digest, bill_json(db, bid))


@app.get('/api/bills')
def bills(start: str = '', end: str = '', status: str = '', q: str = '', page: int = 1,
          user=Depends(current_user), db=Depends(database)):
    start, end = start or today(db), end or today(db)
    if start > end:
        fail('Start date must be before the end date.')
    paid = 'COALESCE((SELECT sum(amount_paise) FROM bill_payments WHERE bill_id=b.id),0)'
    filters = {'Paid': f'b.total_paise={paid}', 'Unpaid': f'b.total_paise>0 AND {paid}=0',
               'Part paid': f'{paid}>0 AND {paid}<b.total_paise'}
    if status and status not in filters:
        fail('Invalid payment status.')
    where = ' WHERE b.bill_date BETWEEN ? AND ? AND (b.snapshot LIKE ? OR CAST(b.id AS TEXT)=?)'
    args = [start, end, f'%{q[:100]}%', q]
    if status:
        where += ' AND (' + filters[status] + ')'
    count = db.execute('SELECT count(*) FROM bills b'+where, args).fetchone()[0]
    ids = db.execute('SELECT b.id FROM bills b'+where+' ORDER BY b.id DESC LIMIT 30 OFFSET ?', (*args, (max(1, page)-1)*30)).fetchall()
    return {'items': [bill_json(db, row['id']) for row in ids], 'total': count, 'page': page}


@app.get('/api/bills/{bid}')
def bill_detail(bid: int, user=Depends(current_user), db=Depends(database)):
    return bill_json(db, bid)


class PaymentInput(StrictModel):
    version: int
    amount_paise: int = Field(strict=True, ge=1, le=1_000_000_000)
    method: str
    reference: str = Field(default='', max_length=150)


@app.post('/api/bills/{bid}/payments')
def record_payment(bid: int, body: PaymentInput, request: Request, user=Depends(current_user), db=Depends(database)):
    key, digest, result = replay(db, user, request, body.model_dump())
    if result is not None:
        return result
    bill = bill_json(db, bid)
    check_version(bill, body.version)
    if body.method not in ('Cash', 'UPI', 'Card', 'Bank transfer', 'Other'):
        fail('Choose a valid payment method.')
    if body.amount_paise > bill['balance_paise']:
        fail('Payment exceeds the outstanding balance. Refresh the bill before recording payment.', 409)
    pid = db.execute('''INSERT INTO bill_payments(bill_id,amount_paise,method,reference,received_by,receiver_name,created_at)
        VALUES(?,?,?,?,?,?,?)''', (bid, body.amount_paise, body.method, body.reference, user['id'], user['name'], now())).lastrowid
    db.execute('UPDATE bills SET version=version+1 WHERE id=?', (bid,))
    audit(db, user, 'Recorded payment', 'bill', bid, dump({'payment_id': pid, 'amount_paise': body.amount_paise, 'method': body.method}))
    return save_replay(db, user, request, key, digest, bill_json(db, bid))


class FollowInput(StrictModel):
    patient_id: int
    origin_visit_id: int | None = None
    doctor_id: int
    department_id: int
    due_date: str
    due_time: str = ''
    reminder_local: str
    note: str = Field(default='', max_length=2000)
    assigned_to: int | None = None
    duplicate_ack: bool = False


def follow_values(db, body):
    valid_patient(db, body.patient_id)
    doctor_valid(db, body.doctor_id, body.department_id)
    if body.origin_visit_id and record(db, 'visits', body.origin_visit_id)['patient_id'] != body.patient_id:
        fail('Origin visit must belong to this patient.')
    if body.assigned_to and not record(db, 'users', body.assigned_to)['active']:
        fail('Choose an active staff member.')
    try:
        date.fromisoformat(body.due_date)
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', body.due_date) or (body.due_time and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', body.due_time)):
            fail('Enter a valid follow-up date and optional HH:MM time.')
        zone = ZoneInfo(get_settings(db)['timezone'])
        due = datetime.fromisoformat(body.due_date+'T'+(body.due_time or '23:59:59')).replace(tzinfo=zone)
        reminder = datetime.fromisoformat(body.reminder_local)
        if reminder.tzinfo:
            fail('Enter the reminder in hospital local time.')
        reminder = reminder.replace(tzinfo=zone)
        if reminder > due:
            fail('Reminder cannot be later than the follow-up.')
    except ValueError:
        fail('Enter valid follow-up and reminder dates/times.')
    values = body.model_dump(exclude={'reminder_local', 'duplicate_ack'})
    values['reminder_at'] = reminder.astimezone(timezone.utc).isoformat(timespec='seconds')
    return values


def follow_event(db, fid, kind, detail, user):
    db.execute('INSERT INTO followup_events(followup_id,kind,detail,actor,created_at) VALUES(?,?,?,?,?)', (fid, kind, detail, user['id'], now()))
    audit(db, user, kind+' follow-up', 'followup', fid, detail)


def follow_overdue(db, row):
    due = datetime.fromisoformat(row['due_date']+'T'+(row['due_time'] or '23:59:59')).replace(tzinfo=ZoneInfo(get_settings(db)['timezone']))
    return row['status'] == 'Scheduled' and due < local_now(db)


@app.get('/api/followups')
def followups(view: str = 'All', doctor_id: int = 0, department_id: int = 0, status: str = '', assigned_to: int = 0,
              q: str = '', page: int = 1, due_date: str = '', user=Depends(current_user), db=Depends(database)):
    where, args = ['1=1'], []
    if due_date:
        where.append('f.due_date=?')
        args.append(due_date)
    for col, value in [('doctor_id', doctor_id), ('department_id', department_id), ('assigned_to', assigned_to), ('status', status)]:
        if value:
            where.append(f'f.{col}=?')
            args.append(value)
    if view == 'Due Today':
        where += ["f.status='Scheduled'", 'f.due_date=?']
        args.append(today(db))
    elif view == 'Upcoming':
        where += ["f.status='Scheduled'", 'f.due_date>?']
        args.append(today(db))
    elif view == 'Overdue':
        where += ["f.status='Scheduled'", "(f.due_date||'T'||CASE WHEN f.due_time='' THEN '23:59:59' ELSE f.due_time END)<?"]
        args.append(local_now(db).isoformat(timespec='seconds')[:19])
    where.append("(trim(p.first_name||' '||CASE WHEN p.middle_name='' THEN '' ELSE p.middle_name||' ' END||p.surname) LIKE ? OR p.uhid LIKE ?)")
    args += [f'%{q[:100]}%', f'%{q[:100]}%']
    query = FOLLOW_SELECT + ' WHERE ' + ' AND '.join(where)
    total = db.execute('SELECT count(*) FROM ('+query+')', args).fetchone()[0]
    rows = db.execute(query+' ORDER BY f.due_date,f.due_time,f.id LIMIT 30 OFFSET ?', (*args, (max(1, page)-1)*30)).fetchall()
    return {'items': [{**dict(x), 'overdue': follow_overdue(db, x)} for x in rows], 'total': total, 'page': page}


@app.post('/api/followups')
def create_followup(body: FollowInput, request: Request, user=Depends(current_user), db=Depends(database)):
    key, digest, result = replay(db, user, request, body.model_dump())
    if result is not None:
        return result
    values = follow_values(db, body)
    if db.execute("SELECT 1 FROM followups WHERE patient_id=? AND doctor_id=? AND due_date=? AND status='Scheduled'", (body.patient_id, body.doctor_id, body.due_date)).fetchone() and not body.duplicate_ack:
        fail('A scheduled follow-up already exists for this patient/doctor/date. Review it or acknowledge another.', 409)
    values.update(created_by=user['id'], created_at=now(), updated_at=now())
    cols = list(values)
    fid = db.execute(f"INSERT INTO followups({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", list(values.values())).lastrowid
    follow_event(db, fid, 'Scheduled', body.note, user)
    return save_replay(db, user, request, key, digest, record(db, 'followups', fid))


class FollowUpdate(FollowInput):
    version: int
    status: str = 'Scheduled'
    reason: str = Field(min_length=3, max_length=1000)


@app.patch('/api/followups/{fid}')
def update_followup(fid: int, body: FollowUpdate, user=Depends(current_user), db=Depends(database)):
    old = record(db, 'followups', fid)
    check_version(old, body.version)
    if old['status'] == 'Attended':
        fail('An attended follow-up is linked to a visit and cannot be rescheduled. Schedule a new follow-up.', 409)
    if body.status not in ['Scheduled', 'Cancelled', 'No Show']:
        fail('Attendance must be recorded by creating a linked visit.')
    if old['patient_id'] != body.patient_id:
        fail('A follow-up cannot be moved to another patient.')
    base = FollowInput(**body.model_dump(exclude={'version', 'status', 'reason'}))
    values = follow_values(db, base)
    if body.status == 'Scheduled' and not body.duplicate_ack and db.execute("SELECT 1 FROM followups WHERE id<>? AND patient_id=? AND doctor_id=? AND due_date=? AND status='Scheduled'", (fid, body.patient_id, body.doctor_id, body.due_date)).fetchone():
        fail('Another follow-up exists on that date. Review or explicitly acknowledge it.', 409)
    schedule_changed = any(values[k] != old[k] for k in ('due_date', 'due_time', 'reminder_at', 'doctor_id')) or body.status != old['status']
    values.update(status=body.status, updated_at=now())
    db.execute(f"UPDATE followups SET {','.join(k+'=?' for k in values)},version=version+1,schedule_revision=schedule_revision+? WHERE id=?", (*values.values(), int(schedule_changed), fid))
    follow_event(db, fid, 'Updated', dump({'reason': body.reason, 'previous': old}), user)
    return record(db, 'followups', fid)


@app.get('/api/followups/{fid}')
def follow_detail(fid: int, user=Depends(current_user), db=Depends(database)):
    record(db, 'followups', fid)
    row = db.execute(FOLLOW_SELECT+' WHERE f.id=?', (fid,)).fetchone()
    contacts = db.execute('SELECT c.*,u.name AS actor_name FROM contacts c JOIN users u ON u.id=c.actor WHERE followup_id=? ORDER BY c.id DESC', (fid,)).fetchall()
    events = db.execute('SELECT e.*,u.name AS actor_name FROM followup_events e JOIN users u ON u.id=e.actor WHERE followup_id=? ORDER BY e.id DESC', (fid,)).fetchall()
    return {'followup': {**dict(row), 'overdue': follow_overdue(db, row)}, 'contacts': [dict(x) for x in contacts], 'events': [dict(x) for x in events]}


class ContactInput(StrictModel):
    outcome: str = Field(min_length=1, max_length=100)
    note: str = Field(default='', max_length=2000)
    version: int


@app.post('/api/followups/{fid}/contacts')
def contact(fid: int, body: ContactInput, user=Depends(current_user), db=Depends(database)):
    row = record(db, 'followups', fid)
    check_version(row, body.version)
    if row['status'] != 'Scheduled':
        fail('Contact attempts are available for scheduled follow-ups only.')
    if not db.execute("SELECT 1 FROM lookups WHERE kind='contact_outcome' AND name=? AND active=1", (body.outcome,)).fetchone():
        fail('Choose an active contact outcome.')
    cid = db.execute('INSERT INTO contacts(followup_id,outcome,note,actor,created_at) VALUES(?,?,?,?,?)', (fid, body.outcome, body.note, user['id'], now())).lastrowid
    db.execute('UPDATE followups SET version=version+1,updated_at=? WHERE id=?', (now(), fid))
    follow_event(db, fid, 'Contact recorded', body.outcome, user)
    return record(db, 'contacts', cid)


@app.get('/api/reminders')
def reminders(user=Depends(current_user), db=Depends(database)):
    rows = db.execute(FOLLOW_SELECT+''' LEFT JOIN reminder_ack a ON a.followup_id=f.id AND a.revision=f.schedule_revision AND a.user_id=?
      WHERE f.status='Scheduled' AND f.reminder_at<=? AND COALESCE(a.acknowledged,0)=0
      AND (a.snooze_until IS NULL OR a.snooze_until<=?) ORDER BY f.reminder_at LIMIT 50''', (user['id'], now(), now())).fetchall()
    return [dict(x) for x in rows]


class ReminderAction(StrictModel):
    revision: int
    action: str
    minutes: int = Field(default=30, ge=5, le=1440)


@app.post('/api/reminders/{fid}')
def reminder_action(fid: int, body: ReminderAction, user=Depends(current_user), db=Depends(database)):
    follow = record(db, 'followups', fid)
    if follow['schedule_revision'] != body.revision or follow['status'] != 'Scheduled':
        fail('This reminder has changed. Refresh the list.', 409)
    if body.action not in ('acknowledge', 'snooze'):
        fail('Choose acknowledge or snooze.')
    until = (datetime.now(timezone.utc)+timedelta(minutes=body.minutes)).isoformat(timespec='seconds') if body.action == 'snooze' else None
    db.execute('INSERT INTO reminder_ack VALUES(?,?,?,?,?) ON CONFLICT(followup_id,revision,user_id) DO UPDATE SET snooze_until=excluded.snooze_until,acknowledged=excluded.acknowledged',
               (fid, body.revision, user['id'], until, int(body.action == 'acknowledge')))
    audit(db, user, body.action+' reminder', 'followup', fid)
    return {'ok': True}


@app.get('/api/daily-reminders')
def daily_reminders(user=Depends(current_user), db=Depends(database)):
    local = local_now(db)
    if (local.hour, local.minute) < (9, 0):
        return []
    day = local.date().isoformat()
    rows = db.execute(FOLLOW_SELECT+""" LEFT JOIN daily_reminder_ack a ON a.followup_id=f.id
      AND a.revision=f.schedule_revision AND a.user_id=? AND a.day=?
      WHERE f.status='Scheduled' AND f.due_date<=? AND COALESCE(a.acknowledged,0)=0
      AND (a.snooze_until IS NULL OR a.snooze_until<=?) ORDER BY f.due_date,f.id""",
      (user['id'], day, day, now())).fetchall()
    return [dict(row) for row in rows]


@app.post('/api/daily-reminders/{fid}')
def daily_reminder_action(fid: int, body: ReminderAction, user=Depends(current_user), db=Depends(database)):
    follow = record(db, 'followups', fid)
    if follow['schedule_revision'] != body.revision or follow['status'] != 'Scheduled':
        fail('This reminder has changed. Refresh the list.', 409)
    if body.action not in ('acknowledge', 'snooze'):
        fail('Choose acknowledge or snooze.')
    until = (datetime.now(timezone.utc)+timedelta(minutes=body.minutes)).isoformat(timespec='seconds') if body.action == 'snooze' else None
    db.execute("""INSERT INTO daily_reminder_ack VALUES(?,?,?,?,?,?)
      ON CONFLICT(followup_id,revision,user_id,day) DO UPDATE SET snooze_until=excluded.snooze_until,acknowledged=excluded.acknowledged""",
      (fid, body.revision, user['id'], today(db), until, int(body.action == 'acknowledge')))
    audit(db, user, body.action+' daily reminder', 'followup', fid)
    return {'ok': True}


@app.get('/api/catalog')
def catalog(user=Depends(current_user), db=Depends(database)):
    return {'departments': [dict(x) for x in db.execute('SELECT * FROM departments ORDER BY name')],
            'doctors': available_doctors(db),
            'billing_charges': [dict(x) for x in db.execute('SELECT * FROM billing_charges ORDER BY name')],
            'lookups': [dict(x) for x in db.execute('SELECT * FROM lookups ORDER BY kind,name')],
            'staff': [public_user(x) for x in db.execute('SELECT * FROM users ORDER BY name')],
            'settings': get_settings(db), 'today': today(db)}


class DepartmentInput(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=1, max_length=20)
    color: str = Field(default='#DBEAFE', pattern=r'^#(?:DBEAFE|D1FAE5|EDE9FE|FCE7F3|FFEDD5|FEF3C7|CFFAFE|E2E8F0)$')
    description: str = Field(default='', max_length=500)
    active: bool = True
    version: int | None = None


class DoctorInput(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=1, max_length=20)
    department_id: int
    designation: str = Field(default='', max_length=150)
    contact: str = Field(default='', max_length=30)
    consultation_fee_paise: int | None = Field(default=None, strict=True, ge=0, le=100_000_000)
    followup_fee_paise: int | None = Field(default=None, strict=True, ge=0, le=100_000_000)
    active: bool = True
    version: int | None = None


def save_master(db, table, body, user, rid=None):
    values = body.model_dump(exclude={'version'})
    if table == 'departments' and rid and 'color' not in body.model_fields_set:
        values.pop('color', None)
    if table == 'doctors' and rid:
        for field in ('consultation_fee_paise', 'followup_fee_paise'):
            if field not in body.model_fields_set:
                values.pop(field, None)
    if table == 'doctors' and not record(db, 'departments', values['department_id'])['active'] and values['active']:
        fail('Choose an active department.')
    if rid:
        old = record(db, table, rid)
        check_version(old, body.version)
        db.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in values)},version=version+1 WHERE id=?", (*values.values(), rid))
    else:
        rid = db.execute(f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})", list(values.values())).lastrowid
    audit(db, user, 'Updated' if body.version else 'Created', table, rid, dump(values))
    return record(db, table, rid)


@app.post('/api/departments')
def create_department(body: DepartmentInput, user=Depends(master), db=Depends(database)):
    return save_master(db, 'departments', body, user)


@app.patch('/api/departments/{rid}')
def edit_department(rid: int, body: DepartmentInput, user=Depends(master), db=Depends(database)):
    return save_master(db, 'departments', body, user, rid)


@app.post('/api/doctors')
def create_doctor(body: DoctorInput, user=Depends(master), db=Depends(database)):
    return save_master(db, 'doctors', body, user)


@app.patch('/api/doctors/{rid}')
def edit_doctor(rid: int, body: DoctorInput, user=Depends(master), db=Depends(database)):
    return save_master(db, 'doctors', body, user, rid)


class BillingChargeInput(StrictModel):
    name: str = Field(min_length=2, max_length=200)
    price_paise: int = Field(strict=True, ge=1, le=100_000_000)
    active: bool = True
    version: int | None = None


@app.post('/api/billing-charges')
def add_billing_charge(body: BillingChargeInput, user=Depends(master), db=Depends(database)):
    return save_master(db, 'billing_charges', body, user)


@app.patch('/api/billing-charges/{rid}')
def edit_billing_charge(rid: int, body: BillingChargeInput, user=Depends(master), db=Depends(database)):
    return save_master(db, 'billing_charges', body, user, rid)


class LookupInput(StrictModel):
    kind: str
    name: str = Field(min_length=1, max_length=100)
    active: bool = True
    version: int | None = None


@app.post('/api/lookups')
def add_lookup(body: LookupInput, user=Depends(master), db=Depends(database)):
    if body.kind not in ['visit_type', 'complaint', 'referral', 'cancel_reason', 'reschedule_reason', 'contact_outcome']:
        fail('Invalid list type.')
    return save_master(db, 'lookups', body, user)


@app.patch('/api/lookups/{rid}')
def edit_lookup(rid: int, body: LookupInput, user=Depends(master), db=Depends(database)):
    old = record(db, 'lookups', rid)
    if body.kind != old['kind']:
        fail('List type cannot be changed.')
    if old['kind'] == 'visit_type' and old['name'] in ('New', 'Follow-up') and (body.name != old['name'] or not body.active):
        fail('New and Follow-up are required visit types.')
    return save_master(db, 'lookups', body, user, rid)


class StaffInput(Credentials):
    name: str = Field(min_length=2, max_length=100)


@app.post('/api/staff')
def create_staff(body: StaffInput, user=Depends(master), db=Depends(database)):
    if len(body.password) < 12:
        fail('Temporary password must contain at least 12 characters.')
    uid = db.execute("INSERT INTO users(username,name,role,password,must_change,created_at) VALUES(?,?,'Admin',?,1,?)", (body.username, body.name, password_hash(body.password), now())).lastrowid
    audit(db, user, 'Created Admin account', 'user', uid)
    return public_user(record(db, 'users', uid))


class StaffUpdate(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    active: bool
    version: int
    new_password: str = Field(default='', max_length=128)


@app.patch('/api/staff/{uid}')
def update_staff(uid: int, body: StaffUpdate, user=Depends(master), db=Depends(database)):
    old = record(db, 'users', uid)
    check_version(old, body.version)
    if old['role'] == 'Master' and (not body.active or body.new_password):
        fail('The sole Master cannot be deactivated. Change your password through your account.')
    db.execute('UPDATE users SET name=?,active=?,version=version+1 WHERE id=?', (body.name, body.active, uid))
    if body.new_password:
        if len(body.new_password) < 12:
            fail('Temporary password must contain at least 12 characters.')
        db.execute('UPDATE users SET password=?,must_change=1 WHERE id=?', (password_hash(body.new_password), uid))
    if not body.active or body.new_password:
        db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
    audit(db, user, 'Updated staff access', 'user', uid, 'Password reset' if body.new_password else 'Account details/access updated')
    return public_user(record(db, 'users', uid))


class SettingsInput(StrictModel):
    hospital_name: str = Field(min_length=2, max_length=120)
    address: str = Field(default='', max_length=500)
    phone: str = Field(default='', max_length=30)
    timezone: str = 'Asia/Kolkata'
    transfer_policy: str = 'Unspecified'
    reminder_time: str = ''
    language: str = 'English'
    version: int


@app.patch('/api/settings')
def settings_save(body: SettingsInput, user=Depends(master), db=Depends(database)):
    old = get_settings(db)
    check_version(old, body.version)
    try:
        ZoneInfo(body.timezone)
    except Exception:
        fail('Enter a valid IANA timezone.')
    if body.transfer_policy not in ['Unspecified', 'Next token', 'Preserve if available']:
        fail('Choose a valid transfer policy.')
    if body.reminder_time and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', body.reminder_time):
        fail('Reminder time must use HH:MM.')
    if body.language != 'English':
        fail('Only English is currently implemented.')
    if old['timezone'] != body.timezone and db.execute('SELECT 1 FROM visits UNION SELECT 1 FROM followups LIMIT 1').fetchone():
        fail('Timezone cannot be changed after operational records exist without a planned migration.')
    db.execute('UPDATE settings SET data=?,version=version+1 WHERE id=1', (dump(body.model_dump(exclude={'version'})),))
    audit(db, user, 'Updated hospital settings', 'settings', 1, dump({'previous': old}))
    return get_settings(db)


@app.get('/api/audit')
def audits(page: int = 1, q: str = '', user=Depends(master), db=Depends(database)):
    where = ' WHERE (a.action LIKE ? OR a.entity LIKE ? OR u.name LIKE ?)'
    args = (f'%{q[:100]}%',)*3
    base = ' FROM audits a LEFT JOIN users u ON u.id=a.actor'
    total = db.execute('SELECT count(*)'+base+where, args).fetchone()[0]
    rows = db.execute('SELECT a.*,u.name AS actor_name'+base+where+' ORDER BY a.id DESC LIMIT 30 OFFSET ?', (*args, (max(1,page)-1)*30)).fetchall()
    return {'items': [dict(x) for x in rows], 'total': total, 'page': page}


@app.get('/api/dashboard')
def dashboard(user=Depends(current_user), db=Depends(database)):
    day = today(db)
    statuses = {x['status']: x['n'] for x in db.execute('SELECT status,count(*) n FROM visits WHERE visit_date=? GROUP BY status', (day,))}
    queue = db.execute(VISIT_SELECT+" WHERE v.visit_date=? AND v.status IN ('Waiting','Called','Being Attended','On Hold') ORDER BY v.arrival_at LIMIT 7", (day,)).fetchall()
    follows = db.execute(FOLLOW_SELECT+" WHERE f.status='Scheduled' ORDER BY f.due_date,f.due_time LIMIT 6").fetchall()
    overdue = db.execute("SELECT count(*) FROM followups WHERE status='Scheduled' AND (due_date||'T'||CASE WHEN due_time='' THEN '23:59:59' ELSE due_time END)<?", (local_now(db).isoformat(timespec='seconds')[:19],)).fetchone()[0]
    trend = []
    for i in range(6, -1, -1):
        d = (local_now(db).date()-timedelta(days=i)).isoformat()
        trend.append({'date': d, 'visits': db.execute('SELECT count(*) FROM visits WHERE visit_date=?', (d,)).fetchone()[0]})
    zone = ZoneInfo(get_settings(db)['timezone'])
    registrations = sum(datetime.fromisoformat(x[0]).astimezone(zone).date().isoformat() == day for x in db.execute('SELECT created_at FROM patients WHERE merged_into IS NULL'))
    return {'date': day, 'registrations': registrations,
            'total_visits': sum(statuses.values()), 'statuses': statuses, 'overdue': overdue,
            'followups_today': db.execute("SELECT count(*) FROM followups WHERE due_date=? AND status='Scheduled'", (day,)).fetchone()[0],
            'patients': db.execute('SELECT count(*) FROM patients WHERE merged_into IS NULL').fetchone()[0],
            'queue': [visit_json(x) for x in queue], 'followups': [dict(x) for x in follows], 'trend': trend,
            'departments': [dict(x) for x in db.execute('SELECT dep.name,count(*) count FROM visits v JOIN departments dep ON dep.id=v.department_id WHERE v.visit_date=? GROUP BY dep.id', (day,))]}


@app.get('/api/reports')
def reports(kind: str = 'visits', start: str = '', end: str = '', doctor_id: int = 0, department_id: int = 0,
            status: str = '', staff_id: int = 0, page: int = 1, user=Depends(current_user), db=Depends(database)):
    start, end = start or today(db), end or today(db)
    try:
        if date.fromisoformat(start) > date.fromisoformat(end):
            fail('Start date must not be after end date.')
    except ValueError:
        fail('Invalid report date range.')
    args = [start, end]
    if kind == 'registrations':
        rows = [patient_json(x) for x in db.execute('SELECT * FROM patients WHERE merged_into IS NULL ORDER BY id DESC')]
        zone = ZoneInfo(get_settings(db)['timezone'])
        rows = [x for x in rows if start <= datetime.fromisoformat(x['created_at']).astimezone(zone).date().isoformat() <= end and (not staff_id or x['created_by'] == staff_id)]
    elif kind in ['followups', 'contacts']:
        query = FOLLOW_SELECT+' WHERE f.due_date BETWEEN ? AND ?'
        for col, value in [('doctor_id', doctor_id), ('department_id', department_id), ('assigned_to', staff_id), ('status', status)]:
            if value:
                query += f' AND f.{col}=?'
                args.append(value)
        rows = [{**dict(x), 'overdue': follow_overdue(db, x)} for x in db.execute(query+' ORDER BY f.due_date DESC', args)]
        if kind == 'contacts':
            contacts = []
            # Contact reports use contact date rather than scheduled return date.
            zone = ZoneInfo(get_settings(db)['timezone'])
            query = '''SELECT c.*,u.name actor_name,f.patient_id,p.uhid,trim(p.first_name||' '||CASE WHEN p.middle_name='' THEN '' ELSE p.middle_name||' ' END||p.surname) patient_name,d.name doctor_name,dep.name department_name,
                       f.doctor_id,f.department_id FROM contacts c JOIN users u ON u.id=c.actor JOIN followups f ON f.id=c.followup_id
                       JOIN patients p ON p.id=f.patient_id JOIN doctors d ON d.id=f.doctor_id JOIN departments dep ON dep.id=f.department_id ORDER BY c.id DESC'''
            for x in db.execute(query):
                item = dict(x)
                day = datetime.fromisoformat(item['created_at']).astimezone(zone).date().isoformat()
                if start <= day <= end and (not doctor_id or item['doctor_id'] == doctor_id) and (not department_id or item['department_id'] == department_id) and (not staff_id or item['actor'] == staff_id) and (not status or item['outcome'] == status):
                    contacts.append(item)
            rows = contacts
    elif kind in ['visits', 'doctors', 'departments', 'statuses', 'types', 'waiting']:
        query = VISIT_SELECT+' WHERE v.visit_date BETWEEN ? AND ?'
        for col, value in [('doctor_id', doctor_id), ('department_id', department_id), ('created_by', staff_id), ('status', status)]:
            if value:
                query += f' AND v.{col}=?'
                args.append(value)
        rows = [visit_json(x) for x in db.execute(query+' ORDER BY v.id DESC', args)]
        if kind == 'waiting':
            for item in rows:
                started = db.execute("SELECT created_at FROM visit_events WHERE visit_id=? AND status='Being Attended' ORDER BY id LIMIT 1", (item['id'],)).fetchone()
                item['waiting_minutes'] = round((datetime.fromisoformat(started[0])-datetime.fromisoformat(item['arrival_at'])).total_seconds()/60, 1) if started else None
        elif kind in ['doctors', 'departments', 'statuses', 'types']:
            col = {'doctors': 'doctor_name', 'departments': 'department_name', 'statuses': 'status', 'types': 'visit_type'}[kind]
            groups = {}
            for item in rows:
                key = str(item['doctor_id']) if kind == 'doctors' else str(item['department_id']) if kind == 'departments' else item[col]
                if key not in groups:
                    groups[key] = {'name': item[col], 'visits': 0, 'patient_ids': set()}
                groups[key]['visits'] += 1
                groups[key]['patient_ids'].add(item['patient_id'])
            rows = [{'name': x['name'], 'visits': x['visits'], 'patients': len(x['patient_ids'])} for x in groups.values()]
    else:
        fail('Unknown report type.')
    total = len(rows)
    page = max(1, page)
    return {'items': rows[(page-1)*30:page*30], 'total': total, 'page': page, 'kind': kind, 'start': start, 'end': end}
