from pathlib import Path
import os, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(ROOT/'scripts/build_input.py')],check=True)
LIB=Path(os.environ.get('HMCL_GAME_ROOT','/home/rhys/.config/hmcl/.minecraft'))/'libraries'
build=ROOT/'bridge/build';build.mkdir(parents=True,exist_ok=True)
cp=os.pathsep.join(map(str,[ROOT/'input/gamescaling-input-state.jar',ROOT/'instances/server/forge-1.7.10-10.13.4.1614-1.7.10-universal.jar',
    *LIB.glob('com/google/code/gson/gson/*/*.jar'),*LIB.glob('com/google/guava/guava/17.0/*.jar')]))
subprocess.run(['javac','--release','8','-cp',cp,'-d',str(build),str(ROOT/'bridge/src/GameScalingBridge.java')],check=True)
target=ROOT/'instances/client/mods/GameScalingBridge-1.0.jar'
subprocess.run(['jar','cf',str(target),'-C',str(build),'.'],check=True)
print(target)
