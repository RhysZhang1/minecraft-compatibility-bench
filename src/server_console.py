"""Minecraft RCON, restricted to this workspace's loopback test server."""
from pathlib import Path
import json, re, secrets, socket, struct, threading
import instance_config

ROOT=Path(__file__).resolve().parents[1]
def properties_path():return instance_config.server_directory()/'server.properties'
CONSOLE_LOCK=threading.RLock()

def properties(source=None):
    return dict(line.split('=',1) for line in (source or properties_path()).read_text().splitlines()
                if line and not line.startswith(('#','!')) and '=' in line)

def defaults():
    conf=instance_config.config()['server'];return json.loads(instance_config.path(conf.get('settings','server-settings.json')).read_text())

def configure():
    """Called before server start; the random credential stays in the private instance."""
    with CONSOLE_LOCK:
        if not instance_config.console_enabled():return
        current=properties()
        connection=instance_config.config()['connection']
        changes={**defaults()['properties'],'server-ip':'127.0.0.1','enable-rcon':'true',
                 'server-port':str(connection['port']),'rcon.port':str(instance_config.config()['server']['rcon_port']),
                 'rcon.password':current.get('rcon.password') or secrets.token_hex(32)}
        if instance_config.config()['minecraft_version']!='1.7.10' and changes.get('difficulty')=='0':changes['difficulty']='peaceful'
        lines=properties_path().read_text().splitlines()
        lines=[line for line in lines if line.split('=',1)[0] not in changes]
        properties_path().write_text('\n'.join(lines+[k+'='+v for k,v in changes.items()])+'\n')

def validate(command):
    if not isinstance(command,str):raise ValueError('请输入一条 Minecraft 服务器命令')
    command=command.strip().removeprefix('/')
    if not command or len(command.encode('utf-8'))>2048 or any(ord(c)<32 or ord(c)==127 for c in command):
        raise ValueError('请输入单行命令，最多2048字节')
    return command

def packet(ident,kind,body):
    data=struct.pack('<ii',ident,kind)+body+b'\0\0'
    return struct.pack('<i',len(data))+data

def exact(sock,size):
    data=bytearray()
    while len(data)<size:
        chunk=sock.recv(size-len(data))
        if not chunk:raise ConnectionError('服务器已关闭命令连接')
        data.extend(chunk)
    return bytes(data)

def receive(sock):
    size=struct.unpack('<i',exact(sock,4))[0]
    if not 10<=size<=4*1024*1024:raise ConnectionError('服务器返回的命令数据长度无效')
    data=exact(sock,size)
    if data[-2:]!=b'\0\0':raise ConnectionError('服务器返回的命令数据不完整')
    ident,kind=struct.unpack('<ii',data[:8])
    return ident,kind,data[8:-2]

def execute(command,source=None):
    command=validate(command)
    with CONSOLE_LOCK:
        p=properties(source) if source else properties()
        if p.get('enable-rcon')!='true' or not p.get('rcon.password'):
            raise ConnectionError('服务器命令服务尚未配置，请重启测试服务器')
        with socket.create_connection(('127.0.0.1',int(p.get('rcon.port','25575'))),timeout=8) as sock:
            sock.sendall(packet(1,3,p['rcon.password'].encode()))
            ident,kind,_=receive(sock)
            if ident!=1 or kind!=2:raise ConnectionError('服务器命令身份验证失败')
            # A separate response-value probe delimits multi-packet command output.
            # 1.7.10 rejects coalesced request packets: wait for the first reply
            # before sending the delimiter, rather than pipelining both writes.
            sock.sendall(packet(2,2,command.encode('utf-8')))
            output=bytearray()
            probed=False
            while True:
                ident,kind,body=receive(sock)
                if ident==3:break
                if ident!=2 or kind!=0:raise ConnectionError('服务器命令响应编号不匹配')
                output.extend(body)
                if len(output)>1024*1024:raise ConnectionError('命令输出超过1MiB，请缩小查询范围')
                if not probed:
                    sock.sendall(packet(3,0,b''));probed=True
            return re.sub(r'§[0-9a-fk-or]','',output.decode('utf-8',errors='replace'),flags=re.I)

def apply_defaults():
    with CONSOLE_LOCK:
        results=[{'command':c,'output':execute(c)} for c in defaults()['commands']]
        query=defaults().get('verify_keep_inventory','gamerule keepInventory')
        results.append({'command':query,'output':execute(query)})
        results.append({'command':'save-all','output':execute('save-all')})
        for r in results:
            if any(word in r['output'] for word in ['Incorrect argument','Unknown or incomplete command','Unknown game rule']):raise ValueError('服务器未接受设置：'+r['command']+' / '+r['output'])
        if 'true' not in results[-2]['output'].lower():raise ValueError('服务器没有确认死亡不掉落为true')
        return results
