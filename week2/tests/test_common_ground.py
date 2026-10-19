from unittest.mock import patch
import pytest
from referee.store import Store
from referee.simple import SimplePlans
from referee.common_ground import analyse,Recommendation
from referee.codex import AgentError


def group(tmp_path):
    store=Store(tmp_path);plans=SimplePlans(store)
    owner,code=store.create_group('Private group','Private coordinator')
    plans.save_plan(owner,dict(zip='75201',date='2026-10-23',time='18:00',duration=120,budget=30,interests=['Food'],choices=['Pizza','Coffee']))
    friend=store.join(code,'Private friend')
    return plans,owner,friend


def answer(choice='choice-1'):
    return Recommendation(choice_id=choice,summary='Coffee is a shared choice.',reasons=['Both selected it.'],compromises=[],questions=['Check opening hours and cost.'])


def test_recommendation_is_grounded_private_and_does_not_finalize(tmp_path):
    plans,owner,friend=group(tmp_path)
    plans.respond(owner,'Can join',['Pizza','Coffee'],['Food'],'A quiet place',True)
    plans.respond(friend,'Can join',['Coffee'],['Coffee'],'A short walk',True)
    with patch('referee.common_ground.ask',return_value=answer()) as call:
        result=analyse(plans,owner)
    prompt=call.call_args.args[0]
    assert 'Private coordinator' not in prompt and 'Private friend' not in prompt
    assert owner not in prompt and friend not in prompt
    assert 'A quiet place' in prompt
    assert result['choice']=='Coffee'
    assert plans.plan(owner)['final_choice']==''
    with pytest.raises(ValueError,match='organizer'):analyse(plans,friend)


def test_missing_responses_or_consent_never_call_model(tmp_path):
    plans,owner,friend=group(tmp_path)
    with patch('referee.common_ground.ask') as call:
        with pytest.raises(ValueError,match='everyone'):analyse(plans,owner)
        plans.respond(owner,'Can join',['Coffee'],[],analysis_consent=True)
        plans.respond(friend,'Maybe',['Coffee'],[])
        with pytest.raises(ValueError,match='allow group analysis'):analyse(plans,owner)
        call.assert_not_called()


def test_unsupported_recommendation_rejected(tmp_path):
    plans,owner,friend=group(tmp_path)
    for key in [owner,friend]:plans.respond(key,'Can join',['Coffee'],[],analysis_consent=True)
    with patch('referee.common_ground.ask',return_value=answer('choice-0')):
        with pytest.raises(AgentError,match='unsupported'):analyse(plans,owner)


def test_no_common_choice_requests_clarification(tmp_path):
    plans,owner,friend=group(tmp_path)
    plans.respond(owner,'Can join',['Pizza'],[],analysis_consent=True)
    plans.respond(friend,'Can join',['Coffee'],[],analysis_consent=True)
    with patch('referee.common_ground.ask',return_value=answer('')):
        assert analyse(plans,owner)['choice']=='No shared choice yet'


def test_changes_during_analysis_discard_result(tmp_path):
    plans,owner,friend=group(tmp_path)
    for key in [owner,friend]:plans.respond(key,'Can join',['Coffee'],[],analysis_consent=True)
    def changed(*args):
        plans.respond(friend,'Cannot join',[],[])
        return answer()
    with patch('referee.common_ground.ask',side_effect=changed):
        with pytest.raises(ValueError,match='updated'):analyse(plans,owner)


def test_coordinator_can_request_and_view_recommendation(tmp_path):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    plans,owner,friend=group(tmp_path)
    for key in [owner,friend]:plans.respond(key,'Can join',['Coffee'],[],analysis_consent=True)
    appfile=Path(__file__).resolve().parents[1]/'streamlit_app.py'
    with patch('referee.ui.store',return_value=plans.store),patch('referee.common_ground.ask',return_value=answer()):
        app=AppTest.from_file(str(appfile))
        app.session_state['member_key']=owner
        app.session_state['page']='Your group'
        app.run()
        next(b for b in app.button if b.label=='Find our common ground').click().run()
        assert not app.exception and not app.error
        assert any(x.value=='Suggested choice: Coffee' for x in app.text)
        assert plans.plan(owner)['final_choice']==''
        plans.respond(friend,'Maybe',['Pizza'],[],analysis_consent=True)
        app.run()
        assert not any(x.value=='Suggested choice: Coffee' for x in app.text)
