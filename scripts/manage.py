"""Only manage child processes belonging to this workspace."""
from pathlib import Path
import argparse, json, os, signal, subprocess, time
ROOT=Path(__file__).resolve().parents[1]
JAVA=os.environ.get('MINECRAFT_JAVA_BIN','/home/rhys/.local/share/hmcl/java/linux-x86_64/mojang-java-runtime-epsilon/bin/java')

def owned(name):
    try:
        pid=int((ROOT/f'runtime/{name}.pid').read_text())
        cmd=Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0',b' ').decode()
        cwd=Path(f'/proc/{pid}/cwd').resolve()
        if str(ROOT) in cmd or cwd.is_relative_to(ROOT):return pid
    except (OSError,ValueError):pass
    return None

def start(name,profile='balanced'):
    if owned(name):return
    cwd=ROOT
    args={
      'server':[JAVA,'-Xms1G','-Xmx4G','-Dfml.readTimeout=600','@java9args.txt','-jar','lwjgl3ify-forgePatches.jar','nogui'],
      'client':[str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/launch_game.py')],
      'model':['bash',str(ROOT/'scripts/serve_model.sh'),profile],
      'monitor':[str(ROOT/'.venv/bin/python'),str(ROOT/'src/monitor.py')]}[name]
    stdin=subprocess.DEVNULL
    if name=='server':
        cwd=ROOT/'instances/server'
        fifo=ROOT/'runtime/server.stdin'
        if not fifo.exists():os.mkfifo(fifo,0o600)
        stdin=os.open(fifo,os.O_RDWR)
    log=open(ROOT/f'logs/{name}.log','ab',buffering=0)
    p=subprocess.Popen(args,cwd=cwd,stdin=stdin,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    if isinstance(stdin,int) and stdin>=0:os.close(stdin)
    (ROOT/f'runtime/{name}.pid').write_text(str(p.pid));print('Started',name,p.pid)

def stop(name):
    pid=owned(name)
    if not pid:return
    fifo=ROOT/'runtime/server.stdin'
    if name=='server' and fifo.exists():
        fd=os.open(fifo,os.O_WRONLY|os.O_NONBLOCK);os.write(fd,b'stop\n');os.close(fd)
    else:os.kill(pid,signal.SIGTERM)
    deadline=time.monotonic()+45
    while owned(name) and time.monotonic()<deadline:time.sleep(.2)
    if owned(name):raise RuntimeError(f'{name} has not stopped; inspect logs before forcing termination')
    print('Stopped',name)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','stop','restart','status']);p.add_argument('component',choices=['all','server','client','model','monitor'],default='all',nargs='?');p.add_argument('--profile',choices=['cpu','balanced'],default='balanced');a=p.parse_args()
    (ROOT/'runtime').mkdir(exist_ok=True);(ROOT/'logs').mkdir(exist_ok=True)
    names=['server','client','model','monitor'] if a.component=='all' else [a.component]
    if a.action=='status':
        for n in names:print(n,owned(n))
        return
    if a.action in ('stop','restart'):
        for n in reversed(names):stop(n)
    if a.action in ('start','restart'):
        for n in names:start(n,a.profile)

if __name__=='__main__':main()
