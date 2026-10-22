"""Build the process-local input agent from the already installed GTNH ASM runtime."""
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / 'input'
build = folder / 'build'
build.mkdir(exist_ok=True)
subprocess.run(['javac', '--release', '8', '-cp', str(ROOT/'instances/server/lwjgl3ify-forgePatches.jar'),
                '-d', str(build), *map(str, sorted((folder/'src').rglob('*.java')))], check=True)
subprocess.run(['jar', 'cf', str(folder/'gamescaling-input-state.jar'), '-C', str(build), 'gsinput'], check=True)
manifest = build / 'MANIFEST.MF'
manifest.write_text('Manifest-Version: 1.0\nPremain-Class: local.gamescaling.input.InputAgent\n'
                    'Boot-Class-Path: gamescaling-input-state.jar\n\n')
subprocess.run(['jar', 'cfm', str(folder/'gamescaling-input-agent.jar'), str(manifest),
                '-C', str(build), 'local'], check=True)
print(folder/'gamescaling-input-agent.jar')
