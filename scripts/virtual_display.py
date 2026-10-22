"""Private headless Wayland compositor + Xwayland; never connects to desktop X11."""
from pathlib import Path
import argparse,json,os,signal,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
SESSION=ROOT/'runtime/virtual-session'
INFO=ROOT/'runtime/virtual-display.json'
def environment():
    data=json.loads(INFO.read_text())
    if data.get('XDG_RUNTIME_DIR')!=str(SESSION) or not data.get('DISPLAY','').startswith(':'):
        raise ValueError('拒绝连接不属于本项目的显示会话')
    # The compositor only publishes DISPLAY after spawning its own Xwayland.
    return {**os.environ,**data,'SDL_VIDEODRIVER':'x11','GLFW_PLATFORM':'x11'}
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['serve','publish']);a=p.parse_args()
    SESSION.mkdir(parents=True,exist_ok=True);SESSION.chmod(0o700)
    if a.action=='publish':
        keys=['DISPLAY','XAUTHORITY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME']
        value={k:os.environ[k] for k in keys if k in os.environ}
        tmp=INFO.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.chmod(0o600);tmp.replace(INFO)
        while True:time.sleep(60)
    INFO.unlink(missing_ok=True)
    env=dict(os.environ);env.pop('DISPLAY',None);env.pop('WAYLAND_DISPLAY',None)
    env['XDG_RUNTIME_DIR']=str(SESSION)
    for key,path in [('XDG_CONFIG_HOME',SESSION/'config'),('XDG_DATA_HOME',SESSION/'data'),('XDG_CACHE_HOME',ROOT/'.cache/virtual-display')]:
        path.mkdir(parents=True,exist_ok=True);env[key]=str(path)
    cmd=['dbus-run-session','--','kwin_wayland','--virtual','--width','854','--height','480','--xwayland','--socket','mc-wayland','--no-lockscreen','--no-global-shortcuts','--no-kactivities','--inputmethod','/usr/bin/true',__import__('shlex').join([sys.executable,str(Path(__file__).resolve()),'publish'])]
    child=subprocess.Popen(cmd,env=env)
    def stop(*args):
        child.terminate()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:raise SystemExit(child.wait())
    finally:INFO.unlink(missing_ok=True)
if __name__=='__main__':main()
