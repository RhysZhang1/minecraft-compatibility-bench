"""Separate a private full local snapshot from GitHub-ready source archives."""
from pathlib import Path
import argparse,hashlib,json,subprocess,tarfile,time
ROOT=Path(__file__).resolve().parents[1]

def add(archive,path,base=None):
    archive.add(path,arcname=str(path.relative_to(base or ROOT)),recursive=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--full',action='store_true');a=parser.parse_args()
    folder=ROOT/'backups';folder.mkdir(exist_ok=True);stamp=time.strftime('%Y%m%d-%H%M%S')
    source=folder/f'gamescaling-gtnh-source-{stamp}.tar.gz'
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    with tarfile.open(source,'w:gz',compresslevel=1) as tar:
        for f in tracked:
            if f and (ROOT/f).is_file():add(tar,ROOT/f)
        mod=ROOT/'instances/client/mods/GameScalingBridge-1.0.jar'
        if mod.exists():tar.add(mod,arcname='release/GameScalingBridge-1.0.jar')
    bundle=folder/f'gamescaling-gtnh-history-{stamp}.bundle'
    subprocess.run(['git','bundle','create',str(bundle),'--all'],cwd=ROOT,check=True)
    outputs=[source,bundle]
    if a.full:
        # Run after stopping client/server cleanly; never copy a live world save.
        full=folder/f'PRIVATE-gamescaling-gtnh-full-{stamp}.tar.zst'
        paths=[name for name in tracked if name and (ROOT/name).is_file()]
        paths += [name for name in ['instances','models','runtime','logs'] if (ROOT/name).exists()]
        filelist='\0'.join(paths)+'\0'
        subprocess.run(['tar','-I','zstd -T4 -1','-cf',str(full),'--null','-T','-'],
                       input=filelist.encode(),cwd=ROOT,check=True)
        outputs.append(full)
    manifest={}
    for p in outputs:
        h=hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(16*1024*1024),b''):h.update(b)
        manifest[p.name]={'size':p.stat().st_size,'sha256':h.hexdigest()}
    target=folder/f'backup-manifest-{stamp}.json';target.write_text(json.dumps(manifest,indent=2));print(target,flush=True)
    for p in outputs:print(p,flush=True)

if __name__=='__main__':main()
