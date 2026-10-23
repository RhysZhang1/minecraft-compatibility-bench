"""Rebind an already extracted private snapshot to its new directory; no deletion."""
from pathlib import Path
import argparse,json,os,sys,shutil
ROOT=Path(__file__).resolve().parents[1]
def path_mapping(metadata,root):
 mapping={metadata['workspace']:str(root),**{origin:str(root/target) for target,origin in metadata['external_exports'].items()}}
 # Libraries and assets are exported separately, but launch profiles use their common parent.
 for target,origin in metadata['external_exports'].items():
  if Path(origin).name in ('libraries','assets') and Path(target).name==Path(origin).name:
   mapping[str(Path(origin).parent)]=str((root/target).parent)
 return mapping
def convert_paths(value,mapping,original_home):
 if isinstance(value,str):
  candidate=original_home+value[1:] if value.startswith('~/') else value
  for source,target in sorted(mapping.items(),key=lambda x:-len(x[0])):
   if candidate==source or candidate.startswith(source+'/'):return target+candidate[len(source):]
  return value
 if isinstance(value,list):return [convert_paths(v,mapping,original_home) for v in value]
 if isinstance(value,dict):return {k:convert_paths(v,mapping,original_home) for k,v in value.items()}
 return value
def rebind():
 metadata=json.loads((ROOT/'PRIVATE-BACKUP.json').read_text());old=metadata['workspace'];exports=metadata['external_exports']
 mapping=path_mapping(metadata,ROOT)
 def convert(value):return convert_paths(value,mapping,metadata.get('home',str(Path.home())))
 for name in ['local-settings.json','local-instances.json','local-vanilla-servers.json']:
  p=ROOT/name
  if p.exists():shutil.copy2(p,p.with_suffix('.before-rebind.json'));p.write_text(json.dumps(convert(json.loads(p.read_text())),ensure_ascii=False,indent=2));p.chmod(0o600)
 sys.path.insert(0,str(ROOT/'src'));import instance_config as ic,local_environment as env
 # Public default paths may still point to external launchers: put rebound profiles in private config.
 p=ROOT/'local-instances.json';data=json.loads(p.read_text()) if p.exists() else {'instances':{}}
 for key,profile in ic.settings()['instances'].items():data['instances'][key]=convert(profile)
 p.write_text(json.dumps(data,ensure_ascii=False,indent=2));p.chmod(0o600)
 settings=env.settings();llama=ROOT/'external/llama-cpp'
 if llama.exists():settings.update(llama_source=str(llama),llama_server=str(llama/'build/bin/llama-server'))
 java=convert(env.java())
 if Path(java).exists():settings['java']=java
 env.save(settings)
 import vanilla_servers
 for key,item in vanilla_servers.registry().items():
  folder=Path(item['directory'])
  if folder.is_dir() and folder.resolve().is_relative_to(ROOT):vanilla_servers.write_wrappers(folder,key)
 python=ROOT/'external/python-runtime/bin/python3.11'
 if python.exists() and (ROOT/'.venv').exists():
  for name in ('python','python3','python3.11'):
   p=ROOT/'.venv/bin'/name
   if p.is_symlink():p.unlink()
   if not p.exists():p.symlink_to(python)
  cfg=ROOT/'.venv/pyvenv.cfg'
  if cfg.exists():
   text=cfg.read_text()
   for source,target in sorted(mapping.items(),key=lambda x:-len(x[0])):text=text.replace(source,target)
   text='\n'.join('home = '+str(python.parent) if line.startswith('home =') else line for line in text.splitlines())+'\n';cfg.write_text(text)
  for p in (ROOT/'.venv').glob('lib/python*/site-packages/*.pth'):
   text=p.read_text()
   for source,target in sorted(mapping.items(),key=lambda x:-len(x[0])):text=text.replace(source,target)
   p.write_text(text)
  for p in (ROOT/'.venv/bin').iterdir():
   if not p.is_file() or p.is_symlink():continue
   raw=p.read_bytes()
   if raw.startswith(b'#!') and old.encode() in raw.split(b'\n',1)[0]:p.write_bytes(raw.replace(old.encode(),str(ROOT).encode()))
 print('路径已重绑定。下一步运行 ./setup.sh --doctor；依赖系统显卡驱动与KWin/Xwayland。')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--rebind',action='store_true',required=True);p.parse_args();rebind()
