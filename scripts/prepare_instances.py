# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare configured private instances; never overwrite the original installation."""
from pathlib import Path
import json,os,shutil,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import instance_config
from server_console import configure
from game_config import client_options

def main():
    c=instance_config.config();bootstrap=c.get('bootstrap',{})
    for role in ['client','server']:
        if role=='server' and not c['server'].get('managed'):continue
        target=instance_config.path(c[role]['directory'])
        if not target.exists():
            source=bootstrap.get(role+'_source')
            if source:
                source=instance_config.path(source)
                if not source.is_dir():raise RuntimeError('实例来源不存在：'+str(source))
                if role=='server' and c.get('deployment_origin'):
                    import deployment
                    original=deployment.inspect_server(source,c['minecraft_version'])
                    if original['processes'] or original['listening']:raise RuntimeError('创建托管世界副本前必须停止原服务器；原件未复制或修改')
                shutil.copytree(source,target,ignore=shutil.ignore_patterns('logs','crash-reports','backups'))
            elif role=='server' and bootstrap.get('server_files'):
                sources={name:instance_config.path(p) for name,p in bootstrap['server_files'].items()}
                if not all(p.is_file() for p in sources.values()):raise RuntimeError('原版测试所需的现有服务端文件不齐全')
                target.mkdir(parents=True)
                for name,p in sources.items():shutil.copy2(p,target/name)
            else:raise RuntimeError('请先使用setup.sh导入客户端/服务器副本：'+str(target))
        print(role,target)
    if c['server'].get('managed'):
        p=instance_config.server_directory()/'server.properties'
        if not p.exists():p.write_text('')
        configure()
    p=instance_config.client_directory()/'options.txt'
    if not p.exists():p.write_text('lang:en_US\noverrideWidth:854\noverrideHeight:480\nenableVsync:false\npauseOnLostFocus:false\n')
    client_options(p)
    for d in ['runtime','logs','models']:(ROOT/d).mkdir(exist_ok=True)

if __name__=='__main__':main()
