"""Optional reproducible project-local llama.cpp build; never resets existing trees."""
from pathlib import Path
import argparse,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import local_environment as env
REVISION='680a9ae63d60d35c21a0dcd7d3fabdb9c6bfc963'
def build(folder,cuda=True,jobs=2):
 folder=Path(folder).expanduser().resolve()
 if folder.exists():raise ValueError('目标目录已存在，不覆盖或重置；请选择一个新目录')
 folder.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['git','clone','--no-checkout','https://github.com/ggml-org/llama.cpp.git',str(folder)],check=True)
 subprocess.run(['git','checkout','--detach',REVISION],cwd=folder,check=True)
 subprocess.run(['cmake','-S',str(folder),'-B',str(folder/'build'),'-DCMAKE_BUILD_TYPE=Release','-DLLAMA_CURL=OFF','-DGGML_CUDA='+('ON' if cuda else 'OFF')],check=True)
 subprocess.run(['cmake','--build',str(folder/'build'),'--target','llama-server','llama-quantize','-j',str(jobs)],check=True)
 env.save({'llama_source':str(folder),'llama_server':str(folder/'build/bin/llama-server')});print(folder/'build/bin/llama-server')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder');p.add_argument('--cpu',action='store_true');p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.folder,not a.cpu,a.jobs)
