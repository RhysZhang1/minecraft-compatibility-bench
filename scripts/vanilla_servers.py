"""Independent loopback vanilla server testbeds; no client support is implied."""
from pathlib import Path
import argparse,hashlib,json,os,re,secrets,shutil,signal,socket,subprocess,sys,time,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import local_environment,server_console
REGISTRY=ROOT/'local-vanilla-servers.json'
MANIFEST='https://launchermeta.mojang.com/mc/game/version_manifest_v2.json'
def registry():return json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
def digest(path,algorithm='sha256'):
    h=hashlib.new(algorithm)
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def fetch_json(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url,timeout=60) as response:return json.load(response)
        except (OSError,ValueError):
            if attempt==2:raise
            time.sleep(attempt+1)
def download(url,target,sha1):
    target=Path(target)
    if target.exists():
        if digest(target,'sha1')!=sha1:raise ValueError('已有文件校验失败，不覆盖：'+str(target))
        return
    tmp=target.with_suffix('.partial')
    print('下载官方文件：'+url,flush=True)
    with urllib.request.urlopen(url,timeout=60) as response,tmp.open('wb') as f:shutil.copyfileobj(response,f)
    if digest(tmp,'sha1')!=sha1:raise ValueError('官方文件SHA1校验失败，未使用下载结果')
    tmp.replace(target)
def version_of(jar):
    with zipfile.ZipFile(jar) as z:
        if 'version.json' in z.namelist():return json.loads(z.read('version.json'))
    return {}
def create(version,base,port=25567,rcon=25587,source=None,eula_source=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',version) or version in ('.','..'):raise ValueError('版本号无效')
    if not(1<=port<=65535 and 1<=rcon<=65535) or port==rcon:raise ValueError('端口无效')
    base=Path(base).expanduser().resolve();folder=base/('vanilla-'+version)
    if folder.exists():raise ValueError('目录已存在，不覆盖：'+str(folder))
    metadata=None
    if source:
        source=Path(source).expanduser().resolve();found=version_of(source)
        if found.get('id') and found['id']!=version:raise ValueError('源JAR实际版本与请求不一致')
    else:
        cached=ROOT/'instances'/('vanilla-'+version+'-client')/(version+'.json')
        if cached.exists():metadata=json.loads(cached.read_text())
        else:
            entry=next((x for x in fetch_json(MANIFEST)['versions'] if x['id']==version),None)
            if not entry:raise ValueError('官方版本清单中没有该版本')
            metadata=fetch_json(entry['url'])
        if 'server' not in metadata['downloads']:raise ValueError('此版本无官方服务器下载')
    # All validation before creating the destination; an existing server is never touched.
    folder.mkdir(parents=True)
    if source:shutil.copy2(source,folder/'server.jar')
    else:
        item=metadata['downloads']['server'];download(item['url'],folder/'server.jar',item['sha1'])
        (folder/'official-version.json').write_text(json.dumps(metadata,indent=2))
    if eula_source:
        eula_source=Path(eula_source).expanduser()
        if not re.search(r'^eula=true\s*$',eula_source.read_text(),re.M):raise ValueError('源EULA文件没有既有接受记录')
        shutil.copy2(eula_source,folder/'eula.txt')
    password=secrets.token_hex(32)
    values={'server-ip':'127.0.0.1','server-port':str(port),'enable-rcon':'true','rcon.port':str(rcon),'rcon.password':password,
            'online-mode':'false','level-name':'test-world','difficulty':'peaceful' if version!='1.7.10' else '0',
            'view-distance':'8','simulation-distance':'8','max-players':'4','spawn-protection':'0','motd':'Isolated compatibility test '+version}
    p=folder/'server.properties';p.write_text('\n'.join(k+'='+v for k,v in values.items())+'\n');p.chmod(0o600)
    item={'version':version,'directory':str(folder),'port':port,'rcon_port':rcon,'java':local_environment.java(),
          'server_sha256':digest(folder/'server.jar'),'memory':{'min':'1G','max':'4G'},'created_at':time.time()}
    values=registry();key=version
    if key in values:key=version+'-'+str(int(time.time()))
    values[key]=item;tmp=REGISTRY.with_suffix('.tmp');tmp.write_text(json.dumps(values,indent=2));tmp.chmod(0o600);tmp.replace(REGISTRY)
    # Small local wrappers refer back to the project manager; backup restore notes describe rebinding.
    import shlex
    for action in ('start','stop'):
        script=folder/(action+'.sh');script.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexec python3 '+shlex.quote(str(ROOT/'scripts/vanilla_servers.py'))+' '+action+' '+shlex.quote(key)+'\n');script.chmod(0o755)
    (folder/'README.txt').write_text('独立原版服务器 '+version+'\n此服务器能启动不代表AI客户端已支持本版本。\n仅监听本机；离线测试。已有EULA接受记录仅在显式指定源文件时复制。\n')
    print(json.dumps({'key':key,**item},ensure_ascii=False,indent=2));return key

def owned(item):
    folder=Path(item['directory']);p=folder/'server.pid'
    try:
        pid=int(p.read_text());proc=Path('/proc')/str(pid);args=(proc/'cmdline').read_bytes().decode().split('\0')
        if (proc/'cwd').resolve()==folder and Path(args[0]).name=='java' and '-jar' in args and args.index('-jar')+1<len(args) and args[args.index('-jar')+1]=='server.jar':return pid
    except (OSError,ValueError):pass
    return None

def command(item,text):
    return server_console.execute(text,Path(item['directory'])/'server.properties')
def start(key):
    item=registry()[key];folder=Path(item['directory'])
    if owned(item):print('已运行：'+key);return
    if not (folder/'eula.txt').exists() or not re.search(r'^eula=true\s*$',(folder/'eula.txt').read_text(),re.M):
        raise ValueError('此测试服尚无EULA接受记录；请提供你已接受的eula.txt，或自行阅读官方条款后配置')
    for port in (item['port'],item['rcon_port']):
        with socket.socket() as sock:sock.bind(('127.0.0.1',port))
    fifo=folder/'console.fifo'
    if not fifo.exists():os.mkfifo(fifo,0o600)
    fd=os.open(fifo,os.O_RDWR)
    try:
        with (folder/'console.log').open('ab') as log:
            p=subprocess.Popen([item['java'],'-Xms'+item['memory']['min'],'-Xmx'+item['memory']['max'],'-jar','server.jar','nogui'],
                cwd=folder,stdin=fd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    finally:os.close(fd)
    (folder/'server.pid').write_text(str(p.pid));deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        if not owned(item):raise RuntimeError('服务器提前退出；检查 '+str(folder/'console.log'))
        try:
            output=command(item,'list')
            settings=[]
            rule='minecraft:keep_inventory' if item['version'].startswith('26.') else 'keepInventory'
            for text in ('difficulty peaceful','gamerule '+rule+' true','gamerule '+rule,'save-all'):
                reply=command(item,text)
                if any(x in reply for x in ['Incorrect argument','Unknown or incomplete command','Unknown game rule']):raise ValueError('设置验证失败：'+text+' / '+reply)
                settings.append({'command':text,'output':reply})
            result={'time':time.time(),'version':item['version'],'pid':p.pid,'list':output,'settings':settings,'client_tested':False}
            (folder/'validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2));return result
        except (OSError,ConnectionError):time.sleep(.5)
    raise TimeoutError('服务器命令接口等待超时')
def stop(key):
    item=registry()[key];pid=owned(item)
    if not pid:return
    folder=Path(item['directory']);fd=os.open(folder/'console.fifo',os.O_WRONLY|os.O_NONBLOCK)
    try:os.write(fd,b'save-all\nstop\n')
    finally:os.close(fd)
    deadline=time.monotonic()+90
    while owned(item) and time.monotonic()<deadline:time.sleep(.2)
    if owned(item):raise RuntimeError('仍在保存，保留进程：'+key)
    (folder/'server.pid').unlink(missing_ok=True);print('已保存并停止：'+key)
def stop_all():
    for key in registry():stop(key)
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['create','list','start','stop','stop-all']);p.add_argument('version',nargs='?');p.add_argument('--base',default=str(Path.home()/'Desktop/MC26.3/tests'));p.add_argument('--port',type=int,default=25567);p.add_argument('--rcon-port',type=int,default=25587);p.add_argument('--source');p.add_argument('--eula-source');a=p.parse_args()
    if a.action=='list':
        for k,v in registry().items():print(k,v['directory'],'running='+str(owned(v)))
    elif a.action=='create':
        version=a.version or input('Minecraft版本（例如1.7.10、26.3）: ').strip()
        create(version,a.base,a.port,a.rcon_port,a.source,a.eula_source)
    elif a.action=='start':start(a.version)
    elif a.action=='stop':stop(a.version)
    else:stop_all()
if __name__=='__main__':main()
