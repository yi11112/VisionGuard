import json
import sqlite3
import uuid
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / 'visionguard.db'
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, payload TEXT NOT NULL,
              report TEXT, status TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
              payload TEXT NOT NULL, result TEXT, status TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_id TEXT, action TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL);
            ''')
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        return db
    def add(self, event):
        eid = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO events VALUES(?,?,NULL,?,?)', (eid, json.dumps(event, ensure_ascii=False), 'new', now()))
        self.audit(eid, 'created', {'source': event['source']})
        return self.get(eid)
    def get(self, eid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM events WHERE id=?', (eid,)).fetchone()
        if not row:
            return None
        return {'id': row['id'], **json.loads(row['payload']), 'status': row['status'],
                'created': row['created'], 'report': json.loads(row['report']) if row['report'] else None}
    def list(self):
        with self.connect() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM events ORDER BY created DESC LIMIT 200')]
        return [self.get(i) for i in ids]
    def claim_analysis(self, eid):
        with self.connect() as db:
            return db.execute("UPDATE events SET status='analyzing' WHERE id=? AND status IN ('new','error')", (eid,)).rowcount == 1
    def save_report(self, eid, report):
        with self.connect() as db:
            db.execute('UPDATE events SET status=?,report=? WHERE id=?', (report['status'], json.dumps(report, ensure_ascii=False), eid))
        self.audit(eid, 'analysis_completed', {'mode': report['mode'], 'risk': report['risk']})
    def fail(self, eid, detail):
        with self.connect() as db:
            db.execute("UPDATE events SET status='error' WHERE id=?", (eid,))
        self.audit(eid, 'analysis_failed', {'error': detail})
    def audit(self, eid, action, payload):
        with self.connect() as db:
            db.execute('INSERT INTO audit(event_id,action,payload,created) VALUES(?,?,?,?)',
                       (eid, action, json.dumps(payload, ensure_ascii=False), now()))
    def audits(self, eid):
        with self.connect() as db:
            return [dict(r) | {'payload': json.loads(r['payload'])} for r in db.execute('SELECT * FROM audit WHERE event_id=? ORDER BY id', (eid,))]
    def command(self, eid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM commands WHERE event_id=?', (eid,)).fetchone()
        if not row:
            return None
        return dict(row) | {'payload': json.loads(row['payload']), 'result': json.loads(row['result']) if row['result'] else None}
    def approve(self, eid, reviewer, approve):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status,report FROM events WHERE id=?', (eid,)).fetchone()
            if not row or row['status'] != 'awaiting_approval':
                return False
            report = json.loads(row['report'])
            if approve:
                cmd = dict(report['action'])
                cmd['command_id'] = uuid.uuid4().hex
                cmd['reviewer'] = reviewer
                db.execute('INSERT INTO commands VALUES(?,?,?,NULL,?,?)',
                           (cmd['command_id'], eid, json.dumps(cmd), 'dispatching', now()))
            db.execute('UPDATE events SET status=? WHERE id=?', ('dispatching' if approve else 'rejected', eid))
            db.execute('INSERT INTO audit(event_id,action,payload,created) VALUES(?,?,?,?)',
                       (eid, 'approved' if approve else 'rejected', json.dumps({'reviewer': reviewer}), now()))
        return True
    def complete_command(self, eid, result):
        status = result['status']
        with self.connect() as db:
            db.execute('UPDATE commands SET status=?,result=? WHERE event_id=?', (status, json.dumps(result), eid))
            db.execute('UPDATE events SET status=? WHERE id=?', (status, eid))
        self.audit(eid, 'device_result', result)
    def recover(self):
        # Never automatically resend a command after a crash: its delivery may be unknown.
        with self.connect() as db:
            db.execute("UPDATE events SET status='error' WHERE status='analyzing'")
            db.execute("UPDATE commands SET status='delivery_unknown' WHERE status='dispatching'")
            db.execute("UPDATE events SET status='delivery_unknown' WHERE status='dispatching'")

