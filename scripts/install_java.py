"""Install project-local Mojang launcher runtimes; every file uses its official SHA1."""
from pathlib import Path
import argparse,concurrent.futures,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from vanilla_servers import fetch_json,download
ALL='https://piston-meta.mojang.com/v1/products/java-runtime/2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json'
COMPONENTS={8:'jre-legacy',16:'java-runtime-alpha',17:'java-runtime-gamma',21:'java-runtime-delta',25:'java-runtime-epsilon'}
def install(major):
    if major not in COMPONENTS:raise ValueError('启动器未登记这个Java版本')
    target=ROOT/'instances/java'/str(major)
    if (target/'bin/java').exists():return target
    entry=fetch_json(ALL)['linux'][COMPONENTS[major]][0];target.mkdir(parents=True,exist_ok=True)
    manifest_path=target/'runtime-manifest.json';download(entry['manifest']['url'],manifest_path,entry['manifest']['sha1']);manifest=json.loads(manifest_path.read_text())
    tasks=[]
    for name,item in manifest['files'].items():
        p=target/name
        if not p.resolve().is_relative_to(target.resolve()):raise ValueError('运行时文件路径越界')
        if item['type']=='directory':p.mkdir(parents=True,exist_ok=True)
        elif item['type']=='file':tasks.append((p,item))
    def work(task):
        p,item=task;p.parent.mkdir(parents=True,exist_ok=True);i=item['downloads']['raw'];download(i['url'],p,i['sha1'])
        if item.get('executable'):p.chmod(0o755)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(work,tasks))
    for name,item in manifest['files'].items():
        if item['type']=='link':
            p=target/name
            if not (p.parent/item['target']).resolve().is_relative_to(target.resolve()):raise ValueError('运行时链接越界')
            if not p.exists():p.symlink_to(item['target'])
    (target/'download-provenance.json').write_text(json.dumps(entry,indent=2));print(target,flush=True);return target
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('major',type=int);a=p.parse_args();install(a.major)
