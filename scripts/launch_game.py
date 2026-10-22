"""Launch the copied GTNH installation without reading HMCL account credentials."""
from pathlib import Path
import json, os, re, subprocess, sys, uuid, zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('HMCL_GAME_ROOT','/home/rhys/.config/hmcl/.minecraft'))
CLIENT = ROOT / 'instances/client'
JAVA = Path(os.environ.get('MINECRAFT_JAVA_BIN','/home/rhys/.local/share/hmcl/java/linux-x86_64/mojang-java-runtime-epsilon/bin/java'))

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
    version = json.loads((CLIENT / 'GT New Horizons 2.8.4.json').read_text())
    natives = ROOT / 'runtime/natives'
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
        p = SOURCE/'libraries'/group.replace('.', '/')/artifact/ver/f'{artifact}-{ver}{classifier}.jar'
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
    cp.append(str(CLIENT/'GT New Horizons 2.8.4.jar'))
    replacements = {'natives_directory': str(natives), 'launcher_name': 'GameScaling-GTNH',
       'launcher_version': '1', 'classpath': os.pathsep.join(cp), 'auth_player_name': 'GameScalingBot',
       'version_name': version['id'], 'game_directory': str(CLIENT),
       'assets_root': str(SOURCE/'assets'), 'assets_index_name': version['assetIndex']['id'],
       'auth_uuid': str(uuid.UUID(bytes=__import__('hashlib').md5(b'OfflinePlayer:GameScalingBot').digest(),version=3)),
       'auth_access_token': '0', 'user_properties': '{}', 'user_type': 'legacy'}
    def expand(v):
        for k,s in replacements.items(): v=v.replace('${'+k+'}',s)
        return v
    jvm = []
    for arg in version['arguments']['jvm']:
        if isinstance(arg, dict):
            if not allowed(arg['rules']): continue
            arg=arg['value']
        for a in arg if isinstance(arg,list) else [arg]:
            if a.startswith('-Dhmcl.mmc.bootstrap='): continue
            jvm.append(expand(a))
    game = [expand(a) for a in version['arguments']['game'] if isinstance(a,str)]
    cmd = [str(JAVA), '-Xms1G','-Xmx6G','-Dfml.readTimeout=600',
           '-Dfml.ignoreInvalidMinecraftCertificates=true','-Dfml.ignorePatchDiscrepancies=true',
           '-Dminecraft.client.jar='+str(CLIENT/'GT New Horizons 2.8.4.jar'),
           '-Dgamescaling.bridge='+str(ROOT/'runtime/bridge'),
           '-Dorg.lwjgl.glfw.libname=glfw', *jvm,
           'com.gtnewhorizons.retrofuturabootstrap.Main', *game,'--width','854','--height','480']
    (ROOT/'runtime/client-launch.json').write_text(json.dumps(cmd,indent=2))
    os.chdir(CLIENT)
    os.execv(cmd[0],cmd)

if __name__=='__main__': main()
