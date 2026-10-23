# SPDX-License-Identifier: GPL-3.0-or-later
"""Live acceptance test against the copied client, without desktop input injection."""
from pathlib import Path
import hashlib, json, time, urllib.request
ROOT=Path(__file__).resolve().parents[1]
BRIDGE=ROOT/'runtime/bridge'
http=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def read(name):
    try:return json.loads((BRIDGE/name).read_text())
    except (OSError,ValueError):return {}

def write(name,value):
    target=BRIDGE/name;tmp=target.with_suffix('.verify.tmp')
    tmp.write_text(json.dumps(value));tmp.replace(target)

def until(check,timeout=30):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=check()
        if value:return value
        time.sleep(.1)
    raise TimeoutError('Client did not acknowledge the input acceptance test')

def command(steps=None,mouse=None):
    ident=max(int(time.time()*1000),read('state.json').get('command_id',0)+1)
    write('command.json',{'id':ident,'mouse':mouse or [0,0,0],'steps':steps or [[] for _ in range(6)]})
    until(lambda:read('completed.json').get('id')==ident)
    return until(lambda:(s:=read('state.json')).get('command_id')==ident and not s.get('busy') and s)

def main():
    http.open(urllib.request.Request('http://127.0.0.1:8790/api/control',
        data=b'{"enabled":false}',headers={'Content-Type':'application/json'})).close()
    until(lambda:not json.load(http.open('http://127.0.0.1:8790/api/status')).get('inference_started'),timeout=120)
    initial=until(lambda:(s:=read('state.json')).get('connected') and
                  s.get('window_visible') is False and time.time()*1000-s['timestamp']<3000 and s,timeout=180)
    assert initial['input_isolated'] and initial['cursor_free'] and not initial['physical_focused'],initial
    if initial['screen']:command([['Esc']]+[[] for _ in range(5)])
    until(lambda:not read('state.json').get('screen'))
    before=read('state.json');frame_before=hashlib.sha256((BRIDGE/'frame.jpg').read_bytes()).hexdigest()
    ident=int(time.time()*1000);write('input-probe.json',{'id':ident})
    try:
        probe=until(lambda:(p:=read('input-probe-result.json')).get('id')==ident and p)
    finally:(BRIDGE/'input-probe.json').unlink(missing_ok=True)
    assert probe['blocked_callback_count']==5,probe
    assert all(v for k,v in probe.items() if k not in ('id','timestamp','blocked_callback_count')),probe
    time.sleep(1.5);after_physical=read('state.json')
    assert abs(after_physical['yaw']-before['yaw'])<.001,(before,after_physical)
    assert after_physical['screen']==before['screen'],(before,after_physical)
    moved=command([['W'] for _ in range(6)],[30,0,0])
    distance=sum((moved[a]-after_physical[a])**2 for a in ('x','z'))**.5
    assert distance>.1,('No movement; check nearby terrain',distance,moved)
    assert abs(moved['yaw']-after_physical['yaw'])>1,moved
    inventory=command([['E']]+[[] for _ in range(5)])
    assert inventory['screen']=='GuiInventory',inventory
    closed=command([['Esc']]+[[] for _ in range(5)])
    assert not closed['screen'] and not closed['busy'],closed
    assert closed['input_isolated'] and closed['cursor_free'] and not closed['window_visible'] and not closed['physical_focused'],closed
    frame_after=hashlib.sha256((BRIDGE/'frame.jpg').read_bytes()).hexdigest()
    assert frame_before!=frame_after,'Hidden rendering did not update'
    result={'timestamp':time.time(),'callback_probe':probe,'before':before,
            'after_physical_callbacks':after_physical,'after_virtual_move':moved,
            'horizontal_displacement':distance,'inventory':inventory,'final':closed,
            'frame_changed':frame_before!=frame_after,
            'scope':'Actual hidden client; callback replay and virtual input, no human hardware test'}
    target=ROOT/'runtime/input-isolation-validation.json';target.write_text(json.dumps(result,indent=2))
    print(json.dumps({'passed':True,'distance':round(distance,3),'hidden':not closed['window_visible'],
                      'unfocused':not closed['physical_focused'],'evidence':str(target)}))

if __name__=='__main__':main()
