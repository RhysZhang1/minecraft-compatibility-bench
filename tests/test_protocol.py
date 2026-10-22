"""Protocol compatibility checks; no GPU or game required."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import monitor
from jinja2 import Environment
from unittest.mock import patch

class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.memory_patch=patch.object(monitor.MEMORY,'prompt_context',return_value='persistent notes fixture');self.memory_patch.start()
    def tearDown(self):monitor.HISTORY.clear();self.memory_patch.stop()

    def test_prompt_matches_official_template(self):
        path=ROOT/'models/GameScaling-9B-S1-GGUF/chat_template.jinja'
        if not path.exists():self.skipTest('Run the model metadata download first')
        marker='<__test_media__>'
        action='<|action_start|>0 0 0 ; W ; ; ; ; ; <|action_end|>'
        monitor.HISTORY.append(('old-image',action))
        actual=monitor.make_prompt('new-image',marker)
        messages=[{'role':'system','content':monitor.system_prompt()},
            {'role':'user','content':[{'type':'text','text':'current game screen'}, {'type':'image_url','image_url':{'url':'old-image'}}]},
            {'role':'assistant','content':action},
            {'role':'user','content':[{'type':'text','text':'current game screen'}, {'type':'image_url','image_url':{'url':'new-image'}}]}]
        official=Environment().from_string(path.read_text()).render(messages=messages,add_generation_prompt=True)
        expected=official.replace('<|vision_start|><|image_pad|><|vision_end|>',marker)+'<think>'
        self.assertEqual(actual['prompt_string'],expected)
        self.assertEqual(actual['multimodal_data'],['old-image','new-image'])

    def test_unterminated_generation_does_not_become_action(self):
        partial='<think>\n\n</think>\n\n<|action_start|>0 0 0 ; W ; W ; W ; W ; W ; W'
        self.assertFalse(monitor.parse_action(partial).parsed)
        self.assertTrue(monitor.parse_action(partial+'<|action_end|>').parsed)

    def test_thought_quoted_action_is_not_executed(self):
        raw='<think>format: <|action_start|>0 0 0 ; W ; W ; W ; W ; W ; W<|action_end|>'
        self.assertFalse(monitor.parse_action(raw).parsed)

if __name__=='__main__':unittest.main()
