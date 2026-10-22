"""Inspect, select or import an installed compatible client/server pair."""
import argparse,json,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import instance_config as ic
import manage

def idle():
    if any(manage.owned_pids(n) for n in ('server','client','monitor')):
        raise ValueError('请先运行stop.sh，实例切换和导入只在完全停止游戏后进行')
def register(value):
    idle();key=value.pop('key');ic.config()  # validate current registry before changing it
    if key in ic.settings()['instances']:raise ValueError('实例ID已存在；不会覆盖原配置')
    p=ROOT/'local-instances.json'
    current=json.loads(p.read_text()) if p.exists() else {'instances':{}}
    current['instances'][key]=value
    # Validate before publishing the candidate, including backend support.
    import unittest.mock
    merged=ic.settings();merged['instances'][key]=value
    with unittest.mock.patch.object(ic,'settings',return_value=merged):ic.config(key)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n');tmp.chmod(0o600);tmp.replace(p)
    return key

def import_interactive():
    print('默认使用独立虚拟显示通道。已测试原版：1.7.10、1.20.1、1.21.1、26.3；整合包还需验证其启动清单。')
    key=input('新实例ID（字母、数字、下划线或短横线）: ').strip()
    label=input('显示名称: ').strip() or key
    source=Path(input('现有客户端版本目录（会复制，原件不修改）: ').strip()).expanduser().resolve()
    manifests=sorted(source.glob('*.json'))
    print('目录中的JSON：'+', '.join(p.name for p in manifests))
    manifest=input('版本JSON文件名: ').strip()
    jar=input('客户端JAR文件名: ').strip()
    meta=json.loads((source/manifest).read_text());suggested=meta.get('inheritsFrom',meta.get('id','1.20.1'))
    version=input('Minecraft基础版本 ['+suggested+']: ').strip() or suggested
    backend='forge1710-lwjgl3ify' if input('使用现有GTNH/lwjgl3ify专用后端？[y/N]: ').lower()=='y' else 'virtual-x11'
    libs=Path(input('HMCL .minecraft目录（包含libraries和assets）: ').strip()).expanduser().resolve()
    for p in (source/manifest,source/jar,libs/'libraries'):
        if not p.exists():raise ValueError('路径不存在：'+str(p))
    host=input('服务器地址 [127.0.0.1]: ').strip() or '127.0.0.1'
    port=int(input('游戏端口 [25565]: ').strip() or 25565)
    local=input('是否托管本地服务器副本？[y/N]: ').lower()=='y'
    value={'key':key,'label':label,'minecraft_version':version,'backend':backend,
           'world_id':str(uuid.uuid4()),'player':'GameScalingBot',
           'client':{'directory':'instances/'+key+'-client','manifest':manifest,'jar':jar,'libraries_root':str(libs)},
           'server':{'managed':local,'directory':'instances/'+key+'-server'},
           'connection':{'host':host,'port':port},'bootstrap':{'client_source':str(source)}}
    if local:
        server=Path(input('原服务器目录（复制到工作区）: ').strip()).expanduser().resolve()
        if not server.is_dir():raise ValueError('服务器目录不存在')
        value['bootstrap']['server_source']=str(server)
        value['server'].update(jar=input('服务器JAR文件名: ').strip(),jvm_args=input('额外JVM参数（如 @java9args.txt；空格分隔）: ').split(),
                               settings='config/vanilla-server-settings.json',rcon_port=int(input('本地RCON端口 [25575]: ').strip() or 25575))
    register(value);print('已登记：'+key+'。可用 ./start.sh --instance '+key+' --paused 启动。')

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['list','select','import']);p.add_argument('key',nargs='?');a=p.parse_args()
    if a.action=='list':
        for key,item in ic.settings()['instances'].items():
            print(('* ' if key==ic.selected() else '  ')+key+' | '+item['label']+' | '+item['minecraft_version']+' | '+item['backend'])
    elif a.action=='select':idle();ic.select(a.key);print('当前实例：'+ic.selected())
    else:import_interactive()
if __name__=='__main__':main()
