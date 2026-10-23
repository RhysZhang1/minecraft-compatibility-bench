# SPDX-License-Identifier: GPL-3.0-or-later
"""Resource budgets, read-only server inspection, world memory and attachment ownership."""
from pathlib import Path
import copy,json,os,sys,tempfile,unittest,zipfile
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import deployment as deploy,deploy_server as wizard,instance_config as ic,manage,lifecycle,prepare_instances

class DeploymentTests(unittest.TestCase):
 def server(self,**updates):
  return {'directory':'/srv/mc','version':'1.20.1','world_name':'world','loader':'vanilla','supported_version':True,'online_mode':False,'warnings':[],
          'max_heap_gib':4,'processes':[],'listening':False,'connection':{'host':'127.0.0.1','port':25565},**updates}
 def host(self,**updates):
  return {'system':'Linux','architecture':'x86_64','available_gib':28,'total_gib':32,'disk_free_gib':100,'cpu_count':8,'wsl':False,
          'desktop_session_present':False,'tools':{},'libraries':{},'kwin_major':6,'gpus':[{'index':0,'free_gib':8,'total_gib':8,'name':'test GPU'}],**updates}
 def test_8gb_gpu_recommends_2b_and_preserves_game_headroom(self):
  r=deploy.recommend(self.host(),self.server());self.assertEqual((r['recommended'],r['profile']),('2b','balanced'));self.assertEqual(r['client_heap_gib'],4)
 def test_large_gpu_can_recommend_9b(self):
  r=deploy.recommend(self.host(available_gib=60,gpus=[{'index':1,'free_gib':23}]),self.server());self.assertEqual((r['recommended'],r['gpu_index']),('9b',1))
 def test_cpu_machine_does_not_recommend_unsupported_gpu_placement(self):
  r=deploy.recommend(self.host(gpus=[]),self.server());self.assertEqual((r['recommended'],r['profile']),('2b','cpu'));self.assertIsNone(r['gpu_index'])
 def test_insufficient_memory_blocks_automatic_deployment(self):
  report=deploy.plan(ROOT,self.server(),self.host(available_gib=8));self.assertIsNone(report['model']['recommended']);self.assertTrue(report['blockers'])
 def test_running_server_reserves_growth_not_its_entire_heap_twice(self):
  r=deploy.recommend(self.host(available_gib=16),self.server(max_heap_gib=6,processes=[{'rss_gib':5}]));self.assertEqual(r['server_reserved_gib'],1);self.assertEqual(r['model_ram_budget_gib'],9)
 def test_online_auth_and_wsl_are_explicit_blockers(self):
  r=deploy.plan(ROOT,self.server(online_mode=True),self.host(wsl=True));self.assertTrue(any('认证' in s for s in r['blockers']));self.assertTrue(any('WSL' in s for s in r['blockers']))
 def test_memory_cgroup_limit_is_applied_to_host_memory(self):
  files={'/proc/meminfo':'MemTotal: 134217728 kB\nMemAvailable: 67108864 kB\n','/proc/self/cgroup':'0::/test\n',
         '/sys/fs/cgroup/test/memory.max':str(8*deploy.GIB),'/sys/fs/cgroup/test/memory.current':str(6*deploy.GIB)}
  def read(path,*a,**kw):
   if str(path) not in files:raise OSError('not present')
   return files[str(path)]
  with patch.object(Path,'read_text',read):self.assertEqual(deploy.memory_info(),{'total_gib':8,'available_gib':2})
 def test_server_inspection_never_exposes_secret_or_executes_scripts(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);props=folder/'server.properties';props.write_text('online-mode=false\nserver-port=25571\nrcon.password=PRIVATE_TEST_SECRET\nlevel-name=world\n');(folder/'world').mkdir()
   marker=folder/'script-executed';(folder/'start.sh').write_text('touch '+str(marker)+'\njava -Xmx6G -jar server.jar\n')
   with zipfile.ZipFile(folder/'server.jar','w') as z:z.writestr('version.json',json.dumps({'id':'1.20.1'}))
   before={str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*') if p.is_file()}
   report=deploy.inspect_server(folder)
   self.assertEqual(report['version'],'1.20.1');self.assertEqual(report['max_heap_gib'],6);self.assertTrue(report['world_exists']);self.assertNotIn('PRIVATE_TEST_SECRET',json.dumps(report));self.assertFalse(marker.exists())
   self.assertEqual(before,{str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*') if p.is_file()})
 def test_conflicting_jar_versions_require_explicit_selection(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d)
   for version in ('1.20.1','1.21.1'):
    with zipfile.ZipFile(folder/(version+'.jar'),'w') as z:z.writestr('version.json',json.dumps({'id':version}))
   self.assertIsNone(deploy.inspect_server(folder)['version'])
   with self.assertRaisesRegex(ValueError,'不一致'):deploy.inspect_server(folder,'26.3')
 def test_modded_server_is_detected_without_guessing_a_vanilla_client(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);(folder/'server.properties').write_text('online-mode=false')
   with zipfile.ZipFile(folder/'server.jar','w') as z:z.writestr('version.json',json.dumps({'id':'1.20.1'}));z.writestr('net/fabricmc/loader/Main.class',b'not executed')
   report=deploy.inspect_server(folder);self.assertEqual(report['loader'],'fabric');self.assertTrue(any('匹配' in w for w in report['warnings']))
 def test_copy_mode_rejects_a_live_world(self):
  report=deploy.plan(ROOT,self.server(processes=[{'rss_gib':1}]),self.host())
  with self.assertRaisesRegex(ValueError,'仍在运行'):wizard.profile_for(report,{'key':'test','model':'2b','mode':'copy','goal':'observe'})
 def test_incomplete_registration_can_reuse_its_memory_identity(self):
  report=deploy.plan(ROOT,self.server(),self.host());choices={'key':'retry-test','model':'2b','goal':'observe'}
  self.assertEqual(wizard.profile_for(report,choices)['world_id'],wizard.profile_for(report,choices)['world_id'])
  other={**choices,'key':'different-test'};self.assertNotEqual(wizard.profile_for(report,choices)['world_id'],wizard.profile_for(report,other)['world_id'])
 def test_server_started_after_registration_cannot_be_copied_live(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'original';source.mkdir();client=root/'client';client.mkdir()
   profile={'deployment_origin':'test','minecraft_version':'1.20.1','client':{'directory':str(client)},'server':{'managed':True,'directory':str(root/'copy')},'bootstrap':{'server_source':str(source)}}
   with patch.object(ic,'config',return_value=profile),patch.object(deploy,'inspect_server',return_value={'processes':[],'listening':True}),patch.object(prepare_instances.shutil,'copytree') as copytree:
    with self.assertRaisesRegex(RuntimeError,'停止原服务器'):prepare_instances.main()
    copytree.assert_not_called()
 def test_registration_preserves_original_files_and_memory_across_retry(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'original-server';source.mkdir();(source/'server.properties').write_text('online-mode=false\ndifficulty=hard\nrcon.password=PRIVATE\n')
   (root/'config').mkdir();(root/'config/agent-prompt.default.md').write_text('Check observations.')
   base=ic.config('vanilla-1-20-1');base['server']['directory']='instances/unrelated';base.pop('key',None)
   (root/'instance-settings.json').write_text(json.dumps({'selected':'base','instances':{'base':base}}))
   report=deploy.plan(root,self.server(directory=str(source)),self.host());choices={'key':'new-server','model':'2b','goal':'Collect materials','notes':'base marker','summary_interval':20}
   before=(source/'server.properties').read_bytes()
   with patch.object(wizard,'ROOT',root),patch.object(ic,'ROOT',root),patch.object(manage,'owned_pids',return_value=[]):
    a=wizard.save_profile(report,choices);b=wizard.save_profile(report,choices)
    self.assertEqual(a['world_id'],b['world_id']);self.assertFalse(a['server']['managed']);self.assertFalse(manage.matches('server',['java','-jar','server.jar'],source))
    memory=wizard.AgentMemory(root,root/a['memory_directory'],a['world_id']);self.assertEqual(memory.config()['notes'],'base marker');self.assertEqual(memory.config()['summary_interval'],20)
   self.assertEqual(before,(source/'server.properties').read_bytes());self.assertEqual(list(source.iterdir()),[source/'server.properties'])
   self.assertFalse((root/'runtime/selected-instance.json').exists())
 def test_instance_cpu_preference_is_used_without_manual_flags(self):
  pref={'key':'2b','profile':'cpu','gpu_layers':0,'vision_gpu':False,'threads':2};args=SimpleNamespace(model=None,profile=None)
  with patch.object(ic,'config',return_value={'model':pref}),patch.object(lifecycle.model_config,'select'),patch.object(lifecycle.model_config,'selected',return_value='2b'),patch.dict(os.environ,{},clear=True):
   lifecycle.apply_model_preference(args);self.assertEqual(args.profile,'cpu');self.assertEqual(os.environ['MODEL_GPU_LAYERS'],'0');self.assertEqual(os.environ['MODEL_VISION_GPU'],'0')
 def test_explicit_gpu_flag_overrides_saved_cpu_placement(self):
  pref={'key':'2b','profile':'cpu','gpu_layers':0,'vision_gpu':False};args=SimpleNamespace(model=None,profile='balanced')
  with patch.object(ic,'config',return_value={'model':pref}),patch.object(lifecycle.model_config,'select'),patch.object(lifecycle.model_config,'selected',return_value='2b'),patch.dict(os.environ,{},clear=True):
   lifecycle.apply_model_preference(args);self.assertNotIn('MODEL_GPU_LAYERS',os.environ);self.assertNotIn('MODEL_VISION_GPU',os.environ)
 def test_readme_is_generic_and_license_preserves_third_party(self):
  readme=(ROOT/'README.md').read_text();self.assertNotIn('GTNH',readme.upper());self.assertNotIn('以后上传',readme);self.assertIn('没有登录桌面会话',readme)
  self.assertIn('GNU GENERAL PUBLIC LICENSE',(ROOT/'LICENSE').read_text());self.assertIn('Apache License',(ROOT/'vendor/GameScaling/LICENSE').read_text());self.assertIn('GPL-3.0-or-later',(ROOT/'LICENSING.md').read_text())

if __name__=='__main__':unittest.main()
