# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent game notes, separating observed facts, user notes and model proposals."""
from pathlib import Path
import datetime,hashlib,json,math,os,tempfile,threading,time

NEXT_STEPS={
    'inspect_quest_book':('查看任务书，核实当前任务要求。','Inspect the Quest Book and verify requirements.'),
    'check_inventory':('检查当前背包，核实物品及数量。','Check current inventory and item counts.'),
    'check_nei_recipe':('在当前可用的配方界面核实配方和工具。','Verify the recipe and required tools in the available recipe interface.'),
    'collect_goal_items':('核实任务要求后，尝试收集目标物品。','After verifying requirements, collect the objective items.'),
    'find_safe_ground':('先确认脚下和周围地形安全。','Check the nearby terrain for safety.'),
    'continue_current_goal':('继续当前目标，先核实尚未确认的步骤。','Continue the current objective and verify unconfirmed steps.')}
UNKNOWNS={'inventory':'当前物品','recipe':'配方或工具','quest_status':'任务完成情况','base_location':'基地位置'}
SCHEMA={'type':'object','additionalProperties':False,'properties':{
    'next_step':{'type':'string','enum':list(NEXT_STEPS)},
    'uncertain':{'type':'array','items':{'type':'string','enum':list(UNKNOWNS)},'maxItems':4}},
    'required':['next_step','uncertain']}

def readjson(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return {} if default is None else default

def replace(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:f.write(text);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def safe_text(value):
    return str(value).replace('<|','＜|').replace('|>','|＞').replace('<__media_','＜__media_')

def stamp(value):
    if not value:return '尚无记录'
    return datetime.datetime.fromtimestamp(value,datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S +08:00')

class AgentMemory:
    def __init__(self,root,folder=None,world_id=None):
        self.root=Path(root);self.folder=Path(folder) if folder else self.root/'memory';self.world_id=world_id;self.lock=threading.RLock()
        self.pending=False;self.running=False;self.error='';self.last_checkpoint=0

    def ensure(self,goal):
        with self.lock:
            self.folder.mkdir(parents=True,exist_ok=True)
            if self.world_id:
                identity=readjson(self.folder/'world.json')
                if identity and identity.get('world_id')!=self.world_id:raise ValueError('记忆属于另一个世界，请为新世界选择独立记忆目录')
                if not identity:replace(self.folder/'world.json',json.dumps({'world_id':self.world_id}))
            files={'agent_prompt.md':(self.root/'config/agent-prompt.default.md').read_text(),
                   'user_notes.md':'','settings.json':json.dumps({'auto_summary':True,'summary_interval':50})}
            for name,text in files.items():
                if not (self.folder/name).exists():replace(self.folder/name,text)
            self.checkpoint(goal,{},0)

    def config(self):
        def read(name):
            try:return (self.folder/name).read_text()
            except OSError:return ''
        settings=readjson(self.folder/'settings.json',{'auto_summary':True,'summary_interval':50})
        instructions=read('agent_prompt.md');notes=read('user_notes.md')
        revision=hashlib.sha256(json.dumps([instructions,notes,settings],sort_keys=True).encode()).hexdigest()
        return {'instructions':instructions,'notes':notes,'auto_summary':bool(settings.get('auto_summary',True)),
                'summary_interval':max(10,min(500,int(settings.get('summary_interval',50)))),'revision':revision}

    def save_config(self,body,goal):
        with self.lock:
            old=self.config()
            if body.get('revision')!=old['revision']:raise ValueError('笔记已在其他位置更新，请先刷新记忆再保存')
            values={key:body.get(key,old[key]) for key in ['instructions','notes']}
            if not all(isinstance(v,str) for v in values.values()):raise ValueError('提示词和笔记必须是文本')
            if len(goal)+sum(len(v) for v in values.values())>2000:raise ValueError('目标、固定提示词和笔记合计最多2000字，请精简后保存')
            interval=body.get('summary_interval',old['summary_interval'])
            if not isinstance(interval,int) or isinstance(interval,bool) or not 10<=interval<=500:raise ValueError('自动整理间隔应为10至500轮')
            if not isinstance(body.get('auto_summary',True),bool):raise ValueError('自动整理选项无效')
            self.archive('before-edit')
            replace(self.folder/'agent_prompt.md',values['instructions'])
            replace(self.folder/'user_notes.md',values['notes'])
            replace(self.folder/'settings.json',json.dumps({'auto_summary':body.get('auto_summary',old['auto_summary']),'summary_interval':interval}))
            self.checkpoint(goal,{},0)

    def checkpoint(self,goal,game,step,archive=False):
        with self.lock:
            state=readjson(self.folder/'state.json')
            state['goal']=goal;state['last_step']=max(step,state.get('last_step',0))
            state.setdefault('initial_step',step)
            # Old snapshots remain labelled as old; unavailable inventory is never "empty".
            if game.get('connected') and time.time()*1000-game.get('timestamp',0)<10000:
                previous=state.get('observed',{})
                fields=['timestamp','player','dimension','x','y','z','health','screen','inventory','inventory_error']
                state['observed']={k:game[k] for k in fields if k in game}
                if all(k in game for k in ('x','z')):
                    area=[game.get('dimension',0),math.floor(game['x']/16),math.floor(game['z']/16)]
                    route=state.get('recent_areas',[])
                    if not route or route[-1]!=area:state['recent_areas']=(route+[area])[-16:]
                if 'inventory' in previous and 'inventory' in game and not previous.get('inventory_error') and not game.get('inventory_error'):
                    def counts(items):
                        result={}
                        for i in items:result[i['item']]=result.get(i['item'],0)+i['count']
                        return result
                    before=counts(previous['inventory']);after=counts(game['inventory'])
                    changes=[{'time':game['timestamp']/1000,'item':k,'delta':after.get(k,0)-before.get(k,0)} for k in sorted(before.keys()|after.keys()) if before.get(k,0)!=after.get(k,0)]
                    state['inventory_changes']=(state.get('inventory_changes',[])+changes)[-8:]
            state['updated_at']=time.time()
            replace(self.folder/'state.json',json.dumps(state,ensure_ascii=False,indent=2))
            replace(self.folder/'current.md',self.document(state))
            self.last_checkpoint=time.monotonic()
            if archive:self.archive('checkpoint')
            return state

    def document(self,state):
        config=self.config();facts=state.get('observed',{});proposal=state.get('proposal',{})
        lines=['# Minecraft 续玩笔记','','## 当前目标',state.get('goal','待设置'),'','## 已确认的最近观测',
               '- 来源：客户端状态接口；时间：'+stamp(facts.get('timestamp',0)/1000),
               '- 位置：'+self.position(facts)+'；生命：'+str(facts.get('health','待确认')),
               '- 界面：'+(facts.get('screen') or '游戏中/尚未连接'),'- 玩家：'+facts.get('player','GameScalingBot')]
        if 'inventory' in facts and not facts.get('inventory_error'):
            lines.append('- 背包槽位快照（不含箱子等外部容器）：')
            lines.extend('  - 槽位{slot}：{name} / {item} ×{count}'.format(**i) for i in facts['inventory'])
            if not facts['inventory']:lines.append('  - 当前接口提供的槽位为空。')
        else:lines.append('- 背包：尚未取得可靠快照，请在游戏中核实。')
        lines+=['- 近期到访区块（维度/区块X/区块Z，不代表完整探索）：'+str(state.get('recent_areas',[])[-8:])]
        for change in state.get('inventory_changes',[])[-4:]:
            lines.append('- 物品数量变化：'+change['item']+f' {change["delta"]:+d}；'+stamp(change['time']))
        lines+=['- 任务完成情况：未接入任务完成验证，不能从动作日志推定已完成。','','## 用户提供的笔记',config['notes'] or '暂无。',
                '','## 模型整理建议（未确认）']
        if proposal:
            lines+=['- '+NEXT_STEPS[proposal['next_step']][0],'- 待确认：'+('、'.join(UNKNOWNS[u] for u in proposal['uncertain']) or '仍需以当前画面核实。'),
                    '- 整理时间：'+stamp(state.get('summary_at'))]
        else:lines+=['尚未整理。模型建议不会改写已确认事实。']
        lines+=['','## 固定提示词',config['instructions'],'','## 记录说明',
                '这是本项目同一测试世界的续玩记录。坐标和物品是上次观测值，恢复时以新画面/新状态为准。',
                '模型只选择续玩建议和待确认事项；已确认事实由程序采集。当前目标不代表已完成。']
        return '\n'.join(lines)+'\n'

    @staticmethod
    def position(facts):
        if not all(k in facts for k in ('x','y','z')):return '待确认'
        return ', '.join(f'{facts[k]:.1f}' for k in ('x','y','z'))

    def prompt_context(self):
        with self.lock:
            c=self.config();state=readjson(self.folder/'state.json');facts=state.get('observed',{})
            inventory=facts.get('inventory') if not facts.get('inventory_error') else None
            items='unknown' if inventory is None else ', '.join(f'{i["item"]} x{i["count"]} (slot {i["slot"]})' for i in inventory[:12]) or 'empty'
            proposal=state.get('proposal',{})
            lines=['Persistent notes for this test world. Old observations are not proof of current state.',
                   'User instructions: '+c['instructions'],'User notes (user supplied): '+c['notes'],
                   f'Last observed position: {self.position(facts)}. Health: {facts.get("health","unknown")}. Observed at: {stamp(facts.get("timestamp",0)/1000)}.',
                   'Inventory snapshot: '+items+'. Quest completion: NOT VERIFIED. Never treat a goal as completed.']
            lines+=['Recent visited areas [dimension, chunk X, chunk Z]: '+json.dumps(state.get('recent_areas',[])[-6:])+'. These are observed visits, not proof of full exploration.']
            if proposal:lines+=['Unverified suggested next step: '+NEXT_STEPS[proposal['next_step']][1]]
            return safe_text('\n'.join(lines))[:3000]

    def due(self,step):
        with self.lock:
            config=self.config();state=readjson(self.folder/'state.json')
            baseline=max(state.get('summary_step',0),state.get('last_attempt_step',0),state.get('initial_step',step))
            return not self.running and (self.pending or (config['auto_summary'] and step-baseline>=config['summary_interval']))

    def summary_input(self,goal,game,step):
        state=self.checkpoint(goal,game,step)
        if 'initial_step' not in state:
            state['initial_step']=step;replace(self.folder/'state.json',json.dumps(state,ensure_ascii=False,indent=2))
        return {'goal':goal,'observed':state.get('observed',{}),'user_notes':self.config()['notes'],
                'verified_quest_completion':'unknown','previous_suggestion':state.get('proposal',{})}

    def summary_request(self,goal,game,step):
        facts=self.summary_input(goal,game,step)
        prompt='<|im_start|>system\nYou maintain Minecraft continuation notes. Choose one safe next step using ONLY the supplied facts. Goals are not completed quests. Mark unknowns. Return the required JSON object, not game actions. No coordinates or invented items in your answer.<|im_end|>\n<|im_start|>user\n'+safe_text(json.dumps(facts,ensure_ascii=False))+'<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
        return {'prompt':prompt,'stream':False,'temperature':0.,'n_predict':192,'cache_prompt':False,'json_schema':SCHEMA,'stop':['<|im_end|>']}

    def apply_summary(self,raw,step,model):
        value=json.loads(raw)
        if not isinstance(value,dict) or set(value)!={'next_step','uncertain'}:raise ValueError('整理结果结构不完整')
        if not isinstance(value['next_step'],str) or value['next_step'] not in NEXT_STEPS or not isinstance(value['uncertain'],list) or len(value['uncertain'])>4 or any(not isinstance(u,str) or u not in UNKNOWNS for u in value['uncertain']):raise ValueError('整理结果超出允许的续玩建议范围')
        with self.lock:
            state=readjson(self.folder/'state.json');state.update(proposal=value,summary_at=time.time(),summary_step=step,summary_model=model)
            replace(self.folder/'state.json',json.dumps(state,ensure_ascii=False,indent=2))
            replace(self.folder/'current.md',self.document(state));self.archive('summary')
            self.error='';self.pending=False

    def summary_failed(self,error,step):
        with self.lock:
            self.error=str(error);self.pending=False
            state=readjson(self.folder/'state.json');state['last_attempt_step']=step
            replace(self.folder/'state.json',json.dumps(state,ensure_ascii=False,indent=2))

    def archive(self,reason):
        p=self.folder/'current.md'
        if p.exists():
            target=self.folder/'history'/(time.strftime('%Y%m%d-%H%M%S')+f'-{time.time_ns()%1000000:06d}-{reason}.md')
            replace(target,p.read_text())

    def view(self,goal):
        with self.lock:
            c=self.config();s=readjson(self.folder/'state.json')
            document_path=self.folder/'current.md'
            if document_path.is_relative_to(self.root):document_path=document_path.relative_to(self.root)
            return {**c,'goal':goal,'document':self.document(s),'summary_at':s.get('summary_at'),
                    'summary_step':s.get('summary_step'),'pending':self.pending,'running':self.running,'error':self.error,
                    'path':str(document_path),'prompt_chars':len(self.prompt_context()),'updated_at':s.get('updated_at')}
