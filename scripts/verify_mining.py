# SPDX-License-Identifier: GPL-3.0-or-later
"""Live survival mining acceptance with a temporary, cleaned-up air-space fixture.

Pauses AI, keeps original inventory, restores position; does not credit model ability.
"""
from pathlib import Path
import json,math,os,signal,sys,time,urllib.request
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
import server_console,manage
from verify_input import read,write,until
URL='http://127.0.0.1:8790'

def api(path,body=None):
    req=urllib.request.Request(URL+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)

def packet(keys=None,mouse=None,sustain=False):
    ident=max(int(time.time()*1000),read('state.json').get('command_id',0)+1)
    write('command.json',{'id':ident,'mouse':mouse or [0,0,0],'steps':keys or [[] for _ in range(6)],
                          'epoch':read('safety.json')['epoch'],'sustain_mining':sustain})
    done=until(lambda:(d:=read('completed.json')).get('id')==ident and d)
    return done

def count_dirt():return sum(i['count'] for i in read('state.json').get('inventory',[]) if i['item']=='minecraft:dirt')

def main():
    api('/api/control',{'enabled':False})
    until(lambda:not api('/api/status').get('inference_started'),120)
    origin=read('state.json');assert origin.get('connected') and not origin.get('screen')
    # These blocks must all be air before any edits. Only this fixture is removed.
    x=math.floor(origin['x'])+8;z=math.floor(origin['z'])+8;y=180
    platform=[(x+dx,y-1,z+dz) for dx in range(-2,3) for dz in range(-2,4)]
    target=(x,y+1,z+2);backstop=(x,y+1,z+3);places=platform+[target,backstop]
    for pos in places:
        reply=server_console.execute('testforblock %d %d %d minecraft:air'%pos)
        assert 'Successfully' in reply,(pos,reply)
    proof={'time':time.time(),'origin':origin,'fixture':places,'steps':{},'scope':'Scripted executor acceptance, not autonomous model mining'}
    recovery=ROOT/'runtime/mining-test-recovery.json';recovery.write_text(json.dumps(proof,indent=2))
    stopped=None
    def place(pos,name):return server_console.execute('setblock %d %d %d minecraft:%s'%(*pos,name))
    def look(yaw,pitch):
        for _ in range(4):
            current=read('state.json');dyaw=(yaw-current['yaw']+180)%360-180;dpitch=pitch-current['pitch']
            if abs(dyaw)<.1 and abs(dpitch)<.1:return
            packet(mouse=[max(-1000,min(1000,dyaw*1000/current['width']/.15)),max(-1000,min(1000,dpitch*1000/current['height']/.15)),0])
            time.sleep(.6)
        raise AssertionError('Could not align test camera')
    def teleport(yaw=0):
        result=server_console.execute(f'tp GameScalingBot {x+.5} {y} {z+.5}')
        assert 'Teleported' in result,result
        until(lambda:abs(read('state.json').get('x',0)-(x+.5))<.1)
        time.sleep(.6)
        look(yaw,0)
    try:
        for pos in platform:place(pos,'glass')
        place(target,'dirt');place(backstop,'bedrock');teleport()
        packet([['one']]+[[] for _ in range(5)])
        until(lambda:(s:=read('state.json')).get('target_block',{}).get('block')=='minecraft:dirt' and s)
        before=count_dirt();proof['inventory_before']=read('state.json')['inventory']
        # Old behaviour: three independent 200ms presses with inference-sized gaps.
        for _ in range(3):packet([['LB'] for _ in range(6)]);time.sleep(1.4)
        still=server_console.execute('testforblock %d %d %d minecraft:dirt'%target)
        assert 'Successfully' in still,still
        proof['steps']['old_bounded_press']={'attempts':3,'block_remained':True}
        start=time.time();ack=packet([['LB'] for _ in range(6)],sustain=True)
        assert ack['mining_continues'],ack
        ended=until(lambda:(r:=read('mining-result.json')).get('started',0)>=start*1000 and r,20)
        air=server_console.execute('testforblock %d %d %d minecraft:air'%target)
        assert 'Successfully' in air,(air,ended)
        proof['steps']['continuous_mining']={'ack':ack,'end':ended,'block_broken':True,'elapsed':time.time()-start}
        for _ in range(3):
            packet([['W'] for _ in range(6)]);time.sleep(.7)
            if count_dirt()>before:break
        until(lambda:count_dirt()>before,10)
        proof['inventory_after']=read('state.json')['inventory'];proof['dirt_gained']=count_dirt()-before
        (ROOT/'runtime/mining-success.jpg').write_bytes((ROOT/'runtime/bridge/frame.jpg').read_bytes())
        # A hard block provides time to verify cancellation without breaking it.
        place(target,'bedrock');teleport()
        until(lambda:read('state.json').get('target_block',{}).get('block')=='minecraft:bedrock')
        ack=packet([['LB'] for _ in range(6)],sustain=True);assert ack['mining_continues']
        until(lambda:read('state.json').get('mining_active'))
        paused_at=time.time();api('/api/control',{'enabled':False})
        until(lambda:not read('state.json').get('mining_active'))
        proof['steps']['pause_release']={'seconds':time.time()-paused_at,'reason':read('state.json').get('mining_stop')}
        # Freeze just the observer: its heartbeat must expire while the game runs.
        ack=packet([['LB'] for _ in range(6)],sustain=True);assert ack['mining_continues']
        until(lambda:read('state.json').get('mining_active'))
        stopped=manage.owned('monitor');assert stopped
        frozen=time.time();os.kill(stopped,signal.SIGSTOP)
        try:until(lambda:not read('state.json').get('mining_active'),5)
        finally:os.kill(stopped,signal.SIGCONT);stopped=None
        proof['steps']['watchdog_release']={'seconds':time.time()-frozen,'reason':read('state.json').get('mining_stop')}
        time.sleep(.5)
        # No next action is sent: target change alone must end the hold.
        ack=packet([['LB'] for _ in range(6)],sustain=True);assert ack['mining_continues']
        until(lambda:read('state.json').get('mining_active'))
        place(target,'stone');until(lambda:not read('state.json').get('mining_active'))
        proof['steps']['target_change_release']=read('mining-result.json')
        place(target,'bedrock');time.sleep(.6);ack=packet([['LB'] for _ in range(6)],sustain=True);assert ack['mining_continues']
        ended=until(lambda:(r:=read('mining-result.json')).get('started',0)>=ack['time'] and r.get('reason')=='maximum hold reached' and r,15)
        proof['steps']['maximum_hold_release']=ended
        # Existing callback probe reads the actual isolated left-button poll.
        probe_id=int(time.time()*1000);write('input-probe.json',{'id':probe_id})
        try:probe=until(lambda:(p:=read('input-probe-result.json')).get('id')==probe_id and p)
        finally:(ROOT/'runtime/bridge/input-probe.json').unlink(missing_ok=True)
        assert probe['released_LB_poll'],probe
        proof['steps']['actual_button_released']=probe
        proof['passed']=True
    finally:
        if stopped:os.kill(stopped,signal.SIGCONT)
        api('/api/control',{'enabled':False})
        # Restore the same scene; client 1.7 position includes the 1.62 eye offset.
        result=server_console.execute(f'tp GameScalingBot {origin["x"]} {origin["y"]-1.62} {origin["z"]}')
        proof['restore_reply']=result
        try:
            time.sleep(.7);look(origin['yaw'],origin['pitch'])
            selected=origin.get('target_block',{}).get('selected_slot')
            if isinstance(selected,int) and 0<=selected<9:
                packet([['one','two','three','four','five','six','seven','eight','nine'][selected: selected+1]]+[[] for _ in range(5)])
        finally:
            for pos in places:place(pos,'air')
            proof['cleanup_complete']=True
            (ROOT/'runtime/mining-validation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':proof.get('passed',False),'dirt_gained':proof.get('dirt_gained'),'evidence':'runtime/mining-validation.json'}))

if __name__=='__main__':main()
