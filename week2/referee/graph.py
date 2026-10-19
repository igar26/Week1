"""Optional real Neo4j graph: parameters only, with group-scoped identifiers."""
import os
from .models import Place


class GraphError(RuntimeError):pass


class Graph:
    def __enter__(self):
        try:
            from neo4j import GraphDatabase
            if not os.getenv('NEO4J_PASSWORD'):raise GraphError('Set NEO4J_PASSWORD in week2/.env and start Neo4j first.')
            self.driver=GraphDatabase.driver(os.getenv('NEO4J_URI','bolt://localhost:7687'),auth=(os.getenv('NEO4J_USERNAME','neo4j'),os.environ['NEO4J_PASSWORD']),connection_timeout=5)
            self.driver.verify_connectivity();return self
        except GraphError:raise
        except Exception:raise GraphError('Neo4j is unavailable. Check the URI, credentials and running database. No local fallback was substituted.') from None

    def __exit__(self,*args):self.driver.close()

    def run(self,query,**parameters):
        try:
            records,_,_=self.driver.execute_query(query,parameters_=parameters,database_=os.getenv('NEO4J_DATABASE','neo4j'))
            return [r.data() for r in records]
        except Exception:raise GraphError('Neo4j could not execute the group graph query. Check database permissions and settings.') from None

    def sync(self,group,profiles,places,session=None,ballots=None,memories=None):
        if any(not p.graph_consent for p in profiles):raise GraphError('Every participant must opt in before profile data is copied to Neo4j.')
        gid=group['id']
        self.run('MERGE (g:Group {id:$gid}) SET g.name=$name',gid=gid,name=group['name'])
        # Replace this group's preference edges so edits never leave old preferences behind.
        self.run('MATCH (:Group {id:$gid})-[:HAS_MEMBER]->(p:Person)-[r:LIKES|REQUIRES]->() DELETE r',gid=gid)
        for p in profiles:
            self.run('MERGE (g:Group {id:$gid}) MERGE (p:Person {id:$pid}) SET p.name=$name,p.budget=$budget,p.location=point({latitude:$lat,longitude:$lon}) MERGE (g)-[:HAS_MEMBER]->(p)',gid=gid,pid=p.id,name=p.name,budget=p.budget,lat=p.lat,lon=p.lon)
            for interest in p.interests:self.run('MATCH (p:Person {id:$pid}) MERGE (i:Interest {name:$name}) MERGE (p)-[:LIKES]->(i)',pid=p.id,name=interest)
            for diet in p.diets:self.run('MATCH (p:Person {id:$pid}) MERGE (i:Requirement {name:$name}) MERGE (p)-[:REQUIRES]->(i)',pid=p.id,name=diet)
        for p in places:
            if p.source.startswith('Google'):continue # No durable Google content mirroring.
            place_key=gid+':'+p.id
            self.run('MATCH (g:Group {id:$gid}) MERGE (p:Place {id:$id}) SET p.external_id=$external,p.name=$name,p.location=point({latitude:$lat,longitude:$lon}),p.cost=$cost MERGE (g)-[:CONSIDERS]->(p)',gid=gid,id=place_key,external=p.id,name=p.name,lat=p.lat,lon=p.lon,cost=p.cost)
            for interest in p.interests:self.run('MATCH (p:Place {id:$id}) MERGE (i:Interest {name:$name}) MERGE (p)-[:OFFERS]->(i)',id=place_key,name=interest)
        if session:
            self.run('MATCH (g:Group {id:$gid}) MERGE (s:Plan {id:$sid}) SET s.title=$title,s.status=$status MERGE (g)-[:PLANS]->(s)',gid=gid,sid=session['id'],title=session['title'],status=session['status'])
            for vote in ballots or []:
                self.run('MATCH (s:Plan {id:$sid}),(p:Person {id:$pid}) MERGE (v:Vote {id:$id}) SET v.value=$value,v.place_id=$place MERGE (p)-[:CAST]->(v) MERGE (v)-[:IN_PLAN]->(s)',sid=session['id'],pid=vote['member_id'],id=session['id']+':'+vote['member_id']+':'+vote['place_id'],value=vote['value'],place=vote['place_id'])
        for memory in memories or []:
            self.run('MATCH (g:Group {id:$gid}) MERGE (m:Memory {id:$mid}) SET m.caption=null,m.date=$date MERGE (g)-[:REMEMBERS]->(m)',gid=gid,mid=memory['id'],date=memory['created'])
        return 'Neo4j graph updated for this group.'

    def candidate_ids(self,group_id):
        rows=self.run('''MATCH (g:Group {id:$gid})-[:HAS_MEMBER]->(person:Person)
            WITH g,collect(person) AS people
            MATCH (g)-[:CONSIDERS]->(place:Place)
            WHERE size(people)>0 AND all(person IN people WHERE point.distance(person.location,place.location)<=80467.2)
            RETURN place.external_id AS id''',gid=group_id)
        return {r['id'] for r in rows}
