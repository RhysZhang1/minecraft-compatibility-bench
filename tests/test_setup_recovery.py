"""Failure/retry checks for installation, conversion and complete shutdown."""
from pathlib import Path
import json,os,subprocess,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import install_java,vanilla_servers as servers,prepare_2b,lifecycle,manage

class RecoveryTests(unittest.TestCase):
 def test_restored_standalone_wrappers_target_the_new_project_with_spaces(self):
  with tempfile.TemporaryDirectory(prefix='mc restored ') as d:
   root=Path(d)
   with patch.object(servers,'ROOT',root):servers.write_wrappers(root,'1.7.10')
   import shlex
   command=(root/'start.sh').read_text().splitlines()[-1]
   self.assertEqual(shlex.split(command),['exec','python3',str(root/'scripts/vanilla_servers.py'),'start','1.7.10'])

 def test_java_binary_alone_does_not_mark_an_interrupted_install_complete(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);target=root/'instances/java/21';(target/'bin').mkdir(parents=True);(target/'bin/java').write_text('already downloaded')
   manifest={'files':{'bin/java':{'type':'file','downloads':{'raw':{'url':'java','sha1':'hash'}},'executable':True},'lib/modules':{'type':'file','downloads':{'raw':{'url':'modules','sha1':'hash'}}}}}
   def download(url,path,sha):path.write_text(json.dumps(manifest) if url=='manifest' else 'downloaded '+url)
   entries={'linux':{'java-runtime-delta':[{'manifest':{'url':'manifest','sha1':'hash'}}]}}
   with patch.object(install_java,'ROOT',root),patch.object(install_java,'fetch_json',return_value=entries),patch.object(install_java,'download',side_effect=download):install_java.install(21)
   self.assertTrue((target/'lib/modules').is_file());self.assertTrue((target/'download-provenance.json').is_file())

 def test_invalid_eula_leaves_no_half_created_server(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);eula=base/'eula.txt';eula.write_text('eula=false')
   with self.assertRaisesRegex(ValueError,'EULA'):servers.create('1.7.10',base/'servers',eula_source=eula)
   self.assertFalse((base/'servers').exists())

 def test_interrupted_server_download_can_resume_without_publishing_a_partial_server(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);client=root/'instances/vanilla-1.7.10-client';client.mkdir(parents=True)
   (client/'1.7.10.json').write_text(json.dumps({'downloads':{'server':{'url':'official','sha1':'hash'}}}))
   base=root/'servers';registry=root/'registry.json'
   with patch.object(servers,'ROOT',root),patch.object(servers,'REGISTRY',registry):
    with patch.object(servers,'download',side_effect=OSError('connection interrupted')):
     with self.assertRaises(OSError):servers.create('1.7.10',base,java='/java8/bin/java')
    self.assertFalse((base/'vanilla-1.7.10').exists());self.assertFalse(registry.exists())
    with patch.object(servers,'download',side_effect=lambda url,path,sha:path.write_bytes(b'complete official server')):servers.create('1.7.10',base,java='/java8/bin/java')
    item=servers.registry()['1.7.10'];self.assertEqual(item['java'],'/java8/bin/java');self.assertTrue((Path(item['directory'])/'server.jar').is_file())

 def test_failed_conversion_never_becomes_a_reusable_final_gguf(self):
  with tempfile.TemporaryDirectory() as d:
   target=Path(d)/'model.gguf'
   def failed(args,**kw):Path(args[-1]).write_bytes(b'GGUFpartial');raise subprocess.CalledProcessError(1,args)
   with patch.object(prepare_2b.subprocess,'run',side_effect=failed):
    with self.assertRaises(subprocess.CalledProcessError):prepare_2b.convert_atomic(target,['converter',str(target)])
   self.assertFalse(target.exists())
   with patch.object(prepare_2b.subprocess,'run',side_effect=lambda args,**kw:Path(args[-1]).write_bytes(b'GGUFcomplete')):prepare_2b.convert_atomic(target,['converter',str(target)])
   self.assertEqual(target.read_bytes(),b'GGUFcomplete');self.assertEqual(list(Path(d).glob('*.partial.gguf')),[])

 def test_stop_still_reclaims_processes_when_control_file_cannot_be_written(self):
  visited=[]
  with patch.object(lifecycle,'save_control',side_effect=OSError('read only control file')),patch.object(manage,'owned',return_value=None),patch.object(manage,'stop',side_effect=lambda name,force:visited.append(name)),patch.object(servers,'stop_all'):
   self.assertEqual(lifecycle.shutdown(),[])
  self.assertEqual(visited,['monitor','bridge','client','server','model','display'])

 def test_standalone_server_is_found_without_a_pid_file(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);pid=os.getpid()
   with patch.object(manage,'inspect',side_effect=lambda candidate: (['java','-jar','server.jar'],folder) if candidate==pid else None):self.assertEqual(servers.owned({'directory':str(folder)}),pid)

 def test_one_standalone_stop_error_does_not_skip_other_worlds(self):
  visited=[]
  def stop(key,force):
   visited.append(key)
   if key=='a':raise RuntimeError('still saving')
  with patch.object(servers,'registry',return_value={'a':{},'b':{}}),patch.object(servers,'stop',side_effect=stop):
   with self.assertRaisesRegex(RuntimeError,'still saving'):servers.stop_all()
  self.assertEqual(visited,['a','b'])

if __name__=='__main__':unittest.main()
