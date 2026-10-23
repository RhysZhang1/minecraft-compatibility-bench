"""Manage only positively identified processes of this workspace, including stale PID recovery."""
from pathlib import Path
import argparse, json, os, signal, stat, subprocess, time, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from server_console import configure
import model_config
import instance_config
NAMES=('display','server','client','bridge','model','monitor')

def inspect(pid):
    try:
        base=Path('/proc')/str(pid)
        # A zombie no longer owns ports or GPU memory and cannot be signalled usefully.
        process_state=(base/'stat').read_text().rsplit(')',1)[1].split()[0]
        if process_state=='Z':return None
        argv=(base/'cmdline').read_bytes().decode().split('\0')
        cwd=(base/'cwd').resolve()
        return argv,cwd
    except (OSError,ValueError,UnicodeError):return None

def matches(name,argv,cwd):
    executable=Path(argv[0]).name if argv and argv[0] else ''
    def python_script(path):
        return executable.startswith('python') and len(argv)>1 and argv[1]==str(ROOT/path)
    if name=='server':
        if executable!='java' or '-jar' not in argv:return False
        return any(p.get('server',{}).get('managed') and cwd==instance_config.path(p['server']['directory'],ROOT)
            and argv.index('-jar')+1<len(argv) and argv[argv.index('-jar')+1]==p['server']['jar'] for p in instance_config.settings()['instances'].values())
    if name=='client':
        return python_script('scripts/launch_game.py') or (executable=='java' and '-Dgamescaling.bridge='+str(ROOT/'runtime/bridge') in argv)
    if name=='model':
        wrapper=executable=='bash' and len(argv)>1 and argv[1]==str(ROOT/'scripts/serve_model.sh')
        models=[str(ROOT/c['model']) for c in model_config.settings()['models'].values()]
        signature=any(path in argv for path in models) and all(value in argv for value in ['-m','--mmproj','--alias','gamescaling','--port','8789'])
        return wrapper or python_script('scripts/serve_model.py') or signature
    if name=='monitor':return python_script('src/monitor.py')
    if name=='display':return python_script('scripts/virtual_display.py')
    if name=='bridge':return python_script('scripts/virtual_bridge.py')
    if name=='switch':return python_script('scripts/switch_instance.py')
    return False

def owned_pids(name):
    found=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        info=inspect(int(p.name))
        if info and matches(name,*info):found.append(int(p.name))
    return sorted(found)

def owned(name):
    pids=owned_pids(name)
    return pids[0] if pids else None

def service_pids(name):
    pids=owned_pids(name)
    if name=='display' and pids:
        # The compositor intentionally launches a second copy in "publish" mode.
        # Treat that worker as part of the same service, not a duplicate start.
        roles={pid:inspect(pid)[0][2] for pid in pids if inspect(pid) and len(inspect(pid)[0])>2}
        leaders=[pid for pid,role in roles.items() if role=='serve']
        # KWin starts application workers in their own session; their PGID differs.
        if len(leaders)==1 and len(pids)<=2 and len(roles)==len(pids) and all(role in ('serve','publish') for role in roles.values()):pids=leaders
        else:raise RuntimeError('独立显示会话的主进程/工作进程不完整，请先运行 stop.sh 完整停止')
    return pids

def start(name,profile='balanced'):
    from game_config import config as game_config
    game=game_config()
    conf=instance_config.config();server=conf['server']
    if name=='server' and not server.get('managed'):return False
    pids=service_pids(name)
    if len(pids)>1:raise RuntimeError(f'{name} 有多个本项目进程，请先运行 stop.sh 完整停止')
    if pids:
        (ROOT/f'runtime/{name}.pid').write_text(str(pids[0]));return False
    if name=='client':
        # A just-stopped client's fresh snapshot must not make its replacement
        # appear connected before Forge has finished loading.
        (ROOT/'runtime/bridge/state.json').unlink(missing_ok=True)
    cwd=ROOT
    args={
      'display':[str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/virtual_display.py'),'serve'],
      'bridge':[str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/virtual_bridge.py')],
      'server':[instance_config.java(),'-Xms'+game['server']['min_heap'],'-Xmx'+game['server']['max_heap'],'-Dfml.readTimeout=600',*server.get('jvm_args',[]),'-jar',server['jar'],'nogui'],
      'client':[str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/launch_game.py')],
      'model':['bash',str(ROOT/'scripts/serve_model.sh'),profile],
      'monitor':[str(ROOT/'.venv/bin/python'),str(ROOT/'src/monitor.py')]}[name]
    stdin=subprocess.DEVNULL
    if name=='server':
        configure();cwd=instance_config.server_directory(ROOT);fifo=ROOT/'runtime/server.stdin'
        if fifo.exists() and not stat.S_ISFIFO(fifo.stat().st_mode):raise RuntimeError('runtime/server.stdin 不是命名管道')
        if not fifo.exists():os.mkfifo(fifo,0o600)
        stdin=os.open(fifo,os.O_RDWR)
    try:
        with open(ROOT/f'logs/{name}.log','ab',buffering=0) as log:
            p=subprocess.Popen(args,cwd=cwd,stdin=stdin,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    finally:
        if isinstance(stdin,int) and stdin>=0:os.close(stdin)
    (ROOT/f'runtime/{name}.pid').write_text(str(p.pid));print('已启动',name,p.pid,flush=True)
    return True

def signal_owned(name,pid,sig):
    info=inspect(pid)
    if not info or not matches(name,*info):return
    try:
        group=os.getpgid(pid)
        private_display_group=name=='display' and group!=os.getpgrp() and os.getsid(pid)==group
        if group==pid or private_display_group:os.killpg(group,sig)
        else:os.kill(pid,sig)
    except ProcessLookupError:pass

def wait_exit(name,timeout):
    deadline=time.monotonic()+timeout
    while owned_pids(name) and time.monotonic()<deadline:time.sleep(.2)
    return not owned_pids(name)

def stop(name,force=False):
    pids=owned_pids(name)
    if not pids:
        (ROOT/f'runtime/{name}.pid').unlink(missing_ok=True);return
    if name=='server':
        fifo=ROOT/'runtime/server.stdin'
        try:
            fd=os.open(fifo,os.O_WRONLY|os.O_NONBLOCK)
            try:os.write(fd,b'save-all\nstop\n')
            finally:os.close(fd)
        except OSError:
            # JVM shutdown hooks remain the fallback if the inherited console was lost.
            for pid in pids:signal_owned(name,pid,signal.SIGTERM)
        if not wait_exit(name,90):
            for pid in owned_pids(name):signal_owned(name,pid,signal.SIGTERM)
            wait_exit(name,30)
    else:
        for pid in pids:signal_owned(name,pid,signal.SIGTERM)
        wait_exit(name,15)
    remaining=owned_pids(name)
    if remaining and (name!='server' or force):
        for pid in remaining:signal_owned(name,pid,signal.SIGKILL)
        wait_exit(name,5)
    if owned_pids(name):
        raise RuntimeError(f'{name} 未正常退出。已保留进程避免中断世界保存；检查 logs/{name}.log，必要时运行 ./stop.sh --force')
    (ROOT/f'runtime/{name}.pid').unlink(missing_ok=True)
    print('已停止',name,flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','stop','restart','status']);p.add_argument('component',choices=['all',*NAMES],default='all',nargs='?');p.add_argument('--profile',choices=['cpu','balanced'],default='balanced');p.add_argument('--force',action='store_true');a=p.parse_args()
    (ROOT/'runtime').mkdir(exist_ok=True);(ROOT/'logs').mkdir(exist_ok=True)
    names=list(NAMES) if a.component=='all' else [a.component]
    if a.action=='status':
        for n in names:print(n,owned_pids(n))
        return
    if a.action in ('stop','restart'):
        for n in reversed(names):stop(n,a.force)
    if a.action in ('start','restart'):
        for n in names:start(n,a.profile)

if __name__=='__main__':main()
