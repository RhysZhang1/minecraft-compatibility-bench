"""Local-only dashboard and supervised pixel-to-action loop."""
from __future__ import annotations
import base64, collections, hashlib, io, json, os, subprocess, sys, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/GameScaling'))
from gamescaling.action import parse_action,split_reasoning,ACTION_END,NOOP_ACTION_TEXT
from gamescaling.prompt import build_system_prompt
import server_console
import model_config
from agent_memory import AgentMemory,replace as replace_memory

BRIDGE=ROOT/'runtime/bridge'
ENGINE='http://127.0.0.1:8789'
STATE={'phase':'等待客户端和模型就绪','enabled':True,'step':0,'raw':'','thinking':'',
       'last_action':'','latency':0,'errors':0,'parsed':0,'history':[],
       'goal':'Inspect the Quest Book with right click while it is selected in hotbar slot 1. Then find a safe patch of dirt and collect 8 dirt for the first GTNH quest. Avoid water, cliffs and lava.','inference_started':None}
LOCK=threading.RLock()
HISTORY=collections.deque(maxlen=5)
ABORT=threading.Event()
CONTROL_EPOCH=int(time.time()*1000)
COMMAND_LOCK=threading.Lock()
CONSOLE={'ready':False,'settings_applied':False,'message':'等待服务器命令服务','history':[]}
OPENER=__import__('urllib.request',fromlist=['build_opener']).build_opener(__import__('urllib.request',fromlist=['ProxyHandler']).ProxyHandler({}))
MEMORY=AgentMemory(ROOT)

def readjson(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return {} if default is None else default

def atomic(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False));tmp.replace(p)

def publish_safety():
    with LOCK:atomic(BRIDGE/'safety.json',{'epoch':CONTROL_EPOCH,'timestamp':int(time.time()*1000)})

def safety_loop():
    while not ABORT.is_set():
        try:publish_safety()
        except OSError:traceback.print_exc()
        ABORT.wait(.25)

def request(path,body=None,timeout=10):
    req=Request(ENGINE+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    return OPENER.open(req,timeout=timeout)

def event(kind,**values):
    record={'time':time.time(),'kind':kind,**values}
    with LOCK:
        STATE['history']=(STATE['history']+[record])[-30:]
    with (ROOT/'logs/events.jsonl').open('a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')

def system_prompt(memory_context=None):
    if memory_context is None:memory_context=MEMORY.prompt_context()
    context=readjson(ROOT/'runtime/gtnh-context.json')
    quest_hint=''
    for quest in context.get('quests',[]):
        parts=[]
        for task in quest['tasks']:
            parts.append((', '.join(str(x['count'])+' '+(x['ore_dictionary'] or x['item']) for x in task['items']))+(' (consumed)' if task['consume'] else ' (inventory check)'))
        quest_hint+=quest['title']+': '+'; '.join(parts)+'. '
    return build_system_prompt('Minecraft 1.7.10 - GregTech New Horizons 2.8.4',rules=(
      'This is the GT New Horizons modpack, not vanilla progression. Recipes, tool requirements and block harvest levels are modified. '
      'Use visible quest-book guidance and NEI recipes rather than assuming vanilla crafting. '
      'Early progression involves shelter, dirt, gravel, wood and primitive tools. Hand chopping and vanilla wooden tools may not work as expected. '
      'The starting hotbar item is a Quest Book, not an axe. Verify the actually selected item on screen before assuming a tool is equipped. '
      'The following requirements were extracted from this installed pack version: '+quest_hint+
      'Avoid destroying player buildings. Do not type chat commands. Keep the camera near the horizon when travelling. '
      'Each action packet covers 200ms. Movement and use keys release afterwards. '
      'To mine, aim steadily at a harvestable block and hold LB in all six substeps. Only LB can then remain held on that same block while you infer, for at most 10 seconds. '
      'The mining hold stops if the target changes, the block breaks, a GUI opens, control pauses, or the watchdog expires. Check the next observation for results. '
      'Only act on the current screenshot. Close a blocking overlay with Esc when necessary. '
      'Current objective: '+STATE['goal']+'\n'+memory_context),key_bindings=[
        ('W','Move forward'),('A','Strafe left'),('S','Move backward'),('D','Strafe right'),
        ('Space','Jump'),('Shift','Sneak'),('Ctrl','Sprint'),('LB','Attack / mine'),('RB','Use / place / interact'),
        ('E','Open or close inventory'),('Esc','Close current screen'),('Q','Drop item; avoid unless necessary'),
        *[(n,'Select hotbar slot '+str(i)) for i,n in enumerate(['one','two','three','four','five','six','seven','eight','nine'],1)],
        ('R','Show the recipe under the mouse in inventory'),('U','Show uses in NEI')],mouse_aim=True)

def make_prompt(frame,marker=None,memory_context=None):
    if marker is None:
        with request('/props',timeout=5) as response:
            marker=json.load(response)['media_marker']
    # Same ChatML and empty historical <think> spans as the official checkpoint.
    prompt='<|im_start|>system\n'+system_prompt(memory_context)+'<|im_end|>\n'
    images=[]
    with LOCK:history=tuple(HISTORY)
    for old,action in history:
        prompt+='<|im_start|>user\ncurrent game screen'+marker+'<|im_end|>\n'
        prompt+='<|im_start|>assistant\n<think>\n\n</think>\n\n'+action+'<|im_end|>\n'
        images.append(old)
    prompt+='<|im_start|>user\ncurrent game screen'+marker+'<|im_end|>\n<|im_start|>assistant\n<think>'
    images.append(frame)
    return {'prompt_string':prompt,'multimodal_data':images}

def summarize_memory():
    with LOCK:goal=STATE['goal'];step=STATE['step'];epoch=CONTROL_EPOCH
    MEMORY.running=True
    STATE['phase']='正在整理续玩笔记；此请求不执行游戏动作'
    raw='';error=''
    try:
        body=MEMORY.summary_request(goal,readjson(BRIDGE/'state.json'),step)
        with request('/completion',body,timeout=60) as response:reply=json.load(response)
        raw=reply.get('content','')
        if epoch!=CONTROL_EPOCH:raise ValueError('整理期间目标或控制状态已变化，本次草稿未采用')
        MEMORY.apply_summary(raw,step,readjson(ROOT/'runtime/model-active.json').get('key','unknown'))
    except Exception as exc:
        error=str(exc);MEMORY.summary_failed(error,step)
    finally:
        replace_memory(ROOT/'memory/summaries'/f'{time.time_ns()}-{step}.json',json.dumps({'time':time.time(),'step':step,'raw':raw,'error':error,'executed':False},ensure_ascii=False,indent=2))
        MEMORY.running=False

def loop():
    global CONTROL_EPOCH
    command_id=int(time.time()*1000)
    while not ABORT.wait(1):
        try:
            game=readjson(BRIDGE/'state.json')
            if time.monotonic()-MEMORY.last_checkpoint>2:
                MEMORY.checkpoint(STATE['goal'],game,STATE['step'])
            if MEMORY.due(STATE['step']) and (MEMORY.pending or STATE['enabled']):
                summarize_memory()
            with LOCK:enabled=STATE['enabled'];epoch=CONTROL_EPOCH
            if not enabled:
                STATE['phase']='已暂停；已请求释放动作与挖掘长按';continue
            game=readjson(BRIDGE/'state.json')
            if not game.get('connected') or time.time()-game.get('timestamp',0)/1000>10:
                STATE['phase']='等待 GTNH 客户端连接测试服务器';continue
            if not (BRIDGE/'frame.jpg').exists():continue
            try:
                with request('/health',timeout=2) as r:
                    if r.status!=200:continue
            except Exception:
                STATE['phase']='等待本地模型或 llama.cpp 启动';continue
            mem=memory()
            if mem.get('available_gb',100)<1.5:
                STATE['phase']='可用内存低于1.5GiB，自动暂停推理';time.sleep(3);continue
            frame_bytes=(BRIDGE/'frame.jpg').read_bytes()
            frame=base64.b64encode(frame_bytes).decode()
            stamp=f'{STATE["step"]+1:06d}'
            evidence=ROOT/'runtime/episodes';evidence.mkdir(exist_ok=True)
            (evidence/(stamp+'.jpg')).write_bytes(frame_bytes)
            STATE.update(phase='模型正在观察并生成动作',raw='',thinking='',inference_started=time.time())
            memory_context=MEMORY.prompt_context()
            t0=time.monotonic();text='';finish={}
            with request('/completion',{'prompt':make_prompt(frame,memory_context=memory_context),'stream':True,'temperature':1.0,
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
            if ACTION_END not in raw and finish.get('stop_type')=='word' and finish.get('stopping_word')==ACTION_END:
                raw+=ACTION_END
            a=parse_action(raw)
            reasoning,_,closed=split_reasoning(raw)
            elapsed=time.monotonic()-t0
            STATE.update(raw=raw,thinking=reasoning,latency=elapsed,step=STATE['step']+1,
                         parsed=STATE['parsed']+int(a.parsed),last_action=a.history_text,inference_started=None)
            record={'timestamp':time.time(),'step':STATE['step'],'raw':raw,'reasoning':reasoning,'action':a.history_text,
                    'parsed':a.parsed,'latency':elapsed,'game_before':game,'timings':finish.get('timings',{})}
            record['executed']=False
            record['model']=readjson(ROOT/'runtime/model-active.json')
            record['agent_memory']={'revision':MEMORY.config()['revision'],'context':memory_context,
                                    'sha256':hashlib.sha256(memory_context.encode()).hexdigest()}
            if epoch!=CONTROL_EPOCH:record['discard_reason']='控制状态或目标已变化，丢弃此前推理的动作'
            atomic(evidence/(stamp+'.json'),record)
            with LOCK:
                if epoch==CONTROL_EPOCH:HISTORY.append((frame,a.history_text))
            # Only an actual completed, valid packet may move the game.
            with LOCK:
                execute_action=a.parsed and STATE['enabled'] and epoch==CONTROL_EPOCH
                if execute_action:
                    command_id=max(command_id+1,int(time.time()*1000),readjson(BRIDGE/'state.json').get('command_id',0)+1)
                    atomic(BRIDGE/'command.json',{'id':command_id,'mouse':a.mouse,'steps':a.steps,'epoch':epoch,'sustain_mining':True})
            if execute_action:
                STATE['phase']='客户端执行动作；同一方块挖掘可继续长按'
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    completed=readjson(BRIDGE/'completed.json')
                    if completed.get('id')==command_id:
                        record.update(executed=not completed.get('cancelled',False),completion=completed,
                                      command_id=command_id,game_after=readjson(BRIDGE/'state.json'))
                        if completed.get('cancelled'):record['discard_reason']='客户端因控制变化或心跳过期取消动作'
                        break
                    time.sleep(.05)
                else:raise RuntimeError('客户端没有确认动作完成；已停止发送后续动作')
            elif not a.parsed:
                STATE['errors']+=1;STATE['phase']='模型输出未通过解析，保持静止';time.sleep(2)
            atomic(evidence/(stamp+'.json'),record);event('decision',**record)
        except Exception as exc:
            with LOCK:CONTROL_EPOCH+=1;publish_safety()
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
def command_event(command,output,error=False):
    record={'time':time.time(),'command':command,'output':output,'error':error}
    with LOCK:CONSOLE['history']=(CONSOLE['history']+[record])[-30:]
    with (ROOT/'logs/server-commands.jsonl').open('a') as f:
        f.write(json.dumps(record,ensure_ascii=False)+'\n')
    return record

def run_command(command,pause=True):
    global CONTROL_EPOCH
    command=server_console.validate(command)
    with COMMAND_LOCK:
        with LOCK:
            if pause:STATE['enabled']=False
            CONTROL_EPOCH+=1;HISTORY.clear()
            publish_safety()
            atomic(ROOT/'runtime/control.json',{'enabled':STATE['enabled'],'goal':STATE['goal']})
        # Finish the current bounded action before applying a manual world change.
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            game=readjson(BRIDGE/'state.json')
            if not game.get('busy') and not game.get('mining_active'):break
            time.sleep(.05)
        try:
            output=server_console.execute(command)
            return command_event(command,output or '（服务器未返回文字）')
        except (OSError,ValueError,ConnectionError) as exc:
            command_event(command,str(exc),True);raise

def server_settings_loop():
    applied_pid=None
    while not ABORT.wait(3):
        try:
            pid=(ROOT/'runtime/server.pid').read_text().strip()
            if pid==applied_pid:continue
            with COMMAND_LOCK:
                results=server_console.apply_defaults()
                for r in results:command_event(r['command'],r['output'])
            CONSOLE.update(ready=True,settings_applied=True,message='测试设置已应用：和平 · 死亡不掉落')
            atomic(ROOT/'runtime/server-settings-applied.json',{'time':time.time(),'pid':pid,'results':results})
            applied_pid=pid
        except (OSError,ValueError,ConnectionError) as exc:
            CONSOLE.update(ready=False,settings_applied=False,message='等待服务器命令服务：'+str(exc))

def telemetry():
    while not ABORT.wait(5):
        try:
            p=subprocess.run(['nvidia-smi','--query-gpu=memory.used,memory.total,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=4)
            if p.returncode==0:
                a=p.stdout.strip().split(',');GPU.update(used_mb=int(a[0]),total_mb=int(a[1]),utilization=int(a[2]))
        except Exception:pass

def status():
    with LOCK:result=dict(STATE)
    result['game']=readjson(BRIDGE/'state.json')
    if time.time()-result['game'].get('timestamp',0)/1000>10:
        result['game']['connected']=False
    result['memory']=memory();result['gpu']=dict(GPU)
    result['model']=readjson(ROOT/'runtime/model-active.json')
    mv=MEMORY.view(STATE['goal'])
    result['agent_memory']={k:mv[k] for k in ['revision','summary_at','summary_step','pending','running','error','updated_at','prompt_chars']}
    with LOCK:result['console']=dict(CONSOLE)
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
        elif path=='/api/memory':data=json.dumps(MEMORY.view(STATE['goal']),ensure_ascii=False).encode();mime='application/json'
        elif path=='/frame.jpg':
            try:data=(BRIDGE/'frame.jpg').read_bytes();mime='image/jpeg'
            except OSError:self.send_error(404);return
        elif path=='/':data=(ROOT/'ui/index.html').read_bytes();mime='text/html; charset=utf-8'
        else:self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
    def do_POST(self):
        global CONTROL_EPOCH
        origin=self.headers.get('Origin')
        if origin and origin not in ['http://127.0.0.1:8790','http://localhost:8790']:
            self.send_error(403);return
        if self.headers.get('Host') not in ['127.0.0.1:8790','localhost:8790']:
            self.send_error(403);return
        if self.headers.get_content_type()!='application/json':self.send_error(415);return
        if self.path not in ['/api/control','/api/server/command','/api/memory/save','/api/memory/summarize','/api/memory/checkpoint']:self.send_error(404);return
        try:
            size=int(self.headers.get('Content-Length',0))
            if not 0<size<=16384:raise ValueError('请求长度无效')
            body=json.loads(self.rfile.read(size))
            if not isinstance(body,dict):raise ValueError('请求格式无效')
        except (ValueError,UnicodeError):self.json_response(400,{'error':'请求格式无效'});return
        if self.path=='/api/server/command':
            try:self.json_response(200,{'ok':True,'result':run_command(body.get('command'),body.get('pause_model',True))})
            except ValueError as exc:self.json_response(400,{'ok':False,'error':str(exc)})
            except (OSError,ConnectionError) as exc:self.json_response(503,{'ok':False,'error':str(exc)})
            return
        if self.path=='/api/memory/save':
            try:
                goal=body.get('goal',STATE['goal'])
                if not isinstance(goal,str) or not goal.strip() or len(goal)>600:raise ValueError('目标应为1至600字')
                with LOCK:
                    MEMORY.save_config(body,goal.strip());STATE['goal']=goal.strip()
                    CONTROL_EPOCH+=1;HISTORY.clear()
                    publish_safety()
                    atomic(ROOT/'runtime/control.json',{'enabled':STATE['enabled'],'goal':STATE['goal']})
                self.json_response(200,{'ok':True,'memory':MEMORY.view(STATE['goal'])})
            except ValueError as exc:self.json_response(400,{'ok':False,'error':str(exc)})
            return
        if self.path=='/api/memory/summarize':
            with MEMORY.lock:
                if not MEMORY.running:MEMORY.pending=True
            self.json_response(202,{'ok':True});return
        if self.path=='/api/memory/checkpoint':
            MEMORY.checkpoint(STATE['goal'],readjson(BRIDGE/'state.json'),STATE['step'],archive=True)
            self.json_response(200,{'ok':True});return
        with LOCK:
            CONTROL_EPOCH+=1
            publish_safety()
            if 'enabled' in body:STATE['enabled']=bool(body['enabled'])
            if 'goal' in body:STATE['goal']=str(body['goal'])[:1000];HISTORY.clear()
            atomic(ROOT/'runtime/control.json',{'enabled':STATE['enabled'],'goal':STATE['goal']})
        self.json_response(200,{'ok':True})
    def json_response(self,code,value):
        data=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass

def main():
    BRIDGE.mkdir(parents=True,exist_ok=True);(ROOT/'logs').mkdir(exist_ok=True)
    saved=readjson(ROOT/'runtime/control.json')
    STATE.update({key:saved[key] for key in ['enabled','goal'] if key in saved})
    try:
        records=[json.loads(line) for line in (ROOT/'logs/server-commands.jsonl').read_text().splitlines()[-30:]]
        CONSOLE['history']=records
    except (OSError,ValueError):pass
    records=[readjson(p) for p in sorted((ROOT/'runtime/episodes').glob('*.json'))]
    if records:
        last=records[-1]
        STATE.update(step=max(r.get('step',0) for r in records),parsed=sum(bool(r.get('parsed')) for r in records),
            raw=last.get('raw',''),thinking=last.get('reasoning',''),last_action=last.get('action',''),latency=last.get('latency',0))
        STATE['history']=[dict(time=r.get('timestamp',time.time()),kind='decision',**r) for r in records[-10:]]
    MEMORY.ensure(STATE['goal'])
    MEMORY.checkpoint(STATE['goal'],readjson(BRIDGE/'state.json'),STATE['step'])
    publish_safety();threading.Thread(target=safety_loop,daemon=True).start()
    threading.Thread(target=loop,daemon=True).start();threading.Thread(target=telemetry,daemon=True).start()
    threading.Thread(target=server_settings_loop,daemon=True).start()
    print('GTNH monitor: http://127.0.0.1:8790',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8790),Handler).serve_forever()

if __name__=='__main__':main()
