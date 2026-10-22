"""Game resource settings, separate from model placement and private credentials."""
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]

def config():
    value=json.loads((ROOT/'game-settings.json').read_text())
    for role in ('server','client'):
        for key in ('min_heap','max_heap'):
            if not re.fullmatch(r'[1-9][0-9]*[GM]',value[role][key]):raise ValueError('Invalid game heap size')
    return value

def client_options(path):
    path=Path(path);options=config()['client']['options']
    lines=path.read_text().splitlines() if path.exists() else []
    lines=[s for s in lines if s.split(':',1)[0] not in options]
    for k,v in options.items():lines.append(k+':'+(str(v).lower() if isinstance(v,bool) else str(v)))
    path.write_text('\n'.join(lines)+'\n')
