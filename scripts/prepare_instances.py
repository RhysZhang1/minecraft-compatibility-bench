"""Copy user-provided installations into private, reproducible test instances."""
from pathlib import Path
import json,os,shutil,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from server_console import configure
from game_config import client_options

def main():
    sources={'server':Path(os.environ.get('GTNH_SERVER_SOURCE','/home/rhys/Desktop/GTNH')),
             'client':Path(os.environ.get('GTNH_CLIENT_SOURCE','/home/rhys/.config/hmcl/.minecraft/versions/GT New Horizons 2.8.4'))}
    for role,source in sources.items():
        target=ROOT/'instances'/role
        if not target.exists():shutil.copytree(source,target,ignore=shutil.ignore_patterns('logs','crash-reports','backups'))
        print(role,target)
    p=ROOT/'instances/server/server.properties'
    lines=p.read_text().splitlines();changes={'server-ip':'127.0.0.1','server-port':'25565','difficulty':'0'}
    for k,v in changes.items():
        lines=[x for x in lines if not x.startswith(k+'=')];lines.append(k+'='+v)
    p.write_text('\n'.join(lines)+'\n')
    configure()
    p=ROOT/'instances/client/options.txt'
    if not p.exists():p.write_text('lang:en_US\noverrideWidth:854\noverrideHeight:480\nenableVsync:false\npauseOnLostFocus:false\nshowInventoryAchievementHint:false\nmusic:0.0\nsound:0.3\n')
    client_options(p)
    for d in ['runtime','logs','models']:(ROOT/d).mkdir(exist_ok=True)

if __name__=='__main__':main()
