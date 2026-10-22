"""Public source release and offline private snapshot, with verifiable manifests."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,tarfile,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import instance_config as ic,local_environment as env
DENY={'models','instances','runtime','logs','memory','backups','.venv','.cache','.git','research','engines','external','release'}
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(16*1024*1024),b''):h.update(b)
 return h.hexdigest()
def public_files():
 result=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
 return sorted({s for s in result if s and s!='SOURCE-MANIFEST.json' and Path(s).parts[0] not in DENY and not Path(s).name.startswith(('local-','PRIVATE-','restore-')) and (ROOT/s).is_file()})
def filter_private(info):
 if info.isfifo() or info.isdev() or 'runtime/virtual-session' in info.name:return None
 return info

def externals():
 exports={};seen={}
 def put(source,target):
  source=Path(source).expanduser().resolve()
  if not source.exists() or source.is_relative_to(ROOT):return
  if str(source) not in seen:exports[target]=str(source);seen[str(source)]=target
 for key in ic.settings()['instances']:
  p=ic.config(key);client=ic.path(p['client']['directory']);server=ic.path(p['server']['directory'])
  put(client,'external/clients/'+key)
  put(ic.path(p['memory_directory']),'external/memory/'+key)
  put(ic.path(p['episodes_directory']),'external/episodes/'+key)
  if p['server'].get('managed'):put(server,'external/servers/'+key)
  library=ic.path(p['client']['libraries_root'])
  for name in ['libraries','assets']:put(library/name,'external/libraries/'+key+'/'+name)
  java=ic.path(p['java']) if p.get('java') else Path(env.java())
  if java.exists():put(java.resolve().parents[1],'external/java/'+key)
 import vanilla_servers
 for key,item in vanilla_servers.registry().items():put(item['directory'],'external/vanilla-servers/'+key)
 put(env.llama_source(),'external/llama-cpp')
 put((ROOT/'.venv/bin/python').resolve().parents[1],'external/python-runtime')
 return exports

def verify(manifest):
 p=Path(manifest).resolve();data=json.loads(p.read_text())
 for name,info in data.items():
  target=p.parent/name
  if target.parent!=p.parent or not target.is_file() or target.stat().st_size!=info['size'] or digest(target)!=info['sha256']:raise ValueError('备份校验失败：'+name)
  print('SHA256 OK '+name,flush=True)
  if name.endswith('.tar.zst'):subprocess.run(['zstd','-q','-t',str(target)],check=True)
  elif name.endswith('.tar.gz'):
   with tarfile.open(target) as archive:archive.getmembers()
 return data

def main():
 p=argparse.ArgumentParser();p.add_argument('--full',action='store_true');p.add_argument('--verify');a=p.parse_args()
 if a.verify:verify(a.verify);return
 import manage,vanilla_servers
 if a.full and (any(manage.owned_pids(n) for n in (*manage.NAMES,'switch')) or any(vanilla_servers.owned(v) for v in vanilla_servers.registry().values())):raise ValueError('完整私有备份前请先运行stop.sh，不能复制仍在写入的世界')
 folder=ROOT/'backups';folder.mkdir(exist_ok=True);stamp=time.strftime('%Y%m%d-%H%M%S');files=public_files()
 source=folder/f'minecraft-agent-source-{stamp}.tar.gz';members={}
 with tarfile.open(source,'w:gz',compresslevel=1) as tar:
  for name in files:
   path=ROOT/name;tar.add(path,arcname=name,recursive=False);members[name]={'size':path.stat().st_size,'sha256':digest(path)}
  release=[(ROOT/'sensors/gamescaling-sensors-agent.jar','release/gamescaling-sensors-agent.jar'),(ROOT/'input/libgamescaling-ei.so','release/libgamescaling-ei.so'),(ROOT/'instances/client/mods/GameScalingBridge-1.0.jar','release/GameScalingBridge-1.0.jar')]
  release += [(p,'release/'+p.name) for p in (ROOT/'input').glob('*.jar')]
  for path,name in release:
   if path.is_file():tar.add(path,arcname=name,recursive=False);members[name]={'size':path.stat().st_size,'sha256':digest(path)}
  import io
  content=json.dumps(members,indent=2).encode();info=tarfile.TarInfo('SOURCE-MANIFEST.json');info.size=len(content);tar.addfile(info,io.BytesIO(content))
 outputs=[source]
 bundle=folder/f'minecraft-agent-history-{stamp}.bundle'
 subprocess.run(['git','bundle','create',str(bundle),'--all'],cwd=ROOT,check=True);outputs.append(bundle)
 if a.full:
  full=folder/f'PRIVATE-minecraft-agent-full-{stamp}.tar.zst';exports=externals()
  metadata={'created_at':time.time(),'workspace':str(ROOT),'home':str(Path.home()),'external_exports':exports,'selected_instance':ic.selected(),'contains':'source + Git bundle + all model files + instances/worlds + memory/traces + local config + Python environment + declared external runtimes/resources','restore':'scripts/restore_private.py --rebind'}
  with full.open('wb') as output:
   compressor=subprocess.Popen(['zstd','-T4','-1','-q','-c'],stdin=subprocess.PIPE,stdout=output)
   try:
    with tarfile.open(fileobj=compressor.stdin,mode='w|') as tar:
     for name in files:tar.add(ROOT/name,arcname=name,recursive=False)
     for name in ['instances','models','runtime','logs','memory','.venv','input','sensors','local-instances.json','local-settings.json','local-vanilla-servers.json']:
      if (ROOT/name).exists():tar.add(ROOT/name,arcname=name,filter=filter_private)
     tar.add(bundle,arcname='restore-history.bundle');tar.add(source,arcname='restore-source.tar.gz')
     for target,origin in exports.items():tar.add(origin,arcname=target,filter=filter_private)
     import io
     data=json.dumps(metadata,ensure_ascii=False,indent=2).encode();info=tarfile.TarInfo('PRIVATE-BACKUP.json');info.size=len(data);tar.addfile(info,io.BytesIO(data))
   finally:compressor.stdin.close()
   if compressor.wait()!=0:raise RuntimeError('完整备份压缩失败')
  outputs.append(full)
 manifest={p.name:{'size':p.stat().st_size,'sha256':digest(p)} for p in outputs}
 target=folder/f'backup-manifest-{stamp}.json';target.write_text(json.dumps(manifest,indent=2));print(target,flush=True)
 for path in outputs:print(path,flush=True)
if __name__=='__main__':main()
