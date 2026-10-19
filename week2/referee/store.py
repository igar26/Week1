"""Local persistent groups and polls. Bearer membership keys are hashed at rest."""
import hashlib
import io
import json
import re
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from .models import Profile
from .security import private_directory,private_file

ROOT=Path(__file__).resolve().parents[1]


def uid():return uuid.uuid4().hex

def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def now():return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self,root=None):
        self.root=private_directory(Path(root or os.getenv('REFEREE_DATA_DIR') or ROOT/'data').expanduser())
        self.photos_dir=private_directory(self.root/'photos')
        for photo in self.photos_dir.glob('*.jpg'):private_file(photo)
        self.path=self.root/'referee.sqlite'
        private_file(self.path)
        with self.db() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS groups(id TEXT PRIMARY KEY,name TEXT,join_hash TEXT UNIQUE,owner TEXT,demo INTEGER);
            CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY,group_id TEXT REFERENCES groups(id),name TEXT,key_hash TEXT UNIQUE,profile TEXT);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,group_id TEXT REFERENCES groups(id),title TEXT,start TEXT,duration INTEGER,people TEXT,options TEXT,status TEXT,winner TEXT,created TEXT,booking TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS votes(session_id TEXT REFERENCES sessions(id),member_id TEXT REFERENCES members(id),place_id TEXT,value INTEGER CHECK(value BETWEEN 0 AND 2),PRIMARY KEY(session_id,member_id,place_id));
            CREATE TABLE IF NOT EXISTS confirmations(session_id TEXT REFERENCES sessions(id),member_id TEXT REFERENCES members(id),PRIMARY KEY(session_id,member_id));
            CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,group_id TEXT REFERENCES groups(id),session_id TEXT REFERENCES sessions(id),member_id TEXT REFERENCES members(id),caption TEXT,rating INTEGER,again INTEGER,created TEXT);
            CREATE TABLE IF NOT EXISTS photos(id TEXT PRIMARY KEY,memory_id TEXT REFERENCES memories(id) ON DELETE CASCADE,filename TEXT);
            CREATE TABLE IF NOT EXISTS simple_plans(group_id TEXT PRIMARY KEY REFERENCES groups(id),details TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS simple_responses(member_id TEXT PRIMARY KEY REFERENCES members(id),response TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sms_contacts(member_id TEXT PRIMARY KEY REFERENCES members(id),phone TEXT,opt_in INTEGER,updated TEXT);
            CREATE TABLE IF NOT EXISTS sms_outbox(session_id TEXT REFERENCES sessions(id),member_id TEXT REFERENCES members(id),phone_hash TEXT,status TEXT,sid TEXT DEFAULT '',error TEXT DEFAULT '',created TEXT,PRIMARY KEY(session_id,member_id),UNIQUE(session_id,phone_hash));
            ''')
            member_columns={r[1] for r in c.execute('PRAGMA table_info(members)')}
            if 'left_at' not in member_columns:c.execute("ALTER TABLE members ADD COLUMN left_at TEXT DEFAULT ''")
            columns={r[1] for r in c.execute('PRAGMA table_info(sessions)')}
            for name in ['booked_at','coordinator_approved_at','timezone']:
                if name not in columns:c.execute(f"ALTER TABLE sessions ADD COLUMN {name} TEXT DEFAULT ''")
            if 'kind' not in columns:c.execute("ALTER TABLE sessions ADD COLUMN kind TEXT DEFAULT 'advanced'")
            group_columns={r[1] for r in c.execute('PRAGMA table_info(groups)')}
            if 'invite_expires' not in group_columns:c.execute("ALTER TABLE groups ADD COLUMN invite_expires TEXT DEFAULT ''")
            c.execute("UPDATE groups SET invite_expires=? WHERE invite_expires=''",((datetime.now(timezone.utc)+timedelta(days=7)).isoformat(),))

    @contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=20)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback();raise
        finally:c.close()

    def member(self,key):
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{32}',key):raise ValueError('Invalid private rejoin key.')
        with self.db() as c:row=c.execute("SELECT * FROM members WHERE key_hash=? AND left_at=''",(digest(key),)).fetchone()
        if not row:raise ValueError('Invalid member key. Join a group or use your saved private rejoin key.')
        return dict(row)

    def group(self,key):
        member=self.member(key)
        with self.db() as c:return dict(c.execute('SELECT id,name,owner,demo,invite_expires FROM groups WHERE id=?',(member['group_id'],)).fetchone())

    def create_group(self,name,person):
        name=name.strip();person=person.strip()
        if not name or not person:raise ValueError('Enter a group name and your name.')
        if len(name)>80 or len(person)>60:raise ValueError('Please use a shorter name.')
        group_id,member_id,join,key=uid(),uid(),secrets.token_urlsafe(12),secrets.token_urlsafe(24)
        with self.db() as c:
            c.execute('INSERT INTO groups(id,name,join_hash,owner,demo,invite_expires) VALUES(?,?,?,?,0,?)',(group_id,name,digest(join),member_id,(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()))
            c.execute('INSERT INTO members(id,group_id,name,key_hash,profile) VALUES(?,?,?,?,?)',(member_id,group_id,person,digest(key),'{}'))
        return key,join

    def rotate_member_key(self,key):
        member=self.member(key)
        replacement=secrets.token_urlsafe(24)
        with self.db() as c:c.execute('UPDATE members SET key_hash=? WHERE id=?',(digest(replacement),member['id']))
        return replacement


    def rotate_invitation(self,key):
        member=self.owner(key)
        code=secrets.token_urlsafe(12)
        with self.db() as c:
            c.execute('UPDATE groups SET join_hash=?,invite_expires=? WHERE id=?',(digest(code),(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(),member['group_id']))
        return code


    def join(self,join_code,name):
        name=name.strip()
        if not name or len(name)>60:raise ValueError('Enter your name, up to 60 characters.')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            g=c.execute('SELECT * FROM groups WHERE join_hash=?',(digest(join_code.strip()),)).fetchone()
            if not g:raise ValueError('Group invitation not found.')
            if datetime.fromisoformat(g['invite_expires'])<=datetime.now(timezone.utc):raise ValueError('This invitation expired. Ask the coordinator for a new code.')
            if c.execute("SELECT 1 FROM sessions WHERE group_id=? AND status IN ('voting','confirming','finalized')",(g['id'],)).fetchone():
                raise ValueError('The current plan is frozen. Ask the organizer to start a new planning round before joining.')
            simple=c.execute('SELECT details FROM simple_plans WHERE group_id=?',(g['id'],)).fetchone()
            if simple and json.loads(simple[0]).get('final_choice'):
                raise ValueError('This outing is finalized. Ask the coordinator for the next group outing.')
            if c.execute("SELECT 1 FROM members WHERE group_id=? AND lower(name)=lower(?) AND left_at=''",(g['id'],name)).fetchone():
                raise ValueError('That name already belongs to a member. Use your private rejoin key or a distinct name.')
            key=secrets.token_urlsafe(24)
            c.execute('INSERT INTO members(id,group_id,name,key_hash,profile) VALUES(?,?,?,?,?)',(uid(),g['id'],name,digest(key),'{}'))
        return key

    def roster(self,key):
        m=self.member(key)
        with self.db() as c:return [dict(r) for r in c.execute("SELECT id,name,profile FROM members WHERE group_id=? AND left_at='' ORDER BY rowid",(m['group_id'],))]

    def profiles(self,key):
        return [Profile.model_validate_json(r['profile']) for r in self.roster(key) if r['profile']!='{}']

    def save_profile(self,key,profile):
        m=self.member(key)
        if profile.id!=m['id']:raise ValueError('You can only edit your own profile.')
        with self.db() as c:
            if c.execute("SELECT 1 FROM sessions WHERE group_id=? AND status IN ('voting','confirming','finalized')",(m['group_id'],)).fetchone():
                raise ValueError('The plan is frozen. Ask the organizer to start a new round before editing profiles.')
            c.execute('UPDATE members SET profile=? WHERE id=?',(profile.model_dump_json(),m['id']))

    def session(self,key):
        m=self.member(key)
        with self.db() as c:r=c.execute("SELECT * FROM sessions WHERE group_id=? AND status!='archived' ORDER BY rowid DESC LIMIT 1",(m['group_id'],)).fetchone()
        return self.decode_session(r) if r else None

    def decode_session(self,row):
        data=dict(row)
        for k in ['people','options']:data[k]=json.loads(data[k])
        return data

    def get_session(self,key,session_id):
        m=self.member(key)
        with self.db() as c:r=c.execute('SELECT * FROM sessions WHERE id=? AND group_id=?',(session_id,m['group_id'])).fetchone()
        if not r:raise ValueError('This plan does not belong to your group.')
        return self.decode_session(r)

    def owner(self,key):
        m=self.member(key)
        if self.group(key)['owner']!=m['id']:raise ValueError('Only the organizer can change the planning round.')
        return m

    def reset_round(self,key):
        m=self.owner(key)
        with self.db() as c:c.execute("UPDATE sessions SET status='archived' WHERE group_id=? AND status IN ('voting','confirming','finalized')",(m['group_id'],))

    def start_poll(self,key,title,start,duration,proposals,timezone_name=None):
        m=self.owner(key);people=self.profiles(key)
        if len(people)!=len(self.roster(key)) or not all(p.reviewed for p in people):raise ValueError('Everyone must save a reviewed profile.')
        if not proposals:raise ValueError('No feasible options to vote on.')
        if self.session(key) and self.session(key)['status'] in {'voting','confirming','finalized'}:raise ValueError('A poll is already active. Start a new round first.')
        from zoneinfo import ZoneInfo
        timezone_name=timezone_name or getattr(start.tzinfo,'key','America/Chicago')
        ZoneInfo(timezone_name)
        session_id=uid()
        with self.db() as c:
            c.execute('INSERT INTO sessions(id,group_id,title,start,duration,people,options,status,winner,created) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (session_id,m['group_id'],title.strip()[:100] or 'Our next adventure',start.isoformat(),duration,
                 json.dumps([p.model_dump() for p in people]),json.dumps([p.model_dump() for p in proposals]),'voting','',now()))
            c.execute('UPDATE sessions SET timezone=? WHERE id=?',(timezone_name,session_id))
        return session_id

    def vote(self,key,session_id,ballot):
        m=self.member(key);s=self.get_session(key,session_id)
        if s['status']!='voting':raise ValueError('This poll is closed.')
        if m['id'] not in {p['id'] for p in s['people']}:raise ValueError('You are not a participant in this poll.')
        if set(ballot)!={p['place']['id'] for p in s['options']} or any(v not in [0,1,2] for v in ballot.values()):raise ValueError('Vote once on every option.')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT status FROM sessions WHERE id=?',(session_id,)).fetchone()[0]!='voting':raise ValueError('This poll is closed.')
            for place_id,value in ballot.items():c.execute('INSERT OR REPLACE INTO votes VALUES(?,?,?,?)',(session_id,m['id'],place_id,value))

    def ballots(self,key,session_id):
        self.get_session(key,session_id)
        with self.db() as c:return [dict(r) for r in c.execute('SELECT * FROM votes WHERE session_id=?',(session_id,))]

    def close_poll(self,key,session_id):
        self.owner(key);s=self.get_session(key,session_id)
        if s['status']!='voting':raise ValueError('This poll is already closed.')
        rows=self.ballots(key,session_id)
        if len(rows)!=len(s['people'])*len(s['options']):raise ValueError('Wait for every participant to vote on every option.')
        eligible=[]
        for rank,p in enumerate(s['options']):
            values=[r['value'] for r in rows if r['place_id']==p['place']['id']]
            if min(values)>0 and max(values)==2:eligible.append((values.count(2),-rank,p['place']['id']))
        if not eligible:raise ValueError('No consensus: every option has a “Can’t join” or no firm yes. Start a new round.')
        winner=max(eligible)[2]
        with self.db() as c:c.execute("UPDATE sessions SET status='confirming',winner=? WHERE id=?",(winner,session_id))
        return winner

    def confirm(self,key,session_id):
        m=self.member(key);s=self.get_session(key,session_id)
        if s['status']!='confirming':raise ValueError('This plan is not waiting for confirmation.')
        if m['id'] not in {p['id'] for p in s['people']}:raise ValueError('You are not part of this plan.')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT status FROM sessions WHERE id=?',(session_id,)).fetchone()[0]!='confirming':raise ValueError('This plan is no longer waiting for confirmation.')
            c.execute('INSERT OR IGNORE INTO confirmations VALUES(?,?)',(session_id,m['id']))
            count=c.execute('SELECT COUNT(*) FROM confirmations WHERE session_id=?',(session_id,)).fetchone()[0]
            if count==len(s['people']):c.execute("UPDATE sessions SET status='finalized' WHERE id=?",(session_id,))

    def confirmations(self,key,session_id):
        self.get_session(key,session_id)
        with self.db() as c:return [r[0] for r in c.execute('SELECT member_id FROM confirmations WHERE session_id=?',(session_id,))]

    def booking_note(self,key,session_id,note):
        self.owner(key);s=self.get_session(key,session_id)
        if s['status']!='finalized':raise ValueError('Everyone must confirm the outing first.')
        if s['booked_at']:raise ValueError('A confirmed booking reference is frozen. Start a new planning round if the booking changes.')
        with self.db() as c:c.execute('UPDATE sessions SET booking=? WHERE id=?',(note[:300],session_id))

    def complete(self,key,session_id):
        self.owner(key);s=self.get_session(key,session_id)
        if s['status']!='finalized':raise ValueError('Finalize the group plan first.')
        with self.db() as c:c.execute("UPDATE sessions SET status='completed' WHERE id=?",(session_id,))

    def add_past_adventure(self,key,title,day):
        member=self.owner(key)
        from datetime import date
        from zoneinfo import ZoneInfo
        title=title.strip()
        if not title or len(title)>100:raise ValueError('Enter an adventure title up to 100 characters.')
        day=date.fromisoformat(day)
        if day>datetime.now(ZoneInfo('America/Chicago')).date() and not self.group(key)['demo']:
            raise ValueError('Choose the date of an outing that has already happened.')
        session_id=uid()
        people=[{'id':r['id'],'name':r['name']} for r in self.roster(key)]
        with self.db() as c:
            c.execute('INSERT INTO sessions(id,group_id,title,start,duration,people,options,status,winner,created,kind) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (session_id,member['group_id'],title,day.isoformat(),0,json.dumps(people),'[]','completed','',now(),'simple'))
        return session_id

    def add_memory(self,key,session_id,caption,rating,again,uploads):
        m=self.member(key);s=self.get_session(key,session_id)
        if s['status']!='completed':raise ValueError('Mark the outing completed before adding memories.')
        if not 1<=rating<=5 or len(caption)>1500 or len(uploads)>8:raise ValueError('Use a 1–5 rating, a short caption, and up to 8 photos.')
        processed=[]
        for content in uploads:
            if len(content)>12*1024*1024:raise ValueError('Each image must be under 12 MB.')
            try:
                with Image.open(io.BytesIO(content)) as image:
                    if image.width*image.height>25_000_000:raise ValueError('Photo exceeds 25 megapixels.')
                    clean=ImageOps.exif_transpose(image).convert('RGB')
                    clean.thumbnail((2000,2000))
                    buffer=io.BytesIO();clean.save(buffer,format='JPEG',quality=88)
                    processed.append(buffer.getvalue())
            except (UnidentifiedImageError,OSError,Image.DecompressionBombError):raise ValueError('Upload a valid JPEG, PNG or WebP photo.') from None
        memory_id=uid();created=[]
        try:
            with self.db() as c:
                c.execute('BEGIN IMMEDIATE')
                if not c.execute("SELECT 1 FROM members WHERE id=? AND group_id=? AND left_at=''",(m['id'],m['group_id'])).fetchone():raise ValueError('Your group access has ended.')
                c.execute('INSERT INTO memories VALUES(?,?,?,?,?,?,?,?)',(memory_id,m['group_id'],session_id,m['id'],caption,rating,int(again),now()))
                for content in processed:
                    photo_id=uid();filename=photo_id+'.jpg';path=self.photos_dir/filename
                    private_file(path,content);created.append(path)
                    c.execute('INSERT INTO photos VALUES(?,?,?)',(photo_id,memory_id,filename))
        except Exception:
            for path in created:path.unlink(missing_ok=True)
            raise
        return memory_id

    def memories(self,key):
        m=self.member(key)
        with self.db() as c:
            rows=[dict(r) for r in c.execute('SELECT memories.*,members.name,sessions.title,sessions.start FROM memories JOIN members ON memories.member_id=members.id JOIN sessions ON memories.session_id=sessions.id WHERE memories.group_id=? ORDER BY memories.created DESC',(m['group_id'],))]
            for r in rows:r['photos']=[dict(p) for p in c.execute('SELECT * FROM photos WHERE memory_id=?',(r['id'],))]
        return rows

    def photo_bytes(self,key,photo_id):
        m=self.member(key)
        with self.db() as c:r=c.execute('SELECT photos.filename FROM photos JOIN memories ON memories.id=photos.memory_id WHERE photos.id=? AND memories.group_id=?',(photo_id,m['group_id'])).fetchone()
        if not r:raise ValueError('Photo not available to your group.')
        return (self.photos_dir/r['filename']).read_bytes()

    def delete_memory(self,key,memory_id):
        m=self.member(key)
        with self.db() as c:
            row=c.execute('SELECT * FROM memories WHERE id=? AND group_id=?',(memory_id,m['group_id'])).fetchone()
            if not row or row['member_id']!=m['id']:raise ValueError('Only the uploader can delete this memory.')
            paths=[self.photos_dir/r[0] for r in c.execute('SELECT filename FROM photos WHERE memory_id=?',(memory_id,))]
            c.execute('DELETE FROM memories WHERE id=?',(memory_id,))
        for path in paths:path.unlink(missing_ok=True)

    def leave_group(self,key,successor=None,delete_memories=False):
        member=self.member(key)
        if type(delete_memories) is not bool:raise ValueError('Choose whether to delete your shared memories.')
        paths=[]
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            active=c.execute("SELECT * FROM members WHERE id=? AND left_at=''",(member['id'],)).fetchone()
            if not active:raise ValueError('You have already left this group.')
            group=c.execute('SELECT * FROM groups WHERE id=?',(member['group_id'],)).fetchone()
            others=c.execute("SELECT id FROM members WHERE group_id=? AND id!=? AND left_at='' ORDER BY rowid",(member['group_id'],member['id'])).fetchall()
            if group['owner']==member['id'] and others:
                if successor not in {r['id'] for r in others}:raise ValueError('Choose another active member to become coordinator before leaving.')
                c.execute('UPDATE groups SET owner=? WHERE id=?',(successor,member['group_id']))
            if not others:
                c.execute('UPDATE groups SET join_hash=?,invite_expires=? WHERE id=?',(digest(secrets.token_urlsafe(12)),now(),member['group_id']))
            if delete_memories:
                paths=[self.photos_dir/r[0] for r in c.execute('SELECT photos.filename FROM photos JOIN memories ON memories.id=photos.memory_id WHERE memories.group_id=? AND memories.member_id=?',(member['group_id'],member['id']))]
                c.execute('DELETE FROM memories WHERE group_id=? AND member_id=?',(member['group_id'],member['id']))
            c.execute("UPDATE members SET left_at=?,key_hash=?,profile='{}' WHERE id=?",(now(),digest(secrets.token_urlsafe(24)),member['id']))
            c.execute('DELETE FROM sms_contacts WHERE member_id=?',(member['id'],))
            c.execute('DELETE FROM simple_responses WHERE member_id=?',(member['id'],))
            # End older in-progress polls whose frozen roster included the departing member.
            c.execute("UPDATE sessions SET status='archived' WHERE group_id=? AND status IN ('voting','confirming','finalized')",(member['group_id'],))
            keep_agreed_venue=False
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='venue_rounds'").fetchone():
                record=c.execute('SELECT details FROM venue_rounds WHERE group_id=?',(member['group_id'],)).fetchone()
                if record:
                    round=json.loads(record[0])
                    c.execute('DELETE FROM venue_ballots WHERE group_id=? AND member_id=?',(member['group_id'],member['id']))
                    if round['status']=='finalized':
                        keep_agreed_venue=True
                        from .meetup import preference_signature
                        plan=json.loads(c.execute('SELECT details FROM simple_plans WHERE group_id=?',(member['group_id'],)).fetchone()[0])
                        rows=[dict(id=r['id'],name=r['name'],response=json.loads(r['response']) if r['response'] else None) for r in c.execute("SELECT m.id,m.name,r.response FROM members m LEFT JOIN simple_responses r ON r.member_id=m.id WHERE m.group_id=? AND m.left_at='' ORDER BY m.rowid",(member['group_id'],))]
                        round['baseline']=preference_signature(plan,rows)
                        c.execute('UPDATE venue_rounds SET details=? WHERE group_id=?',(json.dumps(round),member['group_id']))
                    else:
                        c.execute('DELETE FROM venue_ballots WHERE group_id=?',(member['group_id'],))
                        c.execute('DELETE FROM venue_rounds WHERE group_id=?',(member['group_id'],))
            if not keep_agreed_venue:
                record=c.execute('SELECT details FROM simple_plans WHERE group_id=?',(member['group_id'],)).fetchone()
                if record:
                    plan=json.loads(record[0]);plan['final_choice']=''
                    c.execute('UPDATE simple_plans SET details=? WHERE group_id=?',(json.dumps(plan),member['group_id']))
        for path in paths:path.unlink(missing_ok=True)

    def create_demo(self):
        from .catalog import demo_profiles
        profiles=demo_profiles()
        key,join=self.create_group('The weekend people',profiles[0].name)
        first=self.member(key);profiles[0].id=first['id'];self.save_profile(key,profiles[0])
        keys={first['id']:key}
        for p in profiles[1:]:
            k=self.join(join,p.name);p.id=self.member(k)['id'];self.save_profile(k,p);keys[p.id]=k
        with self.db() as c:c.execute('UPDATE groups SET demo=1 WHERE id=?',(first['group_id'],))
        return key,join,keys

    def completed_sessions(self,key):
        m=self.member(key)
        with self.db() as c:return [self.decode_session(r) for r in c.execute("SELECT * FROM sessions WHERE group_id=? AND status='completed' ORDER BY rowid DESC",(m['group_id'],))]


    def sms_contact(self,key):
        member=self.member(key)
        with self.db() as c:
            row=c.execute('SELECT phone,opt_in,updated FROM sms_contacts WHERE member_id=?',(member['id'],)).fetchone()
        return dict(row) if row else {'phone':'','opt_in':0,'updated':''}

    def save_sms_contact(self,key,phone,opt_in):
        member=self.member(key);phone=phone.strip()
        if phone and not re.fullmatch(r'\+[1-9]\d{7,14}',phone):raise ValueError('Use an international phone number, such as +12125550123.')
        if opt_in and not phone:raise ValueError('Add your phone number before opting in.')
        with self.db() as c:c.execute('INSERT OR REPLACE INTO sms_contacts VALUES(?,?,?,?)',(member['id'],phone,int(opt_in),now()))

    def confirm_booking(self,key,session_id,reference,coordinator_approved):
        self.owner(key);s=self.get_session(key,session_id)
        if s['status']!='finalized' or not reference.strip() or not coordinator_approved:
            raise ValueError('Finalize the group plan, enter a booking reference, and approve it as coordinator first.')
        if self.group(key)['demo'] or any(p['place']['synthetic'] for p in s['options'] if p['place']['id']==s['winner']):
            raise ValueError('Demo venues cannot create real booking notifications.')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT status FROM sessions WHERE id=?',(session_id,)).fetchone()[0]!='finalized':raise ValueError('The plan is no longer finalized.')
            booked=c.execute('SELECT booked_at FROM sessions WHERE id=?',(session_id,)).fetchone()[0]
            if booked:return # Immutable once notifications may have been submitted.
            c.execute('UPDATE sessions SET booking=?,booked_at=?,coordinator_approved_at=? WHERE id=?',(reference.strip()[:300],now(),now(),session_id))

    def sms_recipients(self,key,session_id):
        self.owner(key);s=self.get_session(key,session_id)
        with self.db() as c:
            result=[]
            for person in s['people']:
                row=c.execute('SELECT phone,opt_in FROM sms_contacts WHERE member_id=?',(person['id'],)).fetchone()
                result.append({'member_id':person['id'],'name':person['name'],'phone':row['phone'] if row else '', 'opt_in':bool(row and row['opt_in'])})
        return result

    def claim_sms(self,key,session_id,member_id):
        self.owner(key);s=self.get_session(key,session_id)
        if s['status']!='finalized' or not s['booked_at'] or not s['coordinator_approved_at']:raise ValueError('Booking and coordinator approval are required before texting.')
        if self.group(key)['demo']:raise ValueError('SMS is disabled for demo groups.')
        if member_id not in {p['id'] for p in s['people']}:raise ValueError('Recipient is not part of this plan.')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            current=c.execute('SELECT status,booked_at,coordinator_approved_at FROM sessions WHERE id=?',(session_id,)).fetchone()
            if current['status']!='finalized' or not current['booked_at'] or not current['coordinator_approved_at']:raise ValueError('The booking is no longer ready for notification.')
            row=c.execute('SELECT phone,opt_in FROM sms_contacts WHERE member_id=?',(member_id,)).fetchone()
            if not row or not row['opt_in'] or not row['phone']:return None
            cursor=c.execute("INSERT OR IGNORE INTO sms_outbox(session_id,member_id,phone_hash,status,created) VALUES(?,?,?,'sending',?)",(session_id,member_id,digest(row['phone']),now()))
            return row['phone'] if cursor.rowcount else None

    def finish_sms(self,key,session_id,member_id,status,sid='',error=''):
        self.owner(key);self.get_session(key,session_id)
        with self.db() as c:c.execute('UPDATE sms_outbox SET status=?,sid=?,error=? WHERE session_id=? AND member_id=?',(status,sid,error,session_id,member_id))

    def sms_statuses(self,key,session_id):
        self.owner(key);self.get_session(key,session_id)
        with self.db() as c:return [dict(r) for r in c.execute('SELECT sms_outbox.member_id,members.name,sms_outbox.status,sms_outbox.sid,sms_outbox.error FROM sms_outbox JOIN members ON members.id=sms_outbox.member_id WHERE session_id=?',(session_id,))]
