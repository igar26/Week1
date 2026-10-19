"""Generate a silent, captioned architecture/demo video without running a server.

Run once: python scripts/build_demo.py
Watch saves: python scripts/build_demo.py --watch
Only allowlisted project sources are hashed. Real databases, .env, photos and
login credentials are never read. Synthetic decisions run in temporary storage.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / 'demo'
SECONDS = 8


def source_files():
    files = [ROOT / 'streamlit_app.py', ROOT / 'README.md', ROOT / '.streamlit/config.toml', ROOT / '.streamlit/secrets.toml.example']
    for folder in ('referee', 'scripts', 'tests'):
        files.extend((ROOT / folder).rglob('*.py'))
    files.extend(ROOT.glob('requirements*.txt'))
    files.extend((ROOT / 'assets').glob('*.png'))
    return sorted(p for p in files if p.is_file() and not p.is_symlink())


def fingerprint():
    digest = hashlib.sha256()
    for path in source_files():
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def synthetic_snapshot():
    from referee.store import Store
    from referee.catalog import demo_places
    from referee.decision import rank_options
    from referee.workflow import process_profiles
    from referee.models import Profile, Place
    from referee.itinerary import meeting_details
    from referee.simple import SimplePlans
    with tempfile.TemporaryDirectory(prefix='after-hours-demo-') as directory:
        store = Store(Path(directory))
        owner, _, keys = store.create_demo()
        profiles = store.profiles(owner)
        # Next Sunday in the venue timezone; no dependency on host timezone.
        day = datetime.now(ZoneInfo('America/Chicago')).date()
        day += timedelta(days=(6-day.weekday()) % 7 or 7)
        start = datetime.combine(day, datetime.min.time()).replace(hour=17, tzinfo=ZoneInfo('America/Chicago'))
        advocates = process_profiles(profiles, 'Demo rules')
        options, rejected = rank_options(profiles, demo_places(), start, 120)
        if not options:
            raise RuntimeError('Synthetic scenario has no eligible venues. Update the walkthrough scenario.')
        sid = store.start_poll(owner, 'A little less group chat, a little more fun', start, 120, options)
        for key in keys.values():
            store.vote(key, sid, {p.place.id: 2 for p in options})
        store.close_poll(owner, sid)
        for key in keys.values():
            store.confirm(key, sid)
        session = store.session(owner)
        details = meeting_details(session)
        store.complete(owner, sid)
        store.add_memory(owner, sid, 'Synthetic demo memory: a lovely evening together.', 5, True, [])
        simple=SimplePlans(store)
        from referee.demo import create_outing_demo
        from referee.common_ground import sample_analysis
        creator,code,demo_keys=create_outing_demo(store)
        preview=sample_analysis(simple,creator)
        simple.finalize(creator,preview['choice'])
        from referee.meetup import Meetups,recommend
        meetup=Meetups(simple)
        meetup.search(creator,'Coffee');meetup.open(creator)
        for key in demo_keys.values():
            person=next(r for r in simple.responses(key) if r['id']==store.member(key)['id'])
            if person['response']['attendance']!='Cannot join':
                meetup.vote(key,{p['place']['id']:2 for p in meetup.current(key)['places']})
        venue_preview=recommend(meetup,creator)
        meetup.finalize(creator,venue_preview['answer']['venue_id'])
        venue_winner=next(p['place']['name'] for p in meetup.current(creator)['places'] if p['place']['id']==meetup.current(creator)['winner'])
        photo_adventure=meetup.complete(creator)
        store.add_memory(creator,photo_adventure,'Synthetic meetup memory ready for group photos.',5,True,[])
        return {
            'simple_members':len(simple.responses(creator)),
            'venue_winner':venue_winner,'venue_voters':len(meetup.ballots(creator)),
            'simple_memories':len(store.memories(creator)),
            'simple_date':simple.plan(creator)['date'],
            'simple_winner':simple.plan(creator)['final_choice'],
            'people': len(profiles), 'advocates': len(advocates), 'eligible': len(options),
            'rejected': len(rejected), 'winner': details['place'].name,
            'duration': details['duration'], 'date': start.strftime('%B %d, %Y'),
            'status': session['status'], 'booked': bool(session['booked_at']),
            'memories': len(store.memories(owner)),
            'profile_fields': list(Profile.model_fields), 'venue_fields': list(Place.model_fields),
            'modules': [p.stem for p in sorted((ROOT/'referee').glob('*.py')) if p.stem!='__init__'],
            'test_functions': sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_')
                for p in (ROOT/'tests').glob('test_*.py') for n in ast.walk(ast.parse(p.read_text()))),
        }


def chapters(s):
    return [
        ('After Hours', 'How this app is built',
         'A code-generated walkthrough with a real synthetic decision run.\nSilent video: read the on-screen captions. No personal data.'),
        ('01 / The experience', 'Less group chat. More actual plans.',
         f"Sign in with Google to start a real event, then enter a ZIP and activity ideas and share an invite. Everyone saves preferences before the group searches nearby venues.\nThis synthetic run saved {s['simple_members']} responses and chose {s['simple_winner']}. Members need no API keys. The demo needs no account."),
        ('02 / Simple responses', 'Pick more than one good time',
         'Members choose Can join, Maybe or Cannot join, pick activities, set a personal spending limit and share needs.\nAfter members opt in, the coordinator can ask the LLM to explain a shared fit. Python checks shared choices; the coordinator still finalizes. Phone access requires secure hosting.'),
        ('03 / Individual budgets', 'A plan friends can afford',
         'Each person saves a maximum spend. Known venue estimates must fit the event budget and every definite attendee limit.\nMaybe stays tentative. Unknown cost needs checking; it is not a promise of affordability.'),
        ('04 / Shared decisions', 'Suggestions need agreement',
         'Python checks activity consensus, venue votes and budgets. The optional LLM explains only supplied choices and facts.\nEvery definite attendee must accept the venue. Only the coordinator confirms; AI never books or sends messages.'),
        ('05 / Nearby places', 'Real discovery, checked by humans',
         'Simple ZIP tiles use Geoapify Places with a host-managed key. Unknown hours, ratings and prices need checking.\nNeo4j and parallel advocates are legacy learning modules. This recording uses fictional places and no external API calls.'),
        ('06 / Agree on a venue', 'From shared activity to a real plan',
         f"Venue tiles and ballots stay on the group page. {s['venue_voters']} available or tentative demo members voted.\nTheir agreed fictional venue is {s['venue_winner']}. Real venue ratings and costs stay unknown until sourced."),
        ('07 / Our next adventure', 'A meetup you can actually follow',
         f"{s['simple_date']} at 6 PM Central, for {s['duration']}.\nThe group keeps its chosen venue and address together. Check hours and final costs before arranging a reservation. Fictional venues have no real route."),
        ('08 / After the yes', 'Reservations, texts and memories',
         f"Reservation made in this demo: {'yes' if s['booked'] else 'no'}. Current meetup scrapbook entries saved: {s['simple_memories']}.\nUpload photos in Our adventures: the group gallery refreshes automatically. Group settings supports leaving, coordinator transfer and optional deletion of your own memories."),
        ('09 / Keep learning', 'Built to stay reviewable',
         f"The current source has {len(s['modules'])} application modules and {s['test_functions']} test functions (not a test-pass count).\nHelp explains architecture and limitations. Run the watcher while coding; GitHub Actions rebuilds the artifact on pushes."),
    ]


def font(size):
    from PIL import ImageFont
    for path in ('/System/Library/Fonts/Supplemental/Arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def wrap(draw, text, face, width):
    lines=[]
    for paragraph in text.split('\n'):
        line=''
        for word in paragraph.split():
            candidate=(line+' '+word).strip()
            if line and draw.textlength(candidate,font=face)>width:
                lines.append(line);line=word
            else:line=candidate
        lines.append(line)
    return lines


def frame(chapter, index, total, revision):
    from PIL import Image, ImageDraw, ImageOps
    canvas=Image.new('RGB',(1280,720),'#10252e')
    draw=ImageDraw.Draw(canvas)
    hero=ROOT/'assets/dallas-after-hours.png'
    if hero.exists():
        with Image.open(hero) as image:
            picture=ImageOps.fit(image.convert('RGB'),(440,720))
        canvas.paste(picture,(840,0))
        canvas.paste(Image.new('RGB',(440,720),'#10252e'),(840,0),Image.new('L',(440,720),155))
    draw.rounded_rectangle((45,45,800,665),radius=28,fill='#193541',outline='#49707b',width=2)
    draw.text((80,78),chapter[0].upper(),font=font(22),fill='#ffac85')
    y=145
    for line in wrap(draw,chapter[1],font(44),655):
        draw.text((80,y),line,font=font(44),fill='#fff3e7');y+=57
    y+=20
    for line in wrap(draw,chapter[2],font(25),650):
        draw.text((80,y),line,font=font(25),fill='#d5e8e6');y+=37
    draw.text((80,605),f'CODE {revision[:10]}   /   SYNTHETIC DATA ONLY',font=font(17),fill='#a7c8cb')
    draw.text((905,555),f'{index+1:02}/{total:02}',font=font(48),fill='#ffac85')
    draw.rounded_rectangle((80,650,80+int(680*(index+1)/total),654),radius=2,fill='#ffac85')
    return canvas


def timestamp(seconds):
    return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}.000'


def build():
    import imageio_ffmpeg
    revision=fingerprint()
    snapshot=synthetic_snapshot()
    scenes=chapters(snapshot)
    OUTPUT.mkdir(exist_ok=True)
    # Publish the manifest last: unsuccessful builds never claim to be current.
    with tempfile.TemporaryDirectory(prefix='after-hours-video-') as directory:
        video=Path(directory)/'walkthrough.mp4'
        writer=imageio_ffmpeg.write_frames(str(video),(1280,720),fps=5,codec='libx264',
                    pix_fmt_out='yuv420p',output_params=['-movflags','+faststart'],ffmpeg_log_level='error')
        writer.send(None)
        try:
            for i,scene in enumerate(scenes):
                image=frame(scene,i,len(scenes),revision)
                raw=image.tobytes()
                for _ in range(SECONDS*5):writer.send(raw)
                if i==0:image.save(OUTPUT/'poster.jpg')
        finally:
            writer.close()
        # Validate encoded output before replacing the existing video.
        reader=imageio_ffmpeg.read_frames(str(video))
        try:
            metadata=next(reader)
            next(reader)
            if metadata['size']!=(1280,720):raise RuntimeError('Unexpected video size')
        finally:reader.close()
        import shutil
        shutil.copyfile(video,OUTPUT/'walkthrough.new.mp4')
        (OUTPUT/'walkthrough.new.mp4').replace(OUTPUT/'walkthrough.mp4')
    captions='WEBVTT\n\n'+'\n\n'.join(f'{timestamp(i*SECONDS)} --> {timestamp((i+1)*SECONDS)}\n{title}. {body}' for i,(_,title,body) in enumerate(scenes))+'\n'
    (OUTPUT/'captions.vtt').write_text(captions)
    (OUTPUT/'transcript.txt').write_text('\n\n'.join(f'{title}\n{body}' for _,title,body in scenes)+'\n')
    (OUTPUT/'manifest.json').write_text(json.dumps({'source_sha256':revision,'generated_at':datetime.now(ZoneInfo('America/Chicago')).isoformat(),
          'seconds':len(scenes)*SECONDS,'format':'captioned slides, not a screen recording','snapshot':snapshot},indent=2)+'\n')
    print(f'Updated demo/walkthrough.mp4 ({len(scenes)*SECONDS}s), source {revision[:10]}',flush=True)
    return revision


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch',action='store_true',help='Regenerate after source saves; Ctrl+C stops.')
    args=parser.parse_args()
    previous=None
    try:
        while True:
            current=fingerprint()
            if current!=previous:
                time.sleep(1)  # Coalesce editor saves before building.
                try:
                    if args.watch:
                        # Fresh imports make edits to application modules visible on every rebuild.
                        subprocess.run([sys.executable, str(Path(__file__).resolve())], check=True, cwd=ROOT)
                        previous=json.loads((OUTPUT/'manifest.json').read_text())['source_sha256']
                    else:
                        previous=build()
                except Exception as error:
                    print(f'Demo build failed ({type(error).__name__}). Previous video retained; fix code and save again.',file=sys.stderr,flush=True)
                    if not args.watch:raise
                    previous=current
            if not args.watch:break
            time.sleep(2)
    except KeyboardInterrupt:
        print('\nDemo watcher stopped.')


if __name__=='__main__':main()
