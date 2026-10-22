from pathlib import Path
import json,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import instance_config as ic
from agent_memory import AgentMemory
import launch_game
class InstanceTests(unittest.TestCase):
    def test_worlds_do_not_share_default_memory_or_episodes(self):
        g=ic.config('gtnh');v=ic.config('vanilla-1-7-10')
        self.assertNotEqual(g['memory_directory'],v['memory_directory']);self.assertNotEqual(g['episodes_directory'],v['episodes_directory']);self.assertNotEqual(g['world_id'],v['world_id'])
        with patch.dict(os.environ,{'MC_INSTANCE':'vanilla-1-7-10'}):self.assertEqual(ic.pack_rules(),'')
    def test_unsupported_version_is_rejected_before_launch(self):
        settings={'selected':'fake','instances':{'fake':{**ic.config('gtnh'),'minecraft_version':'26.3'}}}
        with patch.object(ic,'settings',return_value=settings):
            with self.assertRaisesRegex(ValueError,'输入后端'):ic.config('fake')
    def test_memory_rejects_accidental_world_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'config').mkdir();(root/'config/agent-prompt.default.md').write_text('Generic instructions');folder=root/'notes';a=AgentMemory(root,folder,'world-a');a.ensure('test')
            b=AgentMemory(root,folder,'world-b')
            with self.assertRaisesRegex(ValueError,'world|世界'):b.ensure('test')
    def test_manifest_inherits_parent_and_keeps_child_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'versions/base';p.mkdir(parents=True)
            (p/'base.json').write_text(json.dumps({'id':'base','mainClass':'Base','libraries':[{'name':'parent:lib:1'}],'arguments':{'game':['--a'],'jvm':['-Da=1']}}))
            child=root/'child.json';child.write_text(json.dumps({'id':'child','inheritsFrom':'base','mainClass':'Child','libraries':[],'arguments':{'game':['--b']}}))
            with patch.object(launch_game,'SOURCE',root):value=launch_game.manifest(child)
            self.assertEqual(value['mainClass'],'Child');self.assertEqual(value['arguments']['game'],['--a','--b']);self.assertEqual(len(value['libraries']),1)
if __name__=='__main__':unittest.main()
