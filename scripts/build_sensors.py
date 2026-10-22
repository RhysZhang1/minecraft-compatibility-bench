"""Build optional read-only telemetry; redistribute only our classes and BSD ASM."""
from pathlib import Path
import os,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));import instance_config as ic
sdk=sorted(ROOT.glob('sensors/sdk/asm*.jar'))
if not sdk:sdk=[*ROOT.glob('instances/client/libraries/*forgePatches.jar'),*ic.library_root().glob('libraries/com/github/GTNewHorizons/lwjgl3ify/*/*forgePatches.jar')]
if not sdk:raise SystemExit('缺少ASM编译库；源码归档内含已编译release/gamescaling-sensors-agent.jar，可先恢复该文件，或通过setup.sh准备ASM SDK')
folder=ROOT/'sensors';build=folder/'build';build.mkdir(exist_ok=True)
subprocess.run(['javac','--release','8','-cp',os.pathsep.join(map(str,sdk)),'-d',str(build),*map(str,(folder/'src/gssensors').glob('*.java'))],check=True)
manifest='Manifest-Version: 1.0\nPremain-Class: gssensors.SensorAgent\n\n'
with zipfile.ZipFile(folder/'gamescaling-sensors-agent.jar','w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('META-INF/MANIFEST.MF',manifest)
 for p in build.rglob('*.class'):z.write(p,str(p.relative_to(build)))
 added=set()
 for p in sdk:
  with zipfile.ZipFile(p) as source:
   for name in source.namelist():
    if name.startswith('org/objectweb/asm/') and name.endswith('.class') and name not in added:z.writestr(name,source.read(name));added.add(name)
print(folder/'gamescaling-sensors-agent.jar')
