"""Local-only dashboard and supervised pixel-to-action loop."""
from __future__ import annotations
import base64, collections, io, json, os, subprocess, sys, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/GameScaling'))
from gamescaling.action import parse_action,split_reasoning,ACTION_END,NOOP_ACTION_TEXT
from gamescaling.prompt import build_system_prompt

BRIDGE=ROOT/'runtime/bridge'
ENGINE='http://127.0.0.1:8789'
STATE={'phase':'等待客户端和模型就绪','enabled':True,'step':0,'raw':'','thinking':'',
       'last_action':'','latency':0,'errors':0,'parsed':0,'history':[],
       'goal':'Observe the surroundings, find a safe nearby tree or loose flint, and begin the GTNH stone-age quest progression. Avoid water, cliffs and lava.','inference_started':None}
LOCK=threading.RLock()
HISTORY=collections.deque(maxlen=5)
ABORT=threading.Event()
OPENER=__import__('urllib.request',fromlist=['build_opener']).build_opener(__import__('urllib.request',fromlist=['ProxyHandler']).ProxyHandler({}))

def readjson(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return {} if default is None else default

def atomic(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False));tmp.replace(p)

def request(path,body=None,timeout=10):
    req=Request(ENGINE+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    return OPENER.open(req,timeout=timeout)

def event(kind,**values):
    record={'time':time.time(),'kind':kind,**values}
    with LOCK:
        STATE['history']=(STATE['history']+[record])[-30:]
    with (ROOT/'logs/events.jsonl').open('a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')

def system_prompt():
    return build_system_prompt('Minecraft 1.7.10 - GregTech New Horizons 2.8.4',rules=(
      'This is the GT New Horizons modpack, not vanilla progression. Recipes, tool requirements and block harvest levels are modified. '
      'Use visible quest-book guidance and NEI recipes rather than assuming vanilla crafting. '
      'Early progression involves exploration, flint, wood and primitive tools. Hand chopping and vanilla wooden tools may not work as expected. '
      'Avoid destroying player buildings. Do not type chat commands. Keep the camera near the horizon when travelling. '
      'The game runs while you infer, but every action packet is executed only for 200ms, then ALL keys are released. '
      'Only act on the current screenshot. Close a blocking overlay with Esc when necessary. '
      'Current objective: '+STATE['goal']),key_bindings=[
        ('W','Move forward'),('A','Strafe left'),('S','Move backward'),('D','Strafe right'),
        ('Space','Jump'),('Shift','Sneak'),('Ctrl','Sprint'),('LB','Attack / mine'),('RB','Use / place / interact'),
        ('E','Open or close inventory'),('Esc','Close current screen'),('Q','Drop item; avoid unless necessary'),
        *[(n,'Select hotbar slot '+str(i)) for i,n in enumerate(['one','two','three','four','five','six','seven','eight','nine'],1)],
        ('R','Show the recipe under the mouse in inventory'),('U','Show uses in NEI')],mouse_aim=True)

def make_prompt(frame):
    # Same ChatML and empty historical <think> spans as the official checkpoint.
    prompt='<|im_start|>system\n'+system_prompt()+'<|im_end|>\n'
    images=[]
    for old,action in HISTORY:
        prompt+='<|im_start|>user\ncurrent game screen<__media__><|im_end|>\n'
        prompt+='<|im_start|>assistant\n<think>\n\n</think>\n\n'+action+'<|im_end|>\n'
        images.append(old)
    prompt+='<|im_start|>user\ncurrent game screen<__media__><|im_end|>\n<|im_start|>assistant\n<think>'
    images.append(frame)
    return {'prompt_string':prompt,'multimodal_data':images}

def loop():
    command_id=int(time.time()*1000)
    while not ABORT.wait(1):
        try:
            with LOCK:enabled=STATE['enabled']
            if not enabled:
                STATE['phase']='已暂停；所有动作会在200毫秒内释放';continue
            game=readjson(BRIDGE/'state.json')
            if not game.get('connected') or time.time()-game.get('timestamp',0)/1000>10:
                STATE['phase']='等待 GTNH 客户端连接测试服务器';continue
            if not (BRIDGE/'frame.jpg').exists():continue
            try:
                with request('/health',timeout=2) as r:
                    if r.status!=200:continue
            except Exception:
                STATE['phase']='等待 9B 模型下载或 llama.cpp 启动';continue
            mem=memory()
            if mem.get('available_gb',100)<1.5:
                STATE['phase']='可用内存低于1.5GiB，自动暂停推理';time.sleep(3);continue
            frame_bytes=(BRIDGE/'frame.jpg').read_bytes()
            frame=base64.b64encode(frame_bytes).decode()
            stamp=f'{STATE["step"]+1:06d}'
            evidence=ROOT/'runtime/episodes';evidence.mkdir(exist_ok=True)
            (evidence/(stamp+'.jpg')).write_bytes(frame_bytes)
            STATE.update(phase='模型正在观察并生成动作',raw='',thinking='',inference_started=time.time())
            t0=time.monotonic();text='';finish={}
            with request('/completion',{'prompt':make_prompt(frame),'stream':True,'temperature':1.0,
                    'top_k':0,'top_p':1.0,'min_p':0.0,'repeat_penalty':1.0,'n_predict':768,
                    'stop':[ACTION_END],'cache_prompt':True,'return_tokens':True},timeout=600) as resp:
                for line in resp:
                    if not line.startswith(b'data:'):continue
                    payload=line[5:].strip()
                    if payload==b'[DONE]':break
                    chunk=json.loads(payload)
                    if 'error' in chunk:raise RuntimeError(chunk['error'])
                    text+=chunk.get('content','')
                    STATE['raw']='<think>'+text
                    if chunk.get('stop'):finish=chunk
                    if ABORT.is_set():break
            raw='<think>'+text
            if ACTION_END not in raw and finish.get('stopped_word'):raw+=ACTION_END
            a=parse_action(raw)
            reasoning,_,closed=split_reasoning(raw)
            elapsed=time.monotonic()-t0
            STATE.update(thinking=reasoning,latency=elapsed,step=STATE['step']+1,
                         parsed=STATE['parsed']+int(a.parsed),last_action=a.history_text,inference_started=None)
            record={'step':STATE['step'],'raw':raw,'reasoning':reasoning,'action':a.history_text,
                    'parsed':a.parsed,'latency':elapsed,'game_before':game,'timings':finish.get('timings',{})}
            atomic(evidence/(stamp+'.json'),record);event('decision',**record)
            HISTORY.append((frame,a.history_text))
            # Only an actual completed, valid packet may move the game.
            if a.parsed and STATE['enabled']:
                command_id+=1
                atomic(BRIDGE/'command.json',{'id':command_id,'mouse':a.mouse,'steps':a.steps})
                STATE['phase']='客户端执行200毫秒动作'
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    if readjson(BRIDGE/'completed.json').get('id')==command_id:break
                    time.sleep(.05)
                else:raise RuntimeError('客户端没有确认动作完成；已停止发送后续动作')
            elif not a.parsed:
                STATE['errors']+=1;STATE['phase']='模型输出未通过解析，保持静止';time.sleep(2)
        except Exception as exc:
            STATE['errors']+=1;STATE.update(phase='等待恢复：'+str(exc),inference_started=None)
            event('error',message=str(exc));traceback.print_exc();HISTORY.clear();time.sleep(5)

def memory():
    d={}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            key,value=line.split(':',1);d[key]=int(value.split()[0])*1024
        return {'total_gb':round(d['MemTotal']/2**30,2),'available_gb':round(d['MemAvailable']/2**30,2)}
    except Exception:return {}

GPU={}
def telemetry():
    while not ABORT.wait(5):
        try:
            p=subprocess.run(['nvidia-smi','--query-gpu=memory.used,memory.total,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=4)
            if p.returncode==0:
                a=p.stdout.strip().split(',');GPU.update(used_mb=int(a[0]),total_mb=int(a[1]),utilization=int(a[2]))
        except Exception:pass

def status():
    with LOCK:result=dict(STATE)
    result['game']=readjson(BRIDGE/'state.json');result['memory']=memory();result['gpu']=dict(GPU)
    result['processes']={}
    for name in ['server','client','model']:
        try:
            pid=int((ROOT/f'runtime/{name}.pid').read_text());s=Path(f'/proc/{pid}/status').read_text()
            rss=next((int(x.split()[1])/1024 for x in s.splitlines() if x.startswith('VmRSS:')),0)
            result['processes'][name]={'pid':pid,'rss_mb':round(rss),'alive':True}
        except Exception:result['processes'][name]={'alive':False}
    result['downloads']=[{'file':p.name,'bytes':p.stat().st_size} for p in (ROOT/'models').glob('**/*.incomplete')]
    return result

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/status': data=json.dumps(status(),ensure_ascii=False).encode();mime='application/json'
        elif path=='/frame.jpg':
            try:data=(BRIDGE/'frame.jpg').read_bytes();mime='image/jpeg'
            except OSError:self.send_error(404);return
        elif path=='/':data=(ROOT/'ui/index.html').read_bytes();mime='text/html; charset=utf-8'
        else:self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
    def do_POST(self):
        origin=self.headers.get('Origin')
        if origin and origin not in ['http://127.0.0.1:8790','http://localhost:8790']:
            self.send_error(403);return
        if self.path!='/api/control':self.send_error(404);return
        body=json.loads(self.rfile.read(min(int(self.headers.get('Content-Length',0)),8192)))
        with LOCK:
            if 'enabled' in body:STATE['enabled']=bool(body['enabled'])
            if 'goal' in body:STATE['goal']=str(body['goal'])[:1000];HISTORY.clear()
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"ok":true}')
    def log_message(self,*args):pass

def main():
    BRIDGE.mkdir(parents=True,exist_ok=True);(ROOT/'logs').mkdir(exist_ok=True)
    threading.Thread(target=loop,daemon=True).start();threading.Thread(target=telemetry,daemon=True).start()
    print('GTNH monitor: http://127.0.0.1:8790',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8790),Handler).serve_forever()

if __name__=='__main__':main()
