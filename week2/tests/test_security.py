"""Security regression tests use synthetic data and never contact external services."""
import os
import stat
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch,Mock
import pytest
from langsmith.run_helpers import get_tracing_context
from referee.security import local_only,inline_photo,private_tracing
from referee.store import Store
from referee.catalog import demo_profiles
from referee.graph import Graph,GraphError
from referee.models import Advocate
from referee.codex import ask


@pytest.mark.parametrize('address',['0.0.0.0','::','192.168.1.5',None,'example.com'])
def test_public_binding_rejected(address):
    with pytest.raises(ValueError):local_only(address)
    local_only('127.0.0.1')


def test_private_permissions_existing_data_preserved_and_symlink_refused(tmp_path):
    root=tmp_path/'private'
    first=Store(root);key,_=first.create_group('Private','Someone')
    if os.name=='posix':
        root.chmod(0o755);first.path.chmod(0o644)
    resumed=Store(root)
    assert resumed.group(key)['name']=='Private'
    if os.name=='posix':
        assert stat.S_IMODE(root.stat().st_mode)==0o700
        assert stat.S_IMODE(resumed.path.stat().st_mode)==0o600
        assert stat.S_IMODE(resumed.photos_dir.stat().st_mode)==0o700
    linked=tmp_path/'linked';linked.symlink_to(root,target_is_directory=True)
    with pytest.raises(ValueError):Store(linked)


def test_private_key_rotation_revokes_old_access(tmp_path):
    store=Store(tmp_path)
    original,invite=store.create_group('Circle','Coordinator')
    replacement=store.rotate_member_key(original)
    with pytest.raises(ValueError):store.member(original)
    assert store.owner(replacement)['name']=='Coordinator'
    assert Store(tmp_path).owner(replacement)['name']=='Coordinator'


def test_expired_invitation_and_rotation(tmp_path):
    store=Store(tmp_path);owner,invite=store.create_group('Circle','Coordinator')
    with store.db() as c:c.execute('UPDATE groups SET invite_expires=?',((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),))
    with pytest.raises(ValueError,match='expired'):store.join(invite,'Friend')
    replacement=store.rotate_invitation(owner)
    assert store.member(store.join(replacement,'Friend'))['name']=='Friend'


def test_private_photo_has_no_shared_media_url_and_escapes_alt():
    markup=inline_photo(b'jpeg-test-bytes','" onerror="evil() <script>')
    assert 'src="data:image/jpeg;base64,' in markup
    assert '/media/' not in markup
    assert '<script>' not in markup
    assert 'alt="&quot;' in markup


def test_inherited_langsmith_tracing_is_disabled():
    @private_tracing
    def inspect():return get_tracing_context()['enabled']
    with patch.dict(os.environ,{'LANGSMITH_TRACING':'true','LANGCHAIN_TRACING_V2':'true'}):
        assert inspect() is False


def test_codex_tools_are_disabled_and_child_env_is_allowlisted():
    output=Advocate(person_id='p1',summary='Synthetic',suggested_interests=[],questions=[])
    def fake_run(command,**kwargs):
        assert 'shell_tool' in command and 'unified_exec' in command
        assert 'web_search="disabled"' in command
        assert 'read-only' in command
        assert 'shell' not in kwargs
        assert 'UNRELATED_SECRET' not in kwargs['env']
        assert 'TWILIO_AUTH_TOKEN' not in kwargs['env']
        assert 'LANGSMITH_API_KEY' not in kwargs['env']
        Path(command[command.index('--output-last-message')+1]).write_text(output.model_dump_json())
        return Mock(returncode=0)
    with patch.dict(os.environ,{'UNRELATED_SECRET':'fake','TWILIO_AUTH_TOKEN':'fake','LANGSMITH_API_KEY':'fake'}),patch('referee.codex.executable',return_value='/test/codex'),patch('referee.codex.subprocess.run',side_effect=fake_run):
        assert ask('Synthetic profile only',Advocate)==output


def test_graph_requires_each_person_consent_before_any_write():
    graph=Graph();graph.driver=Mock()
    profiles=demo_profiles();profiles[0].graph_consent=False
    with pytest.raises(GraphError,match='opt in'):graph.sync({'id':'group','name':'Circle'},profiles,[])
    graph.driver.execute_query.assert_not_called()
