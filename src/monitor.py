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
import instance_config
from controller import Feedback,read_observation,append_history

BRIDGE=ROOT/'runtime/bridge'
ENGINE='http://127.0.0.1:8789'
INSTANCE=instance_config.config()
CONTROL_SETTINGS=json.loads((ROOT/'control-settings.json').read_text())
CONTROL_FILE=instance_config.control_file()
EPISODES=instance_config.episodes_directory()
STATE={'phase':'等待客户端和模型就绪','enabled':True,'step':0,'raw':'','thinking':'',
       'last_action':'','latency':0,'errors':0,'parsed':0,'history':[],
       'goal':INSTANCE['initial_goal'],'inference_started':None,'feedback':{},'recovery_reason':''}
LOCK=threading.RLock()
HISTORY=collections.deque(maxlen=CONTROL_SETTINGS.get('history_length',5))
ABORT=threading.Event()
CONTROL_EPOCH=int(time.time()*1000)
COMMAND_LOCK=threading.Lock()
CONSOLE={'ready':False,'settings_applied':False,'message':'等待服务器命令服务','history':[]}
OPENER=__import__('urllib.request',fromlist=['build_opener']).build_opener(__import__('urllib.request',fromlist=['ProxyHandler']).ProxyHandler({}))
MEMORY=AgentMemory(ROOT,instance_config.memory_directory(),INSTANCE['world_id'])
FEEDBACK=Feedback(CONTROL_SETTINGS)
MARKER_CACHE={}

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
    # Stable prefix: live facts and the objective belong in the latest observation.
    return build_system_prompt('Minecraft '+INSTANCE['minecraft_version'],rules=(
      'Avoid destroying player buildings. Do not type chat commands. '
      'Each action packet covers 200ms. Movement and use keys release afterwards. '
      'To mine, aim steadily at a harvestable block and hold LB in all six substeps. Only LB can then remain held on that same block while you infer, for at most 10 seconds. '
      'The mining hold stops if the target changes, the block breaks, a GUI opens, control pauses, or the watchdog expires. Check the next observation for results. '
      'Only act on the current screenshot. Verify what the previous action actually changed. '
      +instance_config.pack_rules()),key_bindings=[
        ('W','Move forward'),('A','Strafe left'),('S','Move backward'),('D','Strafe right'),
        ('Space','Jump'),('Shift','Sneak'),('Ctrl','Sprint'),('LB','Attack / mine'),('RB','Use / place / interact'),
        ('E','Open or close inventory'),('Esc','Close current screen'),('Q','Drop item'),
        *[(n,'Select hotbar slot '+str(i)) for i,n in enumerate(['one','two','three','four','five','six','seven','eight','nine'],1)]],mouse_aim=True)

def observation_text(memory_context=None,feedback=''):
    if memory_context is None:memory_context=MEMORY.prompt_context()
    return 'current game screen\nCurrent objective: '+STATE['goal']+'\n'+memory_context+('\n'+feedback if feedback else '')

def make_prompt(frame,marker=None,memory_context=None,feedback=''):
    if marker is None:
        identity=readjson(ROOT/'runtime/model-active.json').get('time')
        if MARKER_CACHE.get('identity')!=identity or not MARKER_CACHE.get('marker'):
            with request('/props',timeout=5) as response:MARKER_CACHE.update(identity=identity,marker=json.load(response)['media_marker'])
        marker=MARKER_CACHE['marker']
    prompt='<|im_start|>system\n'+system_prompt()+'<|im_end|>\n';images=[]
    with LOCK:history=tuple(HISTORY)
    for old,action in history:
        prompt+='<|im_start|>user\ncurrent game screen'+marker+'<|im_end|>\n'
        prompt+='<|im_start|>assistant\n<think>\n\n</think>\n\n'+action+'<|im_end|>\n'
        images.append(old)
    prompt+='<|im_start|>user\n'+observation_text(memory_context,feedback)+marker+'<|im_end|>\n<|im_start|>assistant\n<think>'
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
        replace_memory(MEMORY.folder/'summaries'/f'{time.time_ns()}-{step}.json',json.dumps({'time':time.time(),'step':step,'raw':raw,'error':error,'executed':False},ensure_ascii=False,indent=2))
        MEMORY.running=False

def loop():
    global CONTROL_EPOCH
    command_id=int(time.time()*1000);last_frame_time=0
    while not ABORT.is_set():
        record=None;stamp=None;cycle_started=time.monotonic()
        try:
            with LOCK:enabled=STATE['enabled'];epoch=CONTROL_EPOCH
            game=readjson(BRIDGE/'state.json')
            if time.monotonic()-MEMORY.last_checkpoint>2:MEMORY.checkpoint(STATE['goal'],game,STATE['step'])
            if MEMORY.due(STATE['step']) and (MEMORY.pending or enabled):summarize_memory()
            if not enabled:
                STATE['phase']='已暂停；已请求释放动作与挖掘长按';ABORT.wait(CONTROL_SETTINGS['idle_wait_seconds']);continue
            if not game.get('connected') or time.time()*1000-game.get('timestamp',0)>3000:
                STATE['phase']='等待 Minecraft 客户端连接配置的服务器';ABORT.wait(CONTROL_SETTINGS['idle_wait_seconds']);continue
            if memory().get('available_gb',100)<1.5:
                STATE['phase']='可用内存低于1.5GiB，等待资源恢复';ABORT.wait(.5);continue
            cycle_started=time.monotonic()
            observation=read_observation(BRIDGE,after=last_frame_time,timeout=CONTROL_SETTINGS['fresh_frame_timeout_seconds'],
                                         cancel=lambda:ABORT.is_set() or epoch!=CONTROL_EPOCH)
            game=observation.game;frame_bytes=observation.image;frame=base64.b64encode(frame_bytes).decode()
            stamp=f'{STATE["step"]+1:06d}';EPISODES.mkdir(parents=True,exist_ok=True)
            (EPISODES/(stamp+'.jpg')).write_bytes(frame_bytes)
            STATE.update(phase='模型正在观察并生成动作',raw='',thinking='',inference_started=time.time())
            memory_context=MEMORY.prompt_context();feedback_text=FEEDBACK.text(game)
            t0=time.monotonic();text='';finish={}
            with request('/completion',{'prompt':make_prompt(frame,memory_context=memory_context,feedback=feedback_text),
                    'stream':True,'temperature':1.0,'top_k':0,'top_p':1.0,'min_p':0.0,'repeat_penalty':1.0,
                    'n_predict':768,'stop':[ACTION_END],'cache_prompt':True,'return_tokens':True},timeout=600) as resp:
                for line in resp:
                    if epoch!=CONTROL_EPOCH or ABORT.is_set():break
                    if not line.startswith(b'data:'):continue
                    payload=line[5:].strip()
                    if payload==b'[DONE]':break
                    chunk=json.loads(payload)
                    if 'error' in chunk:raise RuntimeError(chunk['error'])
                    text+=chunk.get('content','');STATE['raw']='<think>'+text
                    if chunk.get('stop'):finish=chunk
            raw='<think>'+text
            if ACTION_END not in raw and finish.get('stop_type')=='word' and finish.get('stopping_word')==ACTION_END:raw+=ACTION_END
            a=parse_action(raw);reasoning,_,closed=split_reasoning(raw);elapsed=time.monotonic()-t0
            STATE.update(raw=raw,thinking=reasoning,latency=elapsed,step=STATE['step']+1,
                         parsed=STATE['parsed']+int(a.parsed),last_action=a.history_text,inference_started=None)
            record={'timestamp':time.time(),'step':STATE['step'],'raw':raw,'reasoning':reasoning,'action':a.history_text,
                    'parsed':a.parsed,'latency':elapsed,'game_before':game,'observation':observation.metadata,
                    'timings':finish.get('timings',{}),'executed':False,'instance':INSTANCE['key'],
                    'model':readjson(ROOT/'runtime/model-active.json'),
                    'agent_memory':{'revision':MEMORY.config()['revision'],'context':memory_context,'sha256':hashlib.sha256(memory_context.encode()).hexdigest()},
                    'feedback_input':feedback_text}
            current=readjson(BRIDGE/'state.json')
            with LOCK:
                valid_session=current.get('session')==game.get('session') and current.get('connected')
                execute_action=a.parsed and STATE['enabled'] and epoch==CONTROL_EPOCH and valid_session
                if execute_action:
                    command_id=max(command_id+1,int(time.time()*1000),current.get('command_id',0)+1)
                    atomic(BRIDGE/'command.json',{'id':command_id,'mouse':a.mouse,'steps':a.steps,'epoch':epoch,'sustain_mining':True})
            if execute_action:
                STATE['phase']='客户端执行动作并检查结果';deadline=time.monotonic()+10;completed={}
                while time.monotonic()<deadline:
                    completed=readjson(BRIDGE/'completed.json')
                    if completed.get('id')==command_id:break
                    if ABORT.wait(.015):break
                else:raise RuntimeError('客户端没有确认动作完成；停止发送后续动作')
                record.update(executed=completed.get('id')==command_id and not completed.get('cancelled',False),completion=completed,command_id=command_id)
                if record['executed'] and epoch==CONTROL_EPOCH:
                    after=read_observation(BRIDGE,after=completed['time'],timeout=CONTROL_SETTINGS['fresh_frame_timeout_seconds'],
                                           cancel=lambda:ABORT.is_set() or epoch!=CONTROL_EPOCH)
                    last_frame_time=after.metadata['captured_at'];record['game_after']=after.game;record['after_observation']=after.metadata
                    result=FEEDBACK.record(observation,after,a);record['feedback']=result;STATE['feedback']=result
                    with LOCK:
                        append_history(HISTORY,frame,a,CONTROL_SETTINGS.get('coalesce_identical_idle_history',True))
                        if FEEDBACK.reset_history:
                            latest=HISTORY[-1] if HISTORY else None;HISTORY.clear()
                            if latest:HISTORY.append(latest)
                            STATE['recovery_reason']='连续无明显变化，重新观察；没有替模型点击按钮'
                        if FEEDBACK.phase=='stalled':
                            STATE['enabled']=False;CONTROL_EPOCH+=1;publish_safety()
                            STATE['recovery_reason']='有限次数重新观察后仍无明显变化，保留现场并暂停'
                            atomic(CONTROL_FILE,{'enabled':False,'goal':STATE['goal']})
                else:record['discard_reason']='客户端取消动作或控制状态已变化'
            elif epoch!=CONTROL_EPOCH or not valid_session:record['discard_reason']='控制状态或客户端连接已变化'
            elif not a.parsed:
                STATE['errors']+=1;STATE['phase']='输出未通过解析，保留原文并重新观察';HISTORY.clear()
            record['cycle_seconds']=time.monotonic()-cycle_started
            atomic(EPISODES/(stamp+'.json'),record);event('decision',**record)
        except InterruptedError:
            STATE['inference_started']=None
            if record:
                record.update(discard_reason='等待新画面期间控制状态已变化',cycle_seconds=time.monotonic()-cycle_started)
                atomic(EPISODES/(stamp+'.json'),record);event('decision',**record)
        except Exception as exc:
            with LOCK:CONTROL_EPOCH+=1;publish_safety()
            STATE['errors']+=1;STATE.update(phase='等待恢复：'+str(exc),inference_started=None)
            if record:
                record.update(observation_error=str(exc),cycle_seconds=time.monotonic()-cycle_started)
                atomic(EPISODES/(stamp+'.json'),record);event('decision',**record)
            event('error',message=str(exc));traceback.print_exc();HISTORY.clear();MARKER_CACHE.clear();ABORT.wait(.5)

def memory():
    d={}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            key,value=line.split(':',1);d[key]=int(value.split()[0])*1024
        return {'total_gb':round(d['MemTotal']/2**30,2),'available_gb':round(d['MemAvailable']/2**30,2)}
    except Exception:return {}

GPU={}
def console_log():
    p=ROOT/'logs'/'sessions'/INSTANCE['key']/'server-commands.jsonl';p.parent.mkdir(parents=True,exist_ok=True);return p

def command_event(command,output,error=False):
    record={'time':time.time(),'instance':INSTANCE['key'],'command':command,'output':output,'error':error}
    with LOCK:CONSOLE['history']=(CONSOLE['history']+[record])[-30:]
    with console_log().open('a') as f:
        f.write(json.dumps(record,ensure_ascii=False)+'\n')
    return record

def run_command(command,pause=True):
    global CONTROL_EPOCH
    if not instance_config.console_enabled():raise ConnectionError('当前实例未配置本地服务器命令接口')
    command=server_console.validate(command)
    with COMMAND_LOCK:
        with LOCK:
            if pause:STATE['enabled']=False
            CONTROL_EPOCH+=1;HISTORY.clear()
            publish_safety()
            atomic(CONTROL_FILE,{'enabled':STATE['enabled'],'goal':STATE['goal']})
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
    if not instance_config.console_enabled():
        CONSOLE.update(ready=False,settings_applied=True,message='外部服务器：游戏连接不依赖管理权限');return
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
    result['model']=readjson(ROOT/'runtime/model-active.json');result['instance']={k:INSTANCE[k] for k in ['key','label','minecraft_version','backend','world_id']}
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
    result['keep_inventory_command']=next((c for c in server_console.defaults()['commands'] if c.startswith('gamerule ')),'gamerule keepInventory true') if instance_config.console_enabled() else ''
    result['downloads']=[{'file':p.name,'bytes':p.stat().st_size} for p in (ROOT/'models').glob('**/*.incomplete')]
    return result

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        frame_time=None
        path=urlparse(self.path).path
        if path=='/api/status': data=json.dumps(status(),ensure_ascii=False).encode();mime='application/json'
        elif path=='/api/instances':
            profiles=[]
            for key in instance_config.settings()['instances']:
                c=instance_config.config(key);client=instance_config.path(c['client']['directory']);server=instance_config.path(c['server']['directory'])
                ready=(client/c['client']['manifest']).exists() and (not c['server'].get('managed') or (server/c['server']['jar']).exists())
                profiles.append({'key':key,'label':c['label'],'version':c['minecraft_version'],'installed':ready})
            data=json.dumps({'selected':INSTANCE['key'],'instances':profiles},ensure_ascii=False).encode();mime='application/json'
        elif path=='/api/memory':data=json.dumps(MEMORY.view(STATE['goal']),ensure_ascii=False).encode();mime='application/json'
        elif path=='/frame.jpg':
            try:
                with (BRIDGE/'frame.jpg').open('rb') as f:data=f.read();frame_time=os.fstat(f.fileno()).st_mtime_ns//1000000
                mime='image/jpeg'
            except OSError:self.send_error(404);return
        elif path=='/':data=(ROOT/'ui/index.html').read_bytes();mime='text/html; charset=utf-8'
        else:self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store')
        if frame_time is not None:self.send_header('X-Frame-Time',str(frame_time))
        self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_POST(self):
        global CONTROL_EPOCH
        origin=self.headers.get('Origin')
        if origin and origin not in ['http://127.0.0.1:8790','http://localhost:8790']:
            self.send_error(403);return
        if self.headers.get('Host') not in ['127.0.0.1:8790','localhost:8790']:
            self.send_error(403);return
        if self.headers.get_content_type()!='application/json':self.send_error(415);return
        if self.path not in ['/api/control','/api/server/command','/api/memory/save','/api/memory/summarize','/api/memory/checkpoint','/api/instance/switch']:self.send_error(404);return
        try:
            size=int(self.headers.get('Content-Length',0))
            if not 0<size<=16384:raise ValueError('请求长度无效')
            body=json.loads(self.rfile.read(size))
            if not isinstance(body,dict):raise ValueError('请求格式无效')
        except (ValueError,UnicodeError):self.json_response(400,{'error':'请求格式无效'});return
        if self.path=='/api/instance/switch':
            try:
                key=body.get('instance')
                if not isinstance(key,str) or key not in instance_config.settings()['instances']:raise ValueError('未知实例')
                c=instance_config.config(key)
                if STATE.get('switching'):raise ValueError('正在切换，请等待观察台重连')
                if (ROOT/'runtime/stop.request').exists():raise ValueError('正在完全停止，请等待结束后再启动')
                if key==INSTANCE['key']:raise ValueError('已经是当前实例')
                if not (instance_config.path(c['client']['directory'])/c['client']['manifest']).exists():raise ValueError('请先运行setup.sh下载或导入该实例')
                with LOCK:
                    STATE['switching']=True;STATE['enabled']=False;CONTROL_EPOCH+=1;publish_safety()
                    MEMORY.checkpoint(STATE['goal'],readjson(BRIDGE/'state.json'),STATE['step'],archive=True)
                    with (ROOT/'logs/switch.log').open('ab') as output:
                        subprocess.Popen([sys.executable,str(ROOT/'scripts/switch_instance.py'),key],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
                self.json_response(202,{'ok':True});return
            except (OSError,ValueError) as exc:self.json_response(400,{'error':str(exc)});return
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
                    atomic(CONTROL_FILE,{'enabled':STATE['enabled'],'goal':STATE['goal']})
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
            if 'enabled' in body:
                STATE['enabled']=bool(body['enabled'])
                if STATE['enabled']:
                    global FEEDBACK
                    FEEDBACK=Feedback(CONTROL_SETTINGS);STATE['recovery_reason']='';STATE['feedback']={}
            if 'goal' in body:STATE['goal']=str(body['goal'])[:1000];HISTORY.clear()
            atomic(CONTROL_FILE,{'enabled':STATE['enabled'],'goal':STATE['goal']})
        self.json_response(200,{'ok':True})
    def json_response(self,code,value):
        data=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass

def main():
    BRIDGE.mkdir(parents=True,exist_ok=True);(ROOT/'logs').mkdir(exist_ok=True)
    saved=readjson(CONTROL_FILE)
    STATE.update({key:saved[key] for key in ['enabled','goal'] if key in saved})
    try:
        records=[json.loads(line) for line in console_log().read_text().splitlines()[-30:]]
        CONSOLE['history']=records
    except (OSError,ValueError):pass
    records=[readjson(p) for p in sorted((EPISODES).glob('*.json'))]
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
    print('Minecraft monitor: http://127.0.0.1:8790',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8790),Handler).serve_forever()

if __name__=='__main__':main()
