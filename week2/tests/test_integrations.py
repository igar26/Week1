import threading
from unittest.mock import patch,MagicMock
import pytest
from referee.catalog import demo_profiles
from referee.models import Advocate,Coordinator
from referee.workflow import process_profiles,coordinate
from referee.providers import overpass,google_hours,safe_url,ProviderError,fetch
from referee.graph import Graph


def test_independent_workers_actually_run_in_parallel():
    barrier=threading.Barrier(4,timeout=10)
    ids=[];lock=threading.Lock()
    def fake(prompt,schema):
        with lock:ids.append(prompt)
        barrier.wait()
        pid=next(p.id for p in demo_profiles() if p.id in prompt)
        return Advocate(person_id=pid,summary='One person only',suggested_interests=['Food'],questions=[])
    with patch('referee.workflow.codex.ask',side_effect=fake):
        result=process_profiles(demo_profiles(),'Codex CLI')
    assert len(result)==4
    assert len(ids)==4
    assert [r['person_id'] for r in result]==[p.id for p in demo_profiles()]
    assert all(sum(p.name in prompt for p in demo_profiles())==1 for prompt in ids)


def test_ai_consent_required_and_demo_no_llm():
    profiles=demo_profiles();profiles[0].ai_consent=False
    with patch('referee.workflow.codex.ask') as ask:
        with pytest.raises(ValueError):process_profiles(profiles,'Codex CLI')
        assert len(process_profiles(profiles,'Demo rules'))==4
        ask.assert_not_called()


def test_overpass_keeps_unknown_price_and_provenance():
    payload={'elements':[{'type':'node','id':10,'lat':32.8,'lon':-96.8,'tags':{'name':'A real cafe','amenity':'cafe','opening_hours':'Mo-Su 10:00-20:00','diet:vegetarian':'yes'}}]}
    with patch('referee.providers.fetch',return_value=payload):places=overpass(32.8,-96.8)
    assert places[0].cost is None and not places[0].synthetic
    assert places[0].diets==['Vegetarian']
    assert places[0].source_url=='https://www.openstreetmap.org/node/10'
    assert google_hours([{'open':{'day':1,'hour':9},'close':{'day':1,'hour':22}}])=='Mo 09:00-22:00'
    assert safe_url('javascript:alert(1)')==''
    assert safe_url('https://example.org')=='https://example.org'


def test_neo4j_query_scopes_group_and_all_members():
    graph=Graph();graph.driver=MagicMock()
    record=MagicMock();record.data.return_value={'id':'place-1'}
    graph.driver.execute_query.return_value=([record],None,None)
    assert graph.candidate_ids('group-123')=={'place-1'}
    args,kwargs=graph.driver.execute_query.call_args
    assert 'all(person IN people' in args[0]
    assert '80467.2' in args[0]
    assert kwargs['parameters_']=={'gid':'group-123'}


def test_coordinator_receives_all_advocate_results():
    from referee.catalog import demo_places
    from referee.decision import rank_options,DALLAS_TZ
    from datetime import datetime
    profiles=demo_profiles()
    outputs=process_profiles(profiles,'Demo rules')
    options,_=rank_options(profiles,demo_places(),datetime(2026,10,18,17,tzinfo=DALLAS_TZ),120)
    with patch('referee.workflow.codex.ask',return_value=Coordinator(introduction='Your shared plan',option_notes=[])) as ask:
        assert coordinate(profiles,options,'Codex CLI',outputs)=='Your shared plan'
    prompt=ask.call_args.args[0]
    assert all(output['summary'] in prompt for output in outputs)
