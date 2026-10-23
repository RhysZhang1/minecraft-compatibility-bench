# SPDX-License-Identifier: GPL-3.0-or-later
"""Outlive the monitor while it restarts into another registered instance."""
from pathlib import Path
import argparse,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import instance_config
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('instance');a=p.parse_args();instance_config.config(a.instance)
 subprocess.run([ROOT/'stop.sh'],cwd=ROOT,check=True,env={**os.environ,'MC_SWITCH_CHILD':'1'})
 subprocess.run([ROOT/'start.sh','--instance',a.instance,'--paused','--no-open'],cwd=ROOT,check=True)
