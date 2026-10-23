from pathlib import Path
import sys,unittest,tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import manage
import lifecycle

class OwnershipTests(unittest.TestCase):
    def test_display_publisher_is_one_service_with_its_compositor_supervisor(self):
        root=manage.ROOT;script=str(root/'scripts/virtual_display.py')
        def inspect(pid):return (['python3',script,'serve' if pid==100 else 'publish'],root)
        with patch.object(manage,'owned_pids',return_value=[100,101]),patch.object(manage,'inspect',side_effect=inspect),patch.object(manage.os,'getpgid',return_value=100),patch.object(Path,'write_text'),patch.object(manage.subprocess,'Popen') as spawn:
            self.assertFalse(manage.start('display'));spawn.assert_not_called()

    def test_replacement_client_cannot_reuse_old_connected_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'runtime/bridge').mkdir(parents=True);(root/'logs').mkdir()
            old=root/'runtime/bridge/state.json';old.write_text('{"connected":true}')
            def spawn(*args,**kwargs):
                self.assertFalse(old.exists(),'stale state must disappear before new process starts')
                return SimpleNamespace(pid=123)
            with patch.object(manage,'ROOT',root),patch.object(manage,'owned_pids',return_value=[]),patch.object(manage.subprocess,'Popen',side_effect=spawn):
                self.assertTrue(manage.start('client'))
            self.assertEqual((root/'runtime/client.pid').read_text(),'123')

    def test_exact_client_identity(self):
        root=manage.ROOT
        flag='-Dgamescaling.bridge='+str(root/'runtime/bridge')
        self.assertTrue(manage.matches('client',['/jdk/bin/java',flag],root))
        self.assertFalse(manage.matches('client',['/jdk/bin/java',flag+'-other'],root))
        self.assertFalse(manage.matches('client',['bash','-c','java '+flag],root))

    def test_other_java_and_workspace_processes_are_preserved(self):
        root=manage.ROOT
        self.assertFalse(manage.matches('server',['java','-jar','other.jar'],root/'instances/server'))
        self.assertFalse(manage.matches('server',['java','-jar','lwjgl3ify-forgePatches.jar'],root/'other'))
        self.assertFalse(manage.matches('monitor',['cat',str(root/'src/monitor.py')],root))
        self.assertTrue(manage.matches('monitor',['python3',str(root/'src/monitor.py')],root))

    def test_recycled_pid_cannot_receive_signal(self):
        with patch.object(manage,'inspect',return_value=(['java','-jar','other.jar'],Path('/tmp'))),patch.object(manage.os,'kill') as kill,patch.object(manage.os,'killpg') as killpg:
            manage.signal_owned('client',12345,15)
            kill.assert_not_called();killpg.assert_not_called()

    def test_model_identity_survives_custom_engine_path(self):
        root=manage.ROOT
        args=['/custom/engine','-m',str(root/'models/GameScaling-9B-S1-GGUF/GameScaling-9B-S1.Q4_K_M.compat.gguf'),
              '--mmproj','vision.gguf','--alias','gamescaling','--port','8789']
        self.assertTrue(manage.matches('model',args,root))
        args[2]='/other-project/model.gguf'
        self.assertFalse(manage.matches('model',args,root))

    def test_shutdown_continues_after_one_component_fails(self):
        visited=[]
        def stop(name,force):
            visited.append(name)
            if name=='client':raise RuntimeError('test failure')
        with patch.object(lifecycle,'save_control'),patch.object(manage,'owned',return_value=None),patch.object(manage,'stop',side_effect=stop):
            errors=lifecycle.shutdown()
        self.assertEqual(visited,['monitor','bridge','client','server','model','display'])
        self.assertEqual(errors,['test failure'])

if __name__=='__main__':unittest.main()
