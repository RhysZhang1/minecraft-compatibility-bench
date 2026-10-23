"""Reproduce local official 2B -> F16 + Q4_K_M + vision GGUF conversion."""
from pathlib import Path
import hashlib,importlib.metadata,json,os,shutil,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import local_environment
SOURCE=ROOT/'models/GameScaling-2B-S1'
OUTPUT=ROOT/'models/GameScaling-2B-S1-GGUF'
LLAMA=local_environment.llama_source()
REVISION='8036a8f05659f3ce79c4b98f0ccbee4142a0b53d'
SOURCE_HASH='320dd2f7e1804faceae76fbfd6bfb83f17c9294a369bebf07cf1f3278dec3351'

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(16*1024*1024),b''):h.update(block)
    return h.hexdigest()

def convert_atomic(target,command):
    """A failed conversion must never masquerade as a complete output on retry."""
    if target.exists():return
    temporary=target.with_name(target.stem+'.partial.gguf')
    args=[str(temporary) if str(part)==str(target) else part for part in command]
    try:
        subprocess.run(args,cwd=ROOT,check=True)
        with temporary.open('rb') as f:
            if f.read(4)!=b'GGUF':raise ValueError('转换没有生成有效GGUF：'+str(temporary))
        temporary.replace(target)
    finally:temporary.unlink(missing_ok=True)

def main():
    OUTPUT.mkdir(exist_ok=True,parents=True)
    weights=SOURCE/'model.safetensors'
    if not weights.exists():raise SystemExit('先下载官方2B检查点，固定版本：'+REVISION)
    print('Verifying official 2B safetensors…',flush=True)
    if digest(weights)!=SOURCE_HASH:raise SystemExit('Source checkpoint SHA256 mismatch')
    with weights.open('rb') as f:
        length=struct.unpack('<Q',f.read(8))[0];header=json.loads(f.read(length))
    mtp=[name for name in header if 'mtp.' in name]
    convert=[sys.executable,str(LLAMA/'convert_hf_to_gguf.py'),str(SOURCE),'--outtype','f16']
    f16=OUTPUT/'GameScaling-2B-S1.f16.gguf'
    q4=OUTPUT/'GameScaling-2B-S1.Q4_K_M.gguf'
    vision=OUTPUT/'GameScaling-2B-S1.mmproj-f16.gguf'
    commands=[convert+['--no-nextn','--outfile',str(f16)],
              convert+['--mmproj','--outfile',str(vision)],
              [str(LLAMA/'build/bin/llama-quantize'),str(f16),str(q4),'Q4_K_M','8']]
    for target,command in zip([f16,vision,q4],commands):
        convert_atomic(target,command)
    shutil.copy2(SOURCE/'chat_template.jinja',OUTPUT/'chat_template.jinja')
    hashes={p.name:{'size':p.stat().st_size,'sha256':digest(p)} for p in [q4,vision]}
    (ROOT/'models-2b-checksums.json').write_text(json.dumps(hashes,indent=2))
    record={'checkpoint':'THUSI-Lab/GameScaling-2B-S1','revision':REVISION,'source_sha256':SOURCE_HASH,
            'source_mtp_tensor_count':len(mtp),'conversion':'Local llama.cpp; text uses --no-nextn, vision F16, text Q4_K_M',
            'llama_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=LLAMA,text=True).strip(),
            'converter_sha256':digest(LLAMA/'convert_hf_to_gguf.py'),
            'conversion_dependencies':{name:importlib.metadata.version(name) for name in ['torch','numpy','safetensors','transformers','sentencepiece','protobuf']},
            'commands':[[part.replace(str(ROOT)+'/','').replace(str(LLAMA)+'/','${LLAMA_CPP_SOURCE}/') for part in c] for c in commands],
            'files':hashes}
    (ROOT/'models-2b-manifest.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2),flush=True)

if __name__=='__main__':main()
