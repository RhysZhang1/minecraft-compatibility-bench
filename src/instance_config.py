# SPDX-License-Identifier: GPL-3.0-or-later
"""Instance profiles: pack-independent connection, launch and per-world state."""
from pathlib import Path
import json,os,re
import local_environment
ROOT=Path(__file__).resolve().parents[1]
BACKENDS={'virtual-x11':{'minecraft_versions':['1.7.10','1.20.1','1.21.1','26.3'],'client_requirements':['Linux','KWin virtual backend','Xwayland'],'server_requirements':'Matching vanilla or modded protocol; server mod not required','input_isolation':True},'forge1710-lwjgl3ify':{'minecraft_versions':['1.7.10'],'client_requirements':['Forge 1.7.10','lwjgl3ify 2.1.x'],
    'server_requirements':'Matching protocol; no server bridge mod required','input_isolation':True}}

def path(value,root=None):
    p=Path(os.path.expandvars(str(value))).expanduser()
    return p if p.is_absolute() else (root or ROOT)/p

def settings():
    data=json.loads((ROOT/'instance-settings.json').read_text())
    private=ROOT/'local-instances.json'
    if private.exists():data['instances'].update(json.loads(private.read_text()).get('instances',{}))
    return data

def selected():
    if os.environ.get('MC_INSTANCE'):return os.environ['MC_INSTANCE']
    try:return json.loads((ROOT/'runtime/selected-instance.json').read_text())['instance']
    except (OSError,ValueError,KeyError):return settings()['selected']

def config(key=None):
    key=key or selected();all_settings=settings()['instances']
    if key not in all_settings:raise ValueError('未知游戏实例：'+str(key))
    return validate(key,all_settings[key])

def validate(key,profile):
    value={'key':key,**profile}
    backend=BACKENDS.get(value.get('backend'))
    if not backend or value.get('minecraft_version') not in backend['minecraft_versions']:
        raise ValueError('该客户端版本需要对应输入后端，不能仅改版本号复用：'+str(value.get('backend')))
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',key):raise ValueError('实例ID仅限字母数字、短横线和下划线')
    c=value['connection']
    if value['server'].get('managed') and c.get('host') not in ('127.0.0.1','localhost'):raise ValueError('本地托管测试服的客户端地址应为127.0.0.1；连接其他服务器请使用非托管配置')
    if not isinstance(c.get('port'),int) or not 1<=c['port']<=65535:raise ValueError('服务器端口无效')
    value.setdefault('world_id',key);value.setdefault('player','GameScalingBot')
    if not re.fullmatch(r'[a-zA-Z0-9_]{1,16}',value['player']):raise ValueError('离线玩家名无效')
    value.setdefault('memory_directory','memory/sessions/'+key)
    value.setdefault('episodes_directory','runtime/sessions/'+key+'/episodes')
    value.setdefault('control_file','runtime/sessions/'+key+'/control.json')
    value.setdefault('initial_goal','Observe your surroundings and follow the current objective.')
    return value

def select(key):
    config(key);p=ROOT/'runtime/selected-instance.json';p.parent.mkdir(exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps({'instance':key}));tmp.replace(p);os.environ['MC_INSTANCE']=key

def client_directory(root=None):return path(config()['client']['directory'],root)
def server_directory(root=None):return path(config()['server']['directory'],root)
def control_file():return path(config()['control_file'])
def episodes_directory():return path(config()['episodes_directory'])
def memory_directory():return path(config()['memory_directory'])
def managed():return config()['server'].get('managed',False)
def console_enabled():return managed() and config()['server'].get('rcon_port') is not None

def java():
    return str(path(config()['java'])) if config().get('java') and not os.environ.get('MINECRAFT_JAVA_BIN') else local_environment.java()

def library_root():return Path(os.environ.get('HMCL_GAME_ROOT',str(path(config()['client']['libraries_root']))))

def pack_rules():
    c=config();text=''
    if c.get('rules_file'):text=path(c['rules_file']).read_text().strip()
    if c.get('context_file') and path(c['context_file']).exists():
        context=json.loads(path(c['context_file']).read_text());hints=[]
        for quest in context.get('quests',[]):
            requirements=[]
            for task in quest['tasks']:
                requirements.extend(str(x['count'])+' '+(x['ore_dictionary'] or x['item']) for x in task['items'])
            hints.append(quest['title']+': '+', '.join(requirements))
        if hints:text+=' Existing instance requirements: '+'; '.join(hints)+'.'
    return text
