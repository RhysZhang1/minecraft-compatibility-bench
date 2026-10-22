"""Restore verified project-built bridge binaries from a source release archive."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
def prepare():
 manifest=ROOT/'SOURCE-MANIFEST.json'
 if not manifest.exists():return
 expected=json.loads(manifest.read_text())
 for source,target in [('gamescaling-sensors-agent.jar','sensors/gamescaling-sensors-agent.jar'),('libgamescaling-ei.so','input/libgamescaling-ei.so'),('gamescaling-input-agent.jar','input/gamescaling-input-agent.jar'),('gamescaling-input-state.jar','input/gamescaling-input-state.jar')]:
  p=ROOT/'release'/source;out=ROOT/target
  if out.exists() or not p.exists():continue
  info=expected.get('release/'+source,{})
  if hashlib.sha256(p.read_bytes()).hexdigest()!=info.get('sha256'):raise ValueError('release文件校验失败：'+source)
  out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
if __name__=='__main__':prepare()
