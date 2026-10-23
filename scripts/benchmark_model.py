# SPDX-License-Identifier: GPL-3.0-or-later
"""Replay saved screenshots/history against the active model; never execute actions."""
from pathlib import Path
import argparse,base64,json,statistics,subprocess,sys,threading,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import monitor

def main():
    p=argparse.ArgumentParser();p.add_argument('--episodes',type=int,nargs='+',required=True);a=p.parse_args()
    with monitor.OPENER.open('http://127.0.0.1:8790/api/status') as r:state=json.load(r)
    if state['enabled'] or state['inference_started']:raise SystemExit('Pause and finish the live inference before replaying screenshots')
    monitor.STATE['goal']=state['goal']
    samples=[];done=threading.Event()
    def sample():
        while not done.is_set():
            result=subprocess.run(['nvidia-smi','--query-gpu=memory.used,memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
            if result.returncode==0:
                used,free=map(int,result.stdout.strip().split(','));samples.append({'time':time.time(),'used_mb':used,'free_mb':free})
            done.wait(.25)
    thread=threading.Thread(target=sample,daemon=True);thread.start()
    results=[]
    try:
        for number in a.episodes:
            folder=ROOT/'runtime/episodes';monitor.HISTORY.clear()
            for old in range(max(1,number-5),number):
                stem=folder/f'{old:06d}'
                if not stem.with_suffix('.json').exists():continue
                record=json.loads(stem.with_suffix('.json').read_text())
                monitor.HISTORY.append((base64.b64encode(stem.with_suffix('.jpg').read_bytes()).decode(),record['action']))
            stem=folder/f'{number:06d}';previous=json.loads(stem.with_suffix('.json').read_text())
            frame=base64.b64encode(stem.with_suffix('.jpg').read_bytes()).decode()
            prompt=monitor.make_prompt(frame)
            started=time.monotonic()
            with monitor.request('/completion',{'prompt':prompt,'stream':False,'seed':123,'temperature':1.,'top_k':0,'top_p':1.,'min_p':0.,'repeat_penalty':1.,'n_predict':768,'stop':[monitor.ACTION_END],'cache_prompt':False},timeout=600) as r:
                reply=json.load(r)
            latency=time.monotonic()-started;raw='<think>'+reply.get('content','')
            if monitor.ACTION_END not in raw and reply.get('stop_type')=='word' and reply.get('stopping_word')==monitor.ACTION_END:raw+=monitor.ACTION_END
            action=monitor.parse_action(raw)
            item={'episode':number,'latency':latency,'baseline_seconds':previous['latency'],
                  'parsed':action.parsed,'raw':raw,'timings':reply.get('timings',{}),'executed':False}
            results.append(item);print(json.dumps({k:item[k] for k in ['episode','latency','baseline_seconds','parsed']},ensure_ascii=False),flush=True)
    finally:done.set();thread.join(timeout=6)
    output={'model':state['model'],'same_saved_screenshots_and_5_frame_history':True,
            'baseline_note':'Previously recorded 9B/8 GPU layer live timings; current replay uses fixed seed123 and full input processing. This is a small speed comparison, not a task capability evaluation.',
            'results':results,'gpu_samples':samples,'gpu_peak_mb':max(s['used_mb'] for s in samples),
            'gpu_min_free_mb':min(s['free_mb'] for s in samples),'median_seconds':statistics.median(r['latency'] for r in results),
            'baseline_median_seconds':statistics.median(r['baseline_seconds'] for r in results)}
    output['median_speedup']=output['baseline_median_seconds']/output['median_seconds']
    target=ROOT/'runtime/2b-replay-benchmark.json';target.write_text(json.dumps(output,ensure_ascii=False,indent=2));print(target,flush=True)

if __name__=='__main__':main()
