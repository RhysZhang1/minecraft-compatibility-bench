"""Launch the copied GTNH installation without reading HMCL account credentials."""
from pathlib import Path
import json, os, re, subprocess, sys, uuid, zipfile
import shlex
from urllib.parse import urlparse,parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from game_config import config as game_config,client_options
import instance_config
SOURCE = instance_config.library_root()
CLIENT = instance_config.client_directory()
JAVA = Path(instance_config.java())

def manifest(path,seen=None):
    seen=set() if seen is None else seen
    if path in seen:raise ValueError('循环继承的客户端版本配置')
    seen.add(path);value=json.loads(path.read_text())
    if value.get('inheritsFrom'):
        parent=SOURCE/'versions'/value['inheritsFrom']/(value['inheritsFrom']+'.json')
        base=manifest(parent,seen)
        libs=base.get('libraries',[])+value.get('libraries',[])
        args={k:base.get('arguments',{}).get(k,[])+value.get('arguments',{}).get(k,[]) for k in ['jvm','game']}
        value={**base,**value,'libraries':libs,'arguments':args}
    return value

def allowed(rules):
    if not rules:
        return True
    result = False
    for r in rules:
        cond = r.get('os', {})
        if cond.get('name', 'linux') != 'linux':
            continue
        if cond.get('arch') and cond['arch'] not in ('x86_64', 'amd64'):
            continue
        if cond.get('version') and not re.search(cond['version'], os.uname().release):
            continue
        if r.get('features'):
            continue
        result = r['action'] == 'allow'
    return result

def main():
    resources=game_config()['client'];client_options(CLIENT/'options.txt')
    instance=instance_config.config();version=manifest(CLIENT/instance['client']['manifest'])
    natives = ROOT / 'runtime/natives'/instance['key']
    natives.mkdir(parents=True, exist_ok=True)
    cp = []
    missing = []
    # Match HMCL's inherited-library override semantics (e.g. Guava 17 replaces 15).
    selected = {}
    for lib in version['libraries']:
        if allowed(lib.get('rules', [])):
            parts=lib['name'].split(':')
            selected[(parts[0],parts[1],tuple(parts[3:]))]=lib['name']
    for lib in version['libraries']:
        if not allowed(lib.get('rules', [])):
            continue
        parts = lib['name'].split(':')
        group, artifact, ver = parts[:3]
        if selected[(group,artifact,tuple(parts[3:]))] != lib['name']:
            continue
        classifier = '-' + parts[3] if len(parts) > 3 else ''
        artifact_path=lib.get('downloads',{}).get('artifact',{}).get('path')
        p = SOURCE/'libraries'/(artifact_path or str(Path(group.replace('.', '/'))/artifact/ver/f'{artifact}-{ver}{classifier}.jar'))
        if not p.exists() and (CLIENT/'libraries'/p.name).exists():p=CLIENT/'libraries'/p.name
        if not p.exists():
            if lib.get('natives'):
                for osname, native_classifier in lib['natives'].items():
                    if osname != 'linux': continue
                    native_classifier=native_classifier.replace('${arch}','64')
                    np=p.parent/f'{artifact}-{ver}-{native_classifier}.jar'
                    if np.exists():
                        with zipfile.ZipFile(np) as z:
                            for name in z.namelist():
                                if name.endswith('.so'): (natives/Path(name).name).write_bytes(z.read(name))
                continue
            missing.append(str(p)); continue
        cp.append(str(p))
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if name.endswith('.so'):
                    (natives / Path(name).name).write_bytes(z.read(name))
        for osname, classifier in lib.get('natives', {}).items():
            if osname != 'linux': continue
            classifier = classifier.replace('${arch}', '64')
            np = p.parent/f'{artifact}-{ver}-{classifier}.jar'
            if np.exists():
                with zipfile.ZipFile(np) as z:
                    for name in z.namelist():
                        if name.endswith('.so'): (natives/Path(name).name).write_bytes(z.read(name))
    if missing:
        raise RuntimeError('Missing libraries: ' + '\n'.join(missing))
    cp.append(str(CLIENT/instance['client']['jar']))
    player=instance['player']
    replacements = {'natives_directory': str(natives), 'launcher_name': 'GameScaling-Minecraft',
       'launcher_version': '1', 'classpath': os.pathsep.join(cp), 'auth_player_name': player,
       'version_name': version['id'], 'game_directory': str(CLIENT),
       'library_directory':str(SOURCE/'libraries'),'libraries_directory':str(SOURCE/'libraries'),'classpath_separator':os.pathsep,'auth_session':'0',
       'assets_root': str(SOURCE/'assets'), 'assets_index_name': version['assetIndex']['id'],
       'auth_uuid': str(uuid.UUID(bytes=__import__('hashlib').md5(('OfflinePlayer:'+player).encode()).digest(),version=3)),
       'auth_access_token': '0', 'user_properties': '{}', 'user_type': 'legacy','clientid':'','auth_xuid':'','version_type':version.get('type','release')}
    def expand(v):
        for k,s in replacements.items(): v=v.replace('${'+k+'}',s)
        return v
    entry=instance['client'].get('main_class',version.get('mainClass',''))
    jvm = []
    for arg in version.get('arguments',{}).get('jvm',[]):
        if isinstance(arg, dict):
            if not allowed(arg['rules']): continue
            arg=arg['value']
        for a in arg if isinstance(arg,list) else [arg]:
            if a.startswith('-Dhmcl.mmc.bootstrap='):
                if entry=='org.jackhuang.hmcl.HMCLMultiMCBootstrap':
                    bootstrap=a.split('=',1)[1]
                    entry=parse_qs(urlparse(bootstrap).query).get('main_class',[bootstrap])[0]
                continue
            jvm.append(expand(a))
    game = [expand(a) for a in (version.get('arguments',{}).get('game') or shlex.split(version.get('minecraftArguments',''))) if isinstance(a,str)]
    if not jvm:jvm=['-Djava.library.path='+str(natives),'-cp',os.pathsep.join(cp)]
    if instance['backend']=='virtual-x11':
        # Force X11 into the private compositor even when the game supports Wayland.
        from virtual_display import environment
        os.environ.update(environment())
        os.environ['XDG_SESSION_TYPE']='x11';os.environ['SDL_VIDEODRIVER']='x11';os.environ['SDL_VIDEO_DRIVER']='x11';os.environ['SDL_VIDEO_X11_XINPUT2']='0'
        jvm=[a.replace(str(natives)+'/java',str(natives)) for a in jvm]
        sensor=[]
        if (ROOT/'runtime/client-bindings.properties').exists() and True:
            session=json.loads((ROOT/'runtime/bridge/session.json').read_text())['session']
            sensor=['-javaagent:'+str(ROOT/'sensors/gamescaling-sensors-agent.jar'),'-Dgamescaling.bindings='+str(ROOT/'runtime/client-bindings.properties'),'-Dgamescaling.session='+session,'-Dgamescaling.player='+player]
        cmd=[str(JAVA),*sensor,'-Dgamescaling.bridge='+str(ROOT/'runtime/bridge'),'-Xms'+resources['min_heap'],'-Xmx'+resources['max_heap'],*jvm,entry,*game,'--width','854','--height','480']
        if version.get('minecraftArguments') and instance['minecraft_version']=='1.7.10':cmd.extend(['--server',instance['connection']['host'],'--port',str(instance['connection']['port'])])
        else:cmd.extend(['--quickPlayMultiplayer',instance['connection']['host']+':'+str(instance['connection']['port'])])
        (ROOT/'runtime/client-launch.json').write_text(json.dumps(cmd,indent=2))
        os.chdir(CLIENT);os.execv(cmd[0],cmd)
    cmd = [str(JAVA), '-Xms'+resources['min_heap'],'-Xmx'+resources['max_heap'],'-Dfml.readTimeout=600',
           '-javaagent:'+str(ROOT/'input/gamescaling-input-agent.jar'),
           '-Dfml.ignoreInvalidMinecraftCertificates=true','-Dfml.ignorePatchDiscrepancies=true',
           '-Dminecraft.client.jar='+str(CLIENT/instance['client']['jar']),
           '-Dgamescaling.bridge='+str(ROOT/'runtime/bridge'),
           '-Dgamescaling.server.host='+instance['connection']['host'],
           '-Dgamescaling.server.port='+str(instance['connection']['port']),
           '-Dgamescaling.instance='+instance['key'],
           '-Dgamescaling.preview.fps='+str(resources.get('preview_fps',10)),
           '-Dorg.lwjgl.glfw.libname=glfw', *jvm,
           entry, *game,'--width','854','--height','480']
    (ROOT/'runtime/client-launch.json').write_text(json.dumps(cmd,indent=2))
    os.chdir(CLIENT)
    os.execv(cmd[0],cmd)

if __name__=='__main__': main()
