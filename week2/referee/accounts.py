"""Google OIDC accounts for event creators; never collect provider passwords."""
import hashlib
import json
import secrets
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


def identity():
    if not getattr(st.user,'is_logged_in',False):return None
    claims=st.user.to_dict()
    if claims.get('iss') not in {'https://accounts.google.com','accounts.google.com'} or not claims.get('sub') or claims.get('email_verified') is not True:
        raise ValueError('Sign in with a verified Google account to create an event.')
    subject=hashlib.sha256(json.dumps(['https://accounts.google.com',claims['sub']]).encode()).hexdigest()
    return {'id':subject,'name':str(claims.get('name',''))[:60]}


def configured():
    try:
        auth=st.secrets.get('auth',{})
        return all(auth.get(k) and not str(auth[k]).startswith(('YOUR_','REPLACE_')) for k in ['redirect_uri','cookie_secret','client_id','client_secret']) and auth.get('server_metadata_url')=='https://accounts.google.com/.well-known/openid-configuration'
    except (StreamlitSecretNotFoundError,FileNotFoundError):return False


class Accounts:
    def __init__(self,store):
        self.store=store
        with store.db() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS account_members(account_id TEXT REFERENCES accounts(id),member_id TEXT UNIQUE REFERENCES members(id),PRIMARY KEY(account_id,member_id));''')

    def register(self,person):
        with self.store.db() as c:
            c.execute('INSERT INTO accounts VALUES(?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',(person['id'],person['name']))

    def link(self,person,key):
        member=self.store.member(key)
        self.register(person)
        with self.store.db() as c:
            existing=c.execute('SELECT account_id FROM account_members WHERE member_id=?',(member['id'],)).fetchone()
            if existing and existing[0]!=person['id']:raise ValueError('This membership belongs to another account.')
            c.execute('INSERT OR IGNORE INTO account_members VALUES(?,?)',(person['id'],member['id']))

    def groups(self,person):
        with self.store.db() as c:
            return [dict(r) for r in c.execute("SELECT g.id,g.name,m.id AS member_id FROM account_members a JOIN members m ON m.id=a.member_id JOIN groups g ON g.id=m.group_id WHERE a.account_id=? AND m.left_at='' ORDER BY g.rowid DESC",(person['id'],))]

    def open_group(self,person,member_id):
        from .store import digest
        key=secrets.token_urlsafe(24)
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            member=c.execute("SELECT m.id FROM members m JOIN account_members a ON a.member_id=m.id WHERE a.account_id=? AND m.id=? AND m.left_at=''",(person['id'],member_id)).fetchone()
            if not member:raise ValueError('This group is not available to your account.')
            c.execute('UPDATE members SET key_hash=? WHERE id=?',(digest(key),member_id))
        return key


def creator_access(store):
    person=identity()
    if not person:
        st.subheader('Create your account to start a meetup')
        st.write('Continue with Google to create your After Hours account and return to the events you create. Your Google password stays with Google.')
        ready=configured()
        if st.button('Create account / sign in with Google',type='primary',disabled=not ready):st.login()
        if not ready:st.info('Account sign-in needs a one-time setup by the app host. See Help → Connections & setup. You can still try the Dallas demo or join an invitation.')
        return None
    accounts=Accounts(store);accounts.register(person)
    st.caption('Account: '+(person['name'] or 'Google member'))
    groups=accounts.groups(person)
    if groups:
        with st.expander('Your saved meetups'):
            st.caption('Opening a saved meetup replaces its previous browser access session.')
            for group in groups:
                if st.button('Open '+group['name'],key='account_open_'+group['id']):
                    st.session_state.member_key=accounts.open_group(person,group['member_id']);st.rerun()
    return person


def sign_out_control():
    if getattr(st.user,'is_logged_in',False) and st.button('Sign out',key='account_sign_out',type='tertiary'):
        for key in list(st.session_state):del st.session_state[key]
        st.logout()
