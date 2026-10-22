"""Shared model selection for launch, ownership checks, readiness and dashboard."""
from pathlib import Path
import json,os
ROOT=Path(__file__).resolve().parents[1]

def settings():return json.loads((ROOT/'model-settings.json').read_text())

def selected():
    if os.environ.get('GAME_MODEL'):return os.environ['GAME_MODEL']
    try:return json.loads((ROOT/'runtime/selected-model.json').read_text())['model']
    except (OSError,ValueError,KeyError):return settings()['selected']

def config(key=None):
    key=key or selected();models=settings()['models']
    if key not in models:raise ValueError('未知模型：'+str(key))
    return {'key':key,**models[key]}

def select(key):
    config(key)
    folder=ROOT/'runtime';folder.mkdir(exist_ok=True)
    p=folder/'selected-model.json';tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps({'model':key}));tmp.replace(p)

def expected(conf=None):
    c=conf or config();data=json.loads((ROOT/c['checksums']).read_text())
    result={}
    for kind in ['model','vision']:
        path=ROOT/c[kind]
        if c['key']=='9b' and kind=='model':
            digest=json.loads((ROOT/'gguf-normalization.json').read_text())['output_sha256']
        else:digest=data[path.name]['sha256']
        result[path]=digest
    return result
