from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import pytest
from streamlit.testing.v1 import AppTest
from referee.accounts import Accounts,identity
from referee.store import Store


def test_account_group_restore_is_scoped_and_departure_revokes_it(tmp_path):
    store=Store(tmp_path);accounts=Accounts(store)
    alice={'id':'google-subject-alice','name':'Alice'}
    bob={'id':'google-subject-bob','name':'Bob'}
    key,_=store.create_group('Meetup','Alice');accounts.link(alice,key)
    member=store.member(key)['id']
    assert len(accounts.groups(alice))==1
    assert not accounts.groups(bob)
    with pytest.raises(ValueError):accounts.open_group(bob,member)
    with pytest.raises(ValueError):accounts.link(bob,key)
    restored=Accounts(Store(tmp_path)).open_group(alice,member)
    assert store.member(restored)['id']==member
    with pytest.raises(ValueError):store.member(key)
    store.leave_group(restored)
    assert not accounts.groups(alice)
    with pytest.raises(ValueError):accounts.open_group(alice,member)


def test_identity_requires_verified_google_subject_and_ignores_email_as_identity():
    claims={'iss':'https://accounts.google.com','sub':'stable-subject','email_verified':True,'name':'Alex','email':'first@example.com'}
    with patch('referee.accounts.st.user',SimpleNamespace(is_logged_in=True,to_dict=lambda:claims)):
        before=identity()
        claims['email']='changed@example.com'
        assert identity()['id']==before['id']
        claims['email_verified']=False
        with pytest.raises(ValueError):identity()
        claims['email_verified']=True;claims['iss']='https://untrusted.example'
        with pytest.raises(ValueError):identity()


def test_no_event_creation_until_account_sign_in_but_invitation_join_remains(tmp_path):
    store=Store(tmp_path)
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.ui.store',return_value=store),patch('referee.accounts.configured',return_value=False):
        app=AppTest.from_file(str(appfile)).run()
        next(b for b in app.button if b.label=='Plan something good').click().run()
        assert not app.exception
        assert next(b for b in app.button if b.label=='Create account / sign in with Google').disabled
        assert not any(b.label=='Create group' for b in app.button)
        assert any(b.label=='Join group' for b in app.button)
        assert any('one-time setup' in i.value for i in app.info)
