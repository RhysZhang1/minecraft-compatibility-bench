"""Mojang-published names -> runtime names; optional telemetry never guesses facts."""
from pathlib import Path
import json,re,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import instance_config as ic
from vanilla_servers import download

def prepare():
 c=ic.config();client=ic.client_directory();meta=json.loads((client/c['client']['manifest']).read_text());props={}
 if c['minecraft_version']=='1.7.10':
  import legacy_bindings
  props=legacy_bindings.prepare()
 item=meta.get('downloads',{}).get('client_mappings')
 if item:
  mapping=client/'client-mappings.txt';download(item['url'],mapping,item['sha1'])
  owner=None
  for line in mapping.read_text().splitlines():
   if line.startswith('#'):continue
   if line and not line[0].isspace() and ' -> ' in line:
    owner,actual=line.rstrip(':').split(' -> ');props['class.'+owner]=actual;props['reverse.'+actual]=owner
   elif owner and ' -> ' in line:
    source,actual=line.strip().split(' -> ')
    source=re.sub(r'^\d+:\d+:','',source)
    if '(' in source:
     kind='method';name=source.split('(')[0].split()[-1];args=source.split('(',1)[1].split(')',1)[0];arity=str(len(args.split(',')) if args else 0);ret=source.split()[0];signature='signature.'+owner+'.'+name+'.'+arity;entry=actual+'|'+ret+'|'+args;props[signature]=';'.join(dict.fromkeys((props.get(signature,'')+';'+entry).strip(';').split(';')));name+='.'+arity
    else:kind='field';name=source.split()[-1]
    key=kind+'.'+owner+'.'+name
    props[key]=','.join(dict.fromkeys((props.get(key,'')+','+actual).strip(',').split(',')))
 out=ROOT/'runtime/client-bindings.properties';out.parent.mkdir(exist_ok=True);out.write_text('\n'.join(k+'='+v for k,v in props.items())+'\n')
 return bool(props) or c['minecraft_version'].startswith('26.')
if __name__=='__main__':print(prepare())
