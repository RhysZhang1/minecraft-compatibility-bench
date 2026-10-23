# SPDX-License-Identifier: GPL-3.0-or-later
"""Cold start, readiness checks and complete project shutdown (Linux desktop)."""
from pathlib import Path
import argparse, contextlib, fcntl, hashlib, json, os, shutil, signal, socket, subprocess, sys, time
from urllib.request import Request, ProxyHandler, build_opener
import manage
import model_config
import instance_config
import local_environment

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'runtime'
URL='http://127.0.0.1:8790'
PORTS={'server':(25565,25575),'model':(8789,),'monitor':(8790,)}
OPENER=build_opener(ProxyHandler({}))
LABELS={'server':'测试服务器','client':'隐藏游戏客户端','model':'本地模型','monitor':'8790观察台','display':'独立虚拟显示会话','bridge':'通用画面与输入通道'}
STOP_REQUEST=RUNTIME/'stop.request'

def say(message):
    line=time.strftime('[%H:%M:%S] ')+message
    print(line,flush=True)
    try:
        with (ROOT/'logs/lifecycle.log').open('a') as log:log.write(line+'\n')
    except OSError:pass

def http(url,body=None,timeout=3):
    req=Request(url,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with OPENER.open(req,timeout=timeout) as response:return json.load(response)

def load(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}

def save_control(enabled):
    p=instance_config.control_file();p.parent.mkdir(parents=True,exist_ok=True);value=load(p);value['enabled']=enabled
    tmp=p.with_suffix('.lifecycle.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False));tmp.replace(p)
    if manage.owned('monitor'):
        try:http(URL+'/api/control',{'enabled':enabled})
        except (OSError,ValueError):
            if enabled:raise RuntimeError('观察台未确认恢复自动操作')

def cancelled():
    if STOP_REQUEST.exists():raise InterruptedError('收到停止请求，正在收回本次启动的进程')

@contextlib.contextmanager
def lifecycle_lock(action):
    with (RUNTIME/'lifecycle.lock').open('a') as handle:
        deadline=time.monotonic()+180
        waiting=False
        while True:
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if action=='start':raise RuntimeError('另一启动或停止脚本正在运行，请等待其完成')
                if not waiting:say('正在请求取消尚未完成的启动，并等待它释放资源…');waiting=True
                if time.monotonic()>deadline:raise RuntimeError('等待启停锁超时，请查看正在运行的启动终端')
                time.sleep(.5)
        try:yield
        finally:fcntl.flock(handle,fcntl.LOCK_UN)

def run(args):
    cancelled();child=subprocess.Popen(list(map(str,args)),cwd=ROOT,start_new_session=True)
    try:
        while child.poll() is None:cancelled();time.sleep(.2)
        if child.returncode:raise subprocess.CalledProcessError(child.returncode,args)
        cancelled()
    except BaseException:
        if child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
        raise

def preflight():
    import prepare_release
    prepare_release.prepare()
    cancelled()
    instance=instance_config.config();client=instance_config.client_directory();server=instance_config.server_directory()
    if instance['backend']=='forge1710-lwjgl3ify' and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        raise RuntimeError('需要在已登录的桌面会话中启动隐藏游戏客户端')
    for tool in [instance_config.java(),local_environment.llama_server()]:
        if not os.access(tool,os.X_OK):raise RuntimeError('缺少可执行程序：'+tool)
    if not client.is_dir() or (instance_config.managed() and not server.is_dir()):
        if manage.owned('client') or manage.owned('server'):raise RuntimeError('实例不完整，请先完全停止后再初始化')
        say('首次准备独立测试副本…');run([sys.executable,ROOT/'scripts/prepare_instances.py'])
    if instance_config.managed():
        from vanilla_servers import require_eula
        require_eula(server/'eula.txt')
    python=ROOT/'.venv/bin/python'
    if not python.exists():
        uv=shutil.which('uv')
        if not uv:raise RuntimeError('缺少本地Python环境及uv，请按README先准备运行环境')
        say('创建本项目的Python环境…');run([uv,'venv','--python','3.11',ROOT/'.venv'])
    checked=subprocess.run([str(python),'-c','import PIL,requests,psutil,jinja2'],capture_output=True)
    if checked.returncode:
        uv=shutil.which('uv')
        if not uv:raise RuntimeError('Python依赖不完整，请按README安装requirements.txt')
        say('补齐本项目的Python依赖…');run([uv,'pip','install','--python',python,'-r',ROOT/'requirements.txt'])
    conf=model_config.config();model=ROOT/conf['model'];folder=model.parent
    original=folder/'GameScaling-9B-S1.Q4_K_M.gguf'
    if conf['key']=='9b' and not model.exists() and original.exists():
        say('生成兼容模型副本并验证张量一致性…');run([python,ROOT/'scripts/normalize_gguf.py'])
    expected=model_config.expected(conf)
    cache=load(RUNTIME/'model-verification.json')
    for path,digest in expected.items():
        if not path.is_file() or not digest:
            raise RuntimeError('模型文件或校验记录缺失：'+str(path)+'；请恢复本地备份或按README下载并准备模型')
        info=path.stat();fingerprint={'size':info.st_size,'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns,'sha256':digest}
        if cache.get(path.name)!=fingerprint:
            say('校验模型文件：'+path.name)
            h=hashlib.sha256()
            with path.open('rb') as source:
                for block in iter(lambda:source.read(16*1024*1024),b''):cancelled();h.update(block)
            if h.hexdigest()!=digest:raise RuntimeError('模型校验失败，请从备份恢复：'+str(path))
            cache[path.name]=fingerprint
    (RUNTIME/'model-verification.json').write_text(json.dumps(cache,indent=2))
    java_probe=subprocess.run([instance_config.java(),'-version'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=10)
    import re
    match=re.search(r'version "([0-9]+)(?:\.([0-9]+))?',java_probe.stdout)
    actual=int(match.group(2) if match and match.group(1)=='1' else match.group(1)) if match else None
    metadata=load(client/instance['client']['manifest']);required=metadata.get('javaVersion',{}).get('majorVersion',8)
    if actual is None or actual<required:raise RuntimeError('客户端要求Java '+str(required)+'或更新版本，请在setup.sh安装/配置对应运行时')
    needed=[ROOT/conf['template'],client/instance['client']['manifest'],client/instance['client']['jar']]
    if instance_config.managed():
        needed.append(server/instance['server']['jar'])
        needed.extend(server/a[1:] for a in instance['server'].get('jvm_args',[]) if a.startswith('@'))
    for path in needed:
        if not path.is_file():raise RuntimeError('缺少启动资源：'+str(path))
    jars=[client/'mods/GameScalingBridge-1.0.jar',ROOT/'input/gamescaling-input-agent.jar',ROOT/'input/gamescaling-input-state.jar']
    sources=[*ROOT.glob('bridge/src/**/*.java'),*ROOT.glob('input/src/**/*.java'),ROOT/'scripts/build_input.py',ROOT/'scripts/build_bridge.py']
    if instance['backend']=='forge1710-lwjgl3ify' and (any(not p.exists() for p in jars) or max(p.stat().st_mtime_ns for p in sources)>min(p.stat().st_mtime_ns for p in jars)):
        if manage.owned('client'):raise RuntimeError('桥接需要重新编译，请先运行stop.sh再启动')
        if not shutil.which('javac') or not shutil.which('jar'):raise RuntimeError('编译桥接需要已安装的JDK（javac、jar）')
        say('编译游戏桥接及后台输入隔离…');run([python,ROOT/'scripts/build_bridge.py'])
    if instance['backend']=='virtual-x11':
        for tool in ['kwin_wayland','Xwayland','dbus-run-session']:
            if not shutil.which(tool):raise RuntimeError('独立虚拟显示需要 '+tool+'；请在setup.sh环境检测中查看')
        native=ROOT/'input/libgamescaling-ei.so'
        if not native.exists() or (ROOT/'input/ei.c').stat().st_mtime_ns>native.stat().st_mtime_ns:run([python,ROOT/'scripts/build_virtual_input.py'])
        import client_bindings
        if client_bindings.prepare():
            sensor=ROOT/'sensors/gamescaling-sensors-agent.jar'
            if not sensor.exists() or any(p.stat().st_mtime_ns>sensor.stat().st_mtime_ns for p in ROOT.glob('sensors/src/**/*.java')):
                run([python,ROOT/'scripts/build_sensors.py'])
    if instance.get('context_extractor') and not instance_config.path(instance['context_file']).exists():run([python,instance_config.path(instance['context_extractor'])])
    ports_to_check={**PORTS,'server':(instance['connection']['port'],instance['server'].get('rcon_port',25575)) if instance_config.managed() else ()}
    for name,ports in ports_to_check.items():
        if manage.owned_pids(name):continue
        for port in ports:
            with socket.socket() as sock:
                sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                try:sock.bind(('127.0.0.1',port))
                except OSError:raise RuntimeError(f'端口{port}被其他进程占用；未启动，也未终止该进程')
    if shutil.disk_usage(ROOT).free<2*1024**3:raise RuntimeError('工作区可用磁盘空间不足2GiB')

def wait_ready(label,check,roles,timeout):
    say('等待'+label+'…');deadline=time.monotonic()+timeout;last_notice=time.monotonic();last_error=''
    while time.monotonic()<deadline:
        cancelled()
        for role in roles:
            if not manage.owned(role):raise RuntimeError(LABELS[role]+'提前退出，请查看 logs/'+role+'.log')
        try:
            result=check()
            if result:say(label+'已就绪');return result
        except (OSError,ValueError,KeyError) as exc:last_error=str(exc)
        if time.monotonic()-last_notice>20:
            say(label+'仍在准备，请稍候…');last_notice=time.monotonic()
        time.sleep(1)
    raise TimeoutError(label+'就绪超时。'+last_error)

def shutdown(force=False,only=None):
    errors=[]
    try:save_control(False)
    except Exception as exc:say('无法写入暂停状态，继续停止进程：'+str(exc))
    if manage.owned('monitor') and (only is None or 'monitor' in only):
        try:
            http(URL+'/api/memory/checkpoint',{},timeout=8);say('续玩笔记已保存。')
        except (OSError,ValueError):say('未取得最新记忆确认，保留最近自动保存的续玩笔记。')
    for name in ['monitor','bridge','client','server','model','display']:
        if only is not None and name not in only:continue
        if manage.owned(name):say('停止'+LABELS[name]+('并保存世界…' if name=='server' else '…'))
        try:manage.stop(name,force)
        except Exception as exc:errors.append(str(exc))
    if only is None:
        import vanilla_servers
        try:vanilla_servers.stop_all(force)
        except Exception as exc:errors.append(str(exc))
    return errors

def stopped_ports():
    result=[]
    ports={8789,8790}
    for profile in instance_config.settings()['instances'].values():
        if profile['server'].get('managed'):
            ports.add(profile['connection']['port'])
            if profile['server'].get('rcon_port'):ports.add(profile['server']['rcon_port'])
    import vanilla_servers
    for profile in vanilla_servers.registry().values():ports.update((profile['port'],profile['rcon_port']))
    for port in sorted(ports):
        with socket.socket() as sock:
            sock.settimeout(.3)
            if sock.connect_ex(('127.0.0.1',port))==0:result.append(port)
    return result

def apply_model_preference(args):
    preference=instance_config.config().get('model',{})
    explicit_profile=args.profile
    if args.model:model_config.select(args.model)
    elif preference.get('key'):model_config.select(preference['key'])
    args.profile=args.profile or preference.get('profile','balanced')
    if preference.get('key')==model_config.selected():
        if 'threads' in preference:os.environ.setdefault('MODEL_THREADS',str(preference['threads']))
        if explicit_profile is None or explicit_profile==preference.get('profile'):
            if 'gpu_layers' in preference:os.environ.setdefault('MODEL_GPU_LAYERS',str(preference['gpu_layers']))
            if 'vision_gpu' in preference:os.environ.setdefault('MODEL_VISION_GPU','1' if preference['vision_gpu'] else '0')
        if args.profile!='cpu' and preference.get('gpu_index') is not None:os.environ.setdefault('CUDA_VISIBLE_DEVICES',str(preference['gpu_index']))

def cold_start(args):
    started=[]
    STOP_REQUEST.unlink(missing_ok=True)
    try:
        apply_model_preference(args)
        say('启动实例：'+instance_config.config()['label']);say('检查运行环境、模型及启动资源…');preflight()
        if manage.owned('model'):
            argv,_=manage.inspect(manage.owned('model'))
            current_cpu='--device' in argv and argv[argv.index('--device')+1]=='none'
            if current_cpu!=(args.profile=='cpu'):
                raise RuntimeError('已运行模型的CPU/GPU配置不同，请先stop.sh再按所选配置启动')
            if str(ROOT/model_config.config()['model']) not in argv:
                raise RuntimeError('正在运行另一个大小的模型，请先停止模型服务或stop.sh再切换')
        save_control(False)
        if instance_config.config()['backend']=='virtual-x11':
            if manage.start('display'):started.append('display')
            wait_ready('独立虚拟显示会话',lambda:load(RUNTIME/'virtual-display.json').get('DISPLAY'),['display'],60)
            if manage.start('bridge'):started.append('bridge')
        for name in (['server'] if instance_config.managed() else [])+['model']:
            if manage.start(name,args.profile):started.append(name)
            else:say('复用已运行的'+LABELS[name])
        sys.path.insert(0,str(ROOT/'src'));import server_console
        if instance_config.console_enabled():wait_ready('测试服务器和命令接口',lambda:server_console.execute('list'),['server'],args.timeout)
        wait_ready('本地模型',lambda:http('http://127.0.0.1:8789/health').get('status')=='ok',['model'],args.timeout)
        for name in ['monitor','client']:
            if manage.start(name,args.profile):started.append(name)
            else:say('复用已运行的'+LABELS[name])
        def ready():
            value=http(URL+'/api/status');game=value.get('game',{})
            return value if game.get('connected') and game.get('schema_version')==2 and game.get('instance')==instance_config.selected() and game.get('input_isolated') and game.get('window_visible') is False and value.get('console',{}).get('settings_applied') else None
        status=wait_ready('隐藏客户端连接及观察台',ready,(['server'] if instance_config.managed() else [])+['model','client','monitor'],args.timeout)
        save_control(not args.paused)
        report={'time':time.time(),'result':'ready','instance':instance_config.selected(),'profile':args.profile,'model':model_config.selected(),'auto_enabled':not args.paused,
                'processes':{name:manage.owned_pids(name) for name in manage.NAMES},'game':status['game']}
        (RUNTIME/'last-start.json').write_text(json.dumps(report,indent=2))
        say('全部就绪：'+URL+('（自动操作已暂停）' if args.paused else '（自动操作已开启）'))
        say('完全停止：'+str(ROOT/'stop.sh'))
        if not args.no_open:
            opener=shutil.which('xdg-open')
            if opener:
                with open(os.devnull,'wb') as sink:subprocess.Popen([opener,URL],stdout=sink,stderr=sink,start_new_session=True)
            else:say('请在浏览器打开上述观察台地址')
    except BaseException:
        if started:
            say('启动未完成，清理本次新启动的服务…')
            for message in shutdown(only=started):say(message)
        raise

def complete_stop(args):
    errors=shutdown(args.force)
    left={name:manage.owned_pids(name) for name in manage.NAMES}
    if any(left.values()):errors.append('仍有本项目进程：'+json.dumps(left))
    ports=stopped_ports()
    report={'time':time.time(),'result':'stopped' if not errors else 'incomplete','processes':left,'listening_ports':ports,'errors':errors}
    (RUNTIME/'last-stop.json').write_text(json.dumps(report,indent=2))
    STOP_REQUEST.unlink(missing_ok=True)
    if errors:raise RuntimeError('\n'.join(errors))
    say('本项目已完全停止，Java客户端/服务器、模型和观察台均已退出。')
    if ports:say('以下端口仍由其他进程占用，已保留：'+str(ports))
    else:say('已登记的本地服务端口均已释放；存档、模型及日志已保留。')

def main():
    parser=argparse.ArgumentParser(description='Minecraft × GameScaling 一键启停')
    parser.add_argument('action',choices=['start','stop','status'])
    parser.add_argument('--instance',help='选择游戏实例；切换前先正常停止游戏服务')
    parser.add_argument('--model',choices=['2b','9b'],help='选择并记住模型；默认2b，9b保留可切换')
    parser.add_argument('--profile',choices=['balanced','cpu'],default=None,help='未指定时优先使用实例推荐配置；旧实例默认balanced')
    parser.add_argument('--paused',action='store_true',help='全部就绪后保持自动操作暂停')
    parser.add_argument('--no-open',action='store_true',help='不自动打开浏览器')
    parser.add_argument('--timeout',type=int,default=600,help='每阶段就绪等待秒数，默认600')
    parser.add_argument('--force',action='store_true',help='服务器在正常停止及JVM关闭均超时后也强制终止')
    args=parser.parse_args()
    RUNTIME.mkdir(exist_ok=True);(ROOT/'logs').mkdir(exist_ok=True)
    if args.action=='status':
        for name in manage.NAMES:say(LABELS[name]+'：'+str(manage.owned_pids(name)))
        return
    def terminate(*unused):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,terminate)
    if args.action=='stop':
        STOP_REQUEST.touch()
        if os.environ.get('MC_SWITCH_CHILD')!='1':
            for pid in manage.owned_pids('switch'):manage.signal_owned('switch',pid,signal.SIGTERM)
    try:
        with lifecycle_lock(args.action):
            if args.instance and args.instance!=instance_config.selected():
                if args.action!='start':raise RuntimeError('停止操作只作用于当前实例，请不要同时切换实例')
                if any(manage.owned_pids(n) for n in ['server','client','monitor']):raise RuntimeError('切换实例前先运行stop.sh，避免将旧世界状态带入新实例')
                instance_config.select(args.instance)
            if args.action=='start':cold_start(args)
            else:complete_stop(args)
    except (Exception,KeyboardInterrupt) as exc:
        say('未完成：'+(str(exc) or '收到中断请求'));return 1
    return 0

if __name__=='__main__':sys.exit(main())
