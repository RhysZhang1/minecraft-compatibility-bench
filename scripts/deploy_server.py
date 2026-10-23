# SPDX-License-Identifier: GPL-3.0-or-later
"""Guided onboarding of an existing server; default is an unmanaged connection."""
from pathlib import Path
import argparse,copy,hashlib,json,os,re,shlex,shutil,subprocess,sys,time,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import deployment as deploy,instance_config as ic,local_environment as env,model_config
from agent_memory import AgentMemory,replace

def ask(text,default=''):
    return input(text+(' ['+str(default)+']' if str(default) else '')+': ').strip() or str(default)
def yes(text):return ask(text+' [y/N]').lower()=='y'
def run(args):return subprocess.run(list(map(str,args)),cwd=ROOT,check=True)
def private_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);replace(path,json.dumps(data,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)

def instance_id(server):
    ident=hashlib.sha256((server['directory']+'\0'+server['world_name']).encode()).hexdigest()[:8]
    return 'server-'+server['version'].replace('.','-')+'-'+ident

def java_path(version):
    required=deploy.JAVA[version];local=ROOT/'instances/java'/str(required)/'bin/java'
    candidates=[local]
    default=ic.settings()['instances'].get('vanilla-'+version.replace('.','-'),{})
    if default.get('java'):candidates.append(ic.path(default['java']))
    candidates.append(Path(env.java()))
    for path in candidates:
        if not path.is_file():continue
        try:
            p=subprocess.run([str(path),'-version'],capture_output=True,text=True,timeout=8)
            match=re.search(r'version "(\d+)(?:\.(\d+))?',p.stdout+p.stderr)
            major=int(match[2] if match and match[1]=='1' else match[1]) if match else 0
            if major>=required and (required!=8 or major==8):return str(path)
        except (OSError,subprocess.TimeoutExpired):pass
    return None

def client_spec(source,manifest,jar,libraries,version):
    source=Path(source).expanduser().resolve();libraries=Path(libraries).expanduser().resolve()
    for name in (manifest,jar):
        if Path(name).name!=name or not (source/name).is_file():raise ValueError('客户端清单/JAR须为目录内已有文件名')
    data=json.loads((source/manifest).read_text());actual=data.get('inheritsFrom') or data.get('id')
    if actual!=version:raise ValueError('客户端基础版本与服务器不一致；请提供相符的完整启动清单')
    if not (libraries/'libraries').is_dir() or not (libraries/'assets').is_dir():raise ValueError('客户端资源目录必须含libraries与assets')
    return {'source':str(source),'manifest':manifest,'jar':jar,'libraries_root':str(libraries)}

def profile_for(report,choices,existing=None):
    server=report['server'];version=server['version'];key=choices['key'];old=existing or {}
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key):raise ValueError('实例ID不合法')
    mode=choices.get('mode','attach');source=Path(server['directory']);origin=hashlib.sha256(str(source).encode()).hexdigest()
    if old and (old.get('deployment_origin')!=origin or old['server'].get('managed')!=(mode=='copy')):raise ValueError('此ID已用于另一服务器或管理方式；请使用新ID')
    client=choices.get('client') or {'source':str(ROOT/'instances'/('vanilla-'+version+'-client')),'manifest':version+'.json','jar':version+'.jar','libraries_root':'instances/vanilla-runtime'}
    model=choices['model'];option=next(o for o in report['model']['options'] if o['key']==model)
    if not option['fits_ram']:raise ValueError('预留服务器和客户端资源后内存不足，不能自动部署所选模型')
    placement=choices.get('profile',option['profile'])
    if placement not in ('balanced','cpu'):raise ValueError('推理方式无效')
    if placement=='balanced' and not option['gpu_fit_estimate']:raise ValueError('未获得足够可用显存，不自动启用全GPU模式')
    setting='config/vanilla-modern-server-settings.json' if version.startswith('26.') else 'config/vanilla-server-settings.json'
    managed=mode=='copy';directory='instances/deployed/'+key+'/server' if managed else str(source)
    connection=copy.deepcopy(server['connection'])
    srv={'managed':managed,'directory':directory,'settings':setting}
    bootstrap={'client_source':client['source']}
    if managed:
        if server.get('processes') or server.get('listening'):raise ValueError('复制世界前必须停止原服；原服仍在运行或端口仍监听')
        jar=choices.get('server_jar','server.jar')
        if Path(jar).name!=jar or not (source/jar).is_file():raise ValueError('需要原服目录内明确的服务端JAR')
        connection={'host':'127.0.0.1','port':int(choices['port'])}
        srv.update(jar=jar,jvm_args=choices.get('jvm_args',[]),rcon_port=int(choices['rcon_port']),resources={'min_heap':'1G','max_heap':str(max(2,int(server.get('max_heap_gib') or 4)))+'G'})
        if srv['rcon_port']==connection['port'] or not 1<=srv['rcon_port']<=65535:raise ValueError('副本端口无效或重复')
        if srv['rcon_port'] in (8789,8790) or connection['port'] in (8789,8790):raise ValueError('副本端口不能与模型/观察台端口重叠')
        bootstrap['server_source']=str(source)
    player=choices.get('player','GameScalingBot')
    identity=old.get('world_id') or str(uuid.uuid5(uuid.NAMESPACE_URL,'minecraft-gamescaling-agent:'+origin+':'+key))
    profile={'label':choices.get('label',source.name+' · '+version),'minecraft_version':version,'backend':'virtual-x11','world_id':identity,
        'deployment_origin':origin,'player':player,'initial_goal':choices['goal'],'connection':connection,'server':srv,'bootstrap':bootstrap,
        'java':choices.get('java') or str(ROOT/'instances/java'/str(deploy.JAVA[version])/'bin/java'),
        'client':{'directory':'instances/deployed/'+key+'/client','manifest':client['manifest'],'jar':client['jar'],'libraries_root':client['libraries_root'],
                  'resources':{'min_heap':'1G','max_heap':str(report['model']['client_heap_gib'])+'G','options':{'maxFps':60,'renderDistance':8,'rawMouseInput':False,'pauseOnLostFocus':False,'fullscreen':False}}},
        'memory_directory':'memory/sessions/'+key,'episodes_directory':'runtime/sessions/'+key+'/episodes','control_file':'runtime/sessions/'+key+'/control.json',
        'model':{'key':model,'profile':placement,'gpu_layers':99 if placement=='balanced' else 0,'vision_gpu':placement=='balanced','threads':min(6,report['host']['cpu_count'])}}
    if placement=='balanced':profile['model']['gpu_index']=report['model']['gpu_index']
    return ic.validate(key,profile)

def save_profile(report,choices):
    """Only writes AI configuration/memory, never the source server directory."""
    import manage
    if any(manage.owned_pids(n) for n in manage.NAMES):raise ValueError('配置前请先stop.sh；不会停止待接入的原服务器')
    p=ROOT/'local-instances.json';data=json.loads(p.read_text()) if p.exists() else {'instances':{}}
    key=choices['key'];existing=data['instances'].get(key)
    if choices.get('mode','attach')=='attach':
        for item in ic.settings()['instances'].values():
            if item['server'].get('managed') and ic.path(item['server']['directory']).resolve()==Path(report['server']['directory']).resolve():raise ValueError('此服务器已由本项目托管，请使用已有实例；不能同时登记为不接管的原服务器')
    if not existing and key in ic.settings()['instances']:raise ValueError('实例ID已存在，不覆盖内置实例')
    profile=profile_for(report,choices,existing)
    folder=ROOT/profile['memory_directory'];memory=AgentMemory(ROOT,folder,profile['world_id'])
    prompt=(ROOT/'config/agent-prompt.default.md').read_text()
    if len(choices['goal'])+len(prompt)+len(choices.get('notes',''))>2000:raise ValueError('目标、固定提示词和记忆笔记合计最多2000字')
    interval=choices.get('summary_interval',50)
    if not 10<=interval<=500:raise ValueError('记忆整理间隔应为10至500轮')
    # Validate ownership before writing profile or modifying memory.
    marker=deploy.safe_json(folder/'world.json')
    if marker and marker.get('world_id')!=profile['world_id']:raise ValueError('记忆目录属于另一世界')
    memory.ensure(choices['goal']);config=memory.config()
    memory.save_config({**config,'notes':choices.get('notes',config['notes']),'auto_summary':choices.get('auto_summary',True),'summary_interval':interval},choices['goal'])
    profile.pop('key',None);data['instances'][key]=profile;private_json(p,data)
    return profile

def ensure_environment(model,placement):
    python=ROOT/'.venv/bin/python';uv=shutil.which('uv')
    if not python.exists():
        if uv:run([uv,'venv','--python','3.11',ROOT/'.venv'])
        else:run([shutil.which('python3.11') or sys.executable,'-m','venv',ROOT/'.venv'])
    install=[uv,'pip','install','--python',python] if uv else [python,'-m','pip','install']
    run(install+['-r',ROOT/'requirements.txt','-r',ROOT/'requirements-hub.txt'])
    source=env.llama_source();binary=Path(env.llama_server())
    if not binary.is_file():
        import build_engine
        if placement=='balanced' and not shutil.which('nvcc'):raise ValueError('GPU构建缺少nvcc；请先准备CUDA toolkit或选择CPU模式，不安装显卡驱动')
        source=ROOT/'engines/llama.cpp';build_engine.build(source,cuda=placement=='balanced',jobs=2)
    conf=model_config.config(model)
    if model=='2b' and not all((ROOT/conf[k]).is_file() for k in ('model','vision','template')):run(install+['-r',ROOT/'requirements-conversion.txt'])
    run([sys.executable,ROOT/'scripts/download_sdk.py'])
    return python

def ensure_model(key,python):
    conf=model_config.config(key);needed=[ROOT/conf[n] for n in ('model','vision','template')]
    if not all(p.is_file() for p in needed):
        run(['bash',ROOT/'scripts/download_models.sh',key]);run([python,ROOT/('scripts/prepare_2b.py' if key=='2b' else 'scripts/normalize_gguf.py')])
    for path,digest in model_config.expected(conf).items():
        if not path.is_file():raise ValueError('模型准备不完整：'+str(path))
        h=hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(16*1024*1024),b''):h.update(chunk)
        if h.hexdigest()!=digest:raise ValueError('模型SHA256不一致：'+str(path))

def wizard(directory=None,version=None):
    if not directory:
        found=deploy.discover_servers(ask('在什么目录查找服务器（仅两层）',Path.cwd()))
        for i,p in enumerate(found,1):print(str(i)+'. '+p)
        chosen=ask('选择编号，或输入服务器目录')
        directory=found[int(chosen)-1] if chosen.isdigit() and 1<=int(chosen)<=len(found) else chosen
    server=deploy.inspect_server(directory,version)
    if not server['version']:
        version=ask('未能唯一识别，明确指定Minecraft版本（例1.20.1）');server=deploy.inspect_server(directory,version)
    report=deploy.plan(ROOT,server);print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['blockers']:raise ValueError('当前无法自动添加：'+'；'.join(report['blockers']))
    key=ask('新实例ID',instance_id(server));stored=deploy.safe_json(ROOT/'local-instances.json').get('instances',{}).get(key,{})
    choices={'key':key,'model':ask('选择模型（当前自动流程支持2b/9b）',report['model']['recommended'])}
    option=next((o for o in report['model']['options'] if o['key']==choices['model']),None)
    if not option or not option['fits_ram']:raise ValueError('模型未支持或内存预算不足')
    choices['profile']=ask('推理方式（cpu/balanced）',option['profile'])
    if choices['profile']=='balanced' and not option['gpu_fit_estimate']:raise ValueError('当前可用显存不足，不能自动选择GPU模式')
    choices['mode']='copy' if ask('1 接入现有服务器（保留原服运行） / 2 停服后创建托管副本','1')=='2' else 'attach'
    if choices['mode']=='copy':
        if server['processes'] or server['listening']:raise ValueError('请先停止原服再创建世界副本')
        choices.update(server_jar=ask('原服务端JAR文件名','server.jar'),jvm_args=shlex.split(ask('服务端额外JVM参数（留空可）')),port=int(ask('副本游戏端口','25570')),rcon_port=int(ask('副本本地命令端口','25590')))
    if server['loader'] in ('forge','neoforge','fabric') or yes('已有匹配客户端，需要导入而非下载原版？'):
        choices['client']=client_spec(ask('匹配的客户端版本目录'),ask('客户端JSON文件名'),ask('客户端JAR文件名'),ask('包含libraries/assets的资源根目录'),server['version'])
    choices['player']=ask('AI角色名（白名单需由服主允许）',stored.get('player','GameScalingBot'))
    memory=AgentMemory(ROOT,ROOT/'memory/sessions'/key,stored.get('world_id'));old=deploy.safe_json(memory.folder/'state.json')
    choices['goal']=ask('当前目标',old.get('goal',stored.get('initial_goal','Explore carefully and gather basic materials. Check each action result.')))
    choices['notes']=ask('长期笔记（留空则保留已保存内容）',memory.config()['notes'] if memory.folder.exists() else '')
    choices['auto_summary']=ask('自动整理记忆？y/n','y').lower()=='y';choices['summary_interval']=int(ask('每多少轮整理一次记忆（10至500）','50'))
    choices['java']=java_path(server['version'])
    profile_for(report,choices,stored)
    print('\n部署范围：系统依赖（如缺失且选择安装） → 项目Python → llama.cpp → 匹配客户端/Java → 模型下载/准备/校验 → 独立记忆 → 可选暂停启动。')
    print('原服务器文件与认证设置不会修改；接入模式不会接管原服启停。')
    if not yes('按以上方案添加？'):return
    import manage
    if any(manage.owned_pids(n) for n in manage.NAMES):raise ValueError('请先stop.sh后再配置；原服由原有方式运行')
    if report['missing_tools'] or report['missing_libraries'] or (report['host'].get('kwin_major') or 0)<6:
        command=report['system_install_command'];print('需要的系统包命令：'+(shlex.join(command) if command else '当前发行版未提供自动安装方案，请按环境检测补齐'))
        if not command or not yes('执行此系统依赖安装（可能需要sudo，不安装驱动、不升级发行版）？'):raise ValueError('已保留检测结果；补齐系统依赖后重跑')
        run(([shutil.which('sudo') or 'sudo'] if os.geteuid()!=0 else [])+command)
        refreshed=deploy.probe_host(ROOT)
        if any(not refreshed['tools'].get(k) for k in report['missing_tools']) or any(not refreshed['libraries'].get(k) for k in report['missing_libraries']) or (refreshed.get('kwin_major') or 0)<6:raise ValueError('系统依赖仍不完整或KWin过旧；不会自动升级发行版')
    journal=ROOT/'runtime/deployments'/(key+'.json')
    private_json(journal,{'time':time.time(),'state':'preparing','choices':choices,'report':report})
    try:
        python=ensure_environment(choices['model'],choices['profile'])
        if not choices['java']:
            run([sys.executable,ROOT/'scripts/install_java.py',deploy.JAVA[server['version']]]);choices['java']=java_path(server['version'])
        if not choices.get('client'):run([sys.executable,ROOT/'scripts/install_vanilla_client.py',server['version']])
        ensure_model(choices['model'],python)
        # Reinspect just before registering/copying, to catch changed auth or started worlds.
        current=deploy.inspect_server(directory,server['version'])
        if current['online_mode']:raise ValueError('原服认证设置已变化，停止添加')
        report=deploy.plan(ROOT,current)
        profile=save_profile(report,choices)
        private_json(journal,{'time':time.time(),'state':'configured','instance':key,'choices':choices,'report':report})
        print('配置已保存。启动命令：./start.sh --instance '+key+' --paused --no-open')
        print('网页：http://127.0.0.1:8790/；远程可从自己的电脑用SSH转发8790端口，默认不开放公网。')
        if yes('现在启动后台客户端和模型，并保持AI暂停？'):
            run([ROOT/'start.sh','--instance',key,'--paused','--no-open'])
            private_json(journal,{'time':time.time(),'state':'ready','instance':key,'choices':choices,'report':report})
    except BaseException as exc:
        private_json(journal,{'time':time.time(),'state':'incomplete','error':str(exc),'choices':choices,'report':report});raise

def main():
    p=argparse.ArgumentParser(description='给已有Minecraft服务器添加视觉AI玩家')
    p.add_argument('directory',nargs='?');p.add_argument('--version');p.add_argument('--inspect',action='store_true',help='只读检测并推荐，不下载或修改')
    p.add_argument('--scan',help='仅列出该目录内两层的服务器')
    a=p.parse_args()
    try:
        if a.scan:print(json.dumps(deploy.discover_servers(a.scan),ensure_ascii=False,indent=2))
        elif a.inspect:
            if not a.directory:raise ValueError('--inspect需要服务器目录')
            print(json.dumps(deploy.plan(ROOT,deploy.inspect_server(a.directory,a.version)),ensure_ascii=False,indent=2))
        else:wizard(a.directory,a.version)
    except (ValueError,OSError,subprocess.CalledProcessError,EOFError,KeyboardInterrupt) as exc:print('未完成：'+(str(exc) or '已取消'),file=sys.stderr);return 1
    return 0
if __name__=='__main__':sys.exit(main())
