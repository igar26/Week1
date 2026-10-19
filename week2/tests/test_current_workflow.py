from pathlib import Path
from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest
from referee.demo import create_outing_demo
from referee.simple import SimplePlans,budget_limit
from referee.store import Store

APP=Path(__file__).resolve().parents[1]/'streamlit_app.py'


def test_personal_budget_validation_and_tentative_limits(tmp_path):
    store=Store(tmp_path);owner,_,keys=create_outing_demo(store);plans=SimplePlans(store)
    assert budget_limit(plans.plan(owner),plans.responses(owner))==25
    row=next(r['response'] for r in plans.responses(owner) if r['id']==store.member(owner)['id'])
    for invalid in [-1,0,10,14.99,1001,True,float('nan')]:
        with pytest.raises(ValueError,match='budget'):
            plans.respond(owner,'Can join',row['choices'],row['interests'],budget=invalid)
    plans.respond(owner,'Can join',row['choices'],row['interests'],budget=15)
    assert budget_limit(plans.plan(owner),plans.responses(owner))==15


def test_pages_explain_current_flow_and_budget_survives_navigation(tmp_path):
    store=Store(tmp_path)
    with patch('referee.ui.store',return_value=store):
        app=AppTest.from_file(str(APP),default_timeout=30).run()
        next(b for b in app.button if b.label=='Try the Dallas demo').click().run()
        owner=app.session_state['member_key']
        next(n for n in app.number_input if n.label=='My activity budget per person ($)').set_value(15.75)
        next(b for b in app.button if b.label=='Save my response').click().run()
        assert not app.exception and not app.error
        plans=SimplePlans(store)
        assert budget_limit(plans.plan(owner),plans.responses(owner))==15.75
        assert any('Shared spending ceiling: $15.75/person' in c.value for c in app.caption)
        next(b for b in app.button if b.label=='Help').click().run()
        text=' '.join(x.value for x in app.markdown)
        assert 'event creators can return through their Google account once the host configures sign-in' in text
        assert 'Save your private return key' not in text
        assert 'lowest definite attendee budget' in text
        assert 'default experience does not run parallel advocates' in text
        next(b for b in app.button if b.label=='Your group').click().run()
        assert next(n for n in app.number_input if n.label=='My activity budget per person ($)').value==15.75
        assert not app.exception
