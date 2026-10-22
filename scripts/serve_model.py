"""Launch selected checkpoint with a model-specific GPU budget."""
from pathlib import Path
import json,os,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import model_config
import local_environment

def launch_config(conf,profile):
    if profile not in ('cpu','balanced'):raise SystemExit('Usage: serve_model.sh [cpu|balanced]')
    layers=0 if profile=='cpu' else int(os.environ.get('MODEL_GPU_LAYERS',conf['gpu_layers']))
    vision=profile!='cpu' and os.environ.get('MODEL_VISION_GPU','1')=='1'
    engine=local_environment.llama_server()
    cmd=[engine,'-lv',os.environ.get('MODEL_LOG_LEVEL','4'),'-m',str(ROOT/conf['model']),'--mmproj',str(ROOT/conf['vision']),
         '--gpu-layers',str(layers),'--mmproj-offload' if vision else '--no-mmproj-offload',
         '--host','127.0.0.1','--port','8789','--alias','gamescaling','--ctx-size','8192','--parallel','1',
         '--cache-ram','0','--ctx-checkpoints','2',
         '--threads','6','--threads-batch','6','--batch-size','128','--ubatch-size','64',
         '--special','--jinja','--chat-template-file',str(ROOT/conf['template']),
         '--reasoning-format','none','--no-context-shift']
    if profile=='cpu':cmd[1:1]=['--device','none']
    all_tensors_gpu=conf['key']=='2b' and profile!='cpu' and layers>=25
    if all_tensors_gpu:cmd.extend(['--override-tensor','.*=CUDA0'])
    metadata={**conf,'profile':profile,'gpu_layers_requested':layers,'vision_gpu':vision,'time':time.time()}
    metadata['all_tensors_gpu']=all_tensors_gpu
    metadata['cache_ram_mib']=0
    return cmd,metadata

def main():
    profile=sys.argv[1] if len(sys.argv)>1 else 'balanced'
    conf=model_config.config();cmd,metadata=launch_config(conf,profile)
    target=ROOT/'runtime/model-active.json';tmp=target.with_suffix('.tmp')
    tmp.write_text(json.dumps(metadata,ensure_ascii=False,indent=2));tmp.replace(target)
    print('Starting '+conf['label']+' / '+profile,flush=True)
    os.environ['LD_LIBRARY_PATH']=str(Path(cmd[0]).parent)+os.pathsep+os.environ.get('LD_LIBRARY_PATH','')
    os.execv(cmd[0],cmd)

if __name__=='__main__':main()
