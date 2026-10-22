"""Build the process-local input agent from the already installed GTNH ASM runtime."""
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));import instance_config
sdk=[*instance_config.client_directory().glob('libraries/*forgePatches.jar'),*instance_config.library_root().glob('libraries/com/github/GTNewHorizons/lwjgl3ify/*/*forgePatches.jar')]
if not sdk:raise RuntimeError('该输入后端需要lwjgl3ify的forgePatches SDK；请运行setup.sh检查环境')
folder = ROOT / 'input'
build = folder / 'build'
build.mkdir(exist_ok=True)
subprocess.run(['javac', '--release', '8', '-cp', str(sdk[0]),
                '-d', str(build), *map(str, sorted((folder/'src').rglob('*.java')))], check=True)
subprocess.run(['jar', 'cf', str(folder/'gamescaling-input-state.jar'), '-C', str(build), 'gsinput'], check=True)
manifest = build / 'MANIFEST.MF'
manifest.write_text('Manifest-Version: 1.0\nPremain-Class: local.gamescaling.input.InputAgent\n'
                    'Boot-Class-Path: gamescaling-input-state.jar\n\n')
subprocess.run(['jar', 'cfm', str(folder/'gamescaling-input-agent.jar'), str(manifest),
                '-C', str(build), 'local'], check=True)
print(folder/'gamescaling-input-agent.jar')
