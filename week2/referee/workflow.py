"""Dynamic parallel personal advocates, then one coordinator with approved data only."""
import operator
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langsmith import traceable
from .models import Profile, Advocate, Coordinator
from . import codex
from .security import private_tracing


class AdvocateState(TypedDict):
    profiles: list[dict]
    mode: str
    outputs: Annotated[list[dict],operator.add]


def dispatch(state):
    return [Send('advocate',{'profile':p,'mode':state['mode']}) for p in state['profiles']]



def advocate(state):
    p=Profile.model_validate(state['profile'])
    if state['mode']=='Codex CLI':
        safe={k:v for k,v in p.model_dump().items() if k not in {'lat','lon'}}
        output=codex.ask(f'You advocate for one person only. Summarize preferences, suggest interests from Food,Coffee,Outdoors,Art,Music,Games,Museums, and list clarification questions. Do not change budgets, dietary requirements, or assume facts. person_id must be {p.id}. Input: {safe}',Advocate)
        output.person_id=p.id
        output.suggested_interests=[x for x in output.suggested_interests if x in {'Food','Coffee','Outdoors','Art','Music','Games','Museums'}]
    else:
        output=Advocate(person_id=p.id,summary=f'{p.name} is looking for {", ".join(p.interests) or "a shared adventure"}, within ${p.budget:g} per person.',suggested_interests=p.interests,questions=[])
    return {'outputs':[output.model_dump()]}


@private_tracing
def process_profiles(profiles,mode='Demo rules'):
    if not profiles: raise ValueError('Add at least one profile.')
    if mode=='Codex CLI' and any(not p.ai_consent for p in profiles):
        raise ValueError('Every participant must opt in before their profile is sent to Codex.')
    graph=StateGraph(AdvocateState)
    graph.add_node('advocate',advocate)
    graph.add_conditional_edges(START,dispatch,['advocate'])
    graph.add_edge('advocate',END)
    result=graph.compile().invoke({'profiles':[p.model_dump() for p in profiles],'mode':mode,'outputs':[]},config={'max_concurrency':4})
    order={p.id:i for i,p in enumerate(profiles)}
    return sorted(result['outputs'],key=lambda x:order[x['person_id']])


@private_tracing
def coordinate(profiles,proposals,mode,advocates=None):
    if not proposals:return 'No shared fit yet. Review the reasons below; the 50-mile rule has not been relaxed.'
    if mode=='Demo rules':return f'{proposals[0].place.name} leads on fairness. Three options, fewer messages, more actual plans. The humans still get the final say.'
    # Do not send original notes, photos, or exact origins to the coordinator.
    data=[{'name':p.place.name,'minimum_fit':p.minimum_score,'average_fit':p.average_score,
           'cost':p.place.cost,'distances_miles':{x.name:round(p.distances[x.id],1) for x in profiles}} for p in proposals]
    summaries=[{'person_id':a['person_id'],'summary':a['summary'],'questions':a['questions']} for a in (advocates or [])]
    return codex.ask(f'Personal advocates: {summaries}. Write a short warm and lightly funny introduction to these already-ranked group options. Preserve their order, do not invent facts or guarantees. Budget/distance/hours were checked in code. Say that group voting is next. Options: {data}',Coordinator).introduction
