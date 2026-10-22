"""Extract structured early quest requirements from the installed pack."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
QUESTS=ROOT/'instances/client/config/betterquesting/DefaultQuests/Quests'

def main():
    records=[]
    for stem in ['YourFirstNight','SticksnStones']:
        paths=list(QUESTS.glob(f'AndSoItBegins*/*{stem}*.json'))
        if len(paths)!=1:raise RuntimeError('Unexpected quest inventory: '+stem)
        p=paths[0];d=json.loads(p.read_text());props=d['properties:10']['betterquesting:10']
        tasks=[]
        for task in d.get('tasks:9',{}).values():
            items=[{'item':x.get('id:8'),'ore_dictionary':x.get('OreDict:8',''),'count':x['Count:3']} for x in task.get('requiredItems:9',{}).values()]
            if items:tasks.append({'consume':bool(task.get('consume:1',0)),'items':items})
        records.append({'title':re.sub('§.','',props['name:8']),'tasks':tasks,
                        'source':str(p.relative_to(ROOT/'instances/client')),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    target=ROOT/'runtime/gtnh-context.json';target.write_text(json.dumps({'pack':'GTNH 2.8.4','quests':records},indent=2))
    print(target)

if __name__=='__main__':main()
