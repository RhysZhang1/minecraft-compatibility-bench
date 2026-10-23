# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import base64,collections,io,json,os,sys,tempfile,time,unittest
from unittest.mock import patch
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor/GameScaling')]
from controller import Observation,Feedback,read_observation,changes,append_history
from gamescaling.action import parse_action,NOOP_ACTION_TEXT

def picture(color):
    f=io.BytesIO();Image.new('RGB',(80,60),color).save(f,'JPEG');return f.getvalue()
def observation(color='black',**game):
    state=dict(session='one',connected=True,screen='',x=0,y=70,z=0,health=20,inventory=[]);state.update(game);return Observation(picture(color),{},state)
class ControllerTests(unittest.TestCase):
    def test_metadata_image_session_and_age_must_all_match(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);frame=p/'frame.jpg';frame.write_bytes(picture('black'))
            now=int(time.time()*1000)
            meta={'captured_at':now,'image_mtime_ms':frame.stat().st_mtime_ns//1000000,'session':'new'}
            state={'timestamp':now,'connected':True,'session':'new'}
            def write():
                (p/'frame-meta.json').write_text(json.dumps(meta));(p/'state.json').write_text(json.dumps(state))
            write();self.assertEqual(read_observation(p,timeout=.02).game['session'],'new')
            for failure in ('old','mismatch','wrong_session','before_action'):
                bad=dict(meta)
                if failure=='old':bad['captured_at']=now-5000
                if failure=='mismatch':bad['image_mtime_ms']-=1
                if failure=='wrong_session':bad['session']='old-client'
                (p/'frame-meta.json').write_text(json.dumps(bad))
                with self.assertRaises(TimeoutError):read_observation(p,after=now+1 if failure=='before_action' else 0,timeout=.02)
            with self.assertRaises(InterruptedError):read_observation(p,cancel=lambda:True)
    def test_recovery_is_bounded_and_counts_noop_as_action_not_progress(self):
        f=Feedback({'stalled_decisions':2,'recovery_attempts':1});a=parse_action(NOOP_ACTION_TEXT);o=observation()
        for i in range(4):r=f.record(o,o,a)
        self.assertEqual(r['phase'],'stalled');self.assertEqual(r['noop_streak'],4);self.assertEqual(r['stagnant_decisions'],4)
        self.assertFalse(r['changes']);self.assertTrue(f.reset_history)
    def test_inventory_change_is_observed_but_not_claimed_goal_completion(self):
        before=observation();after=observation();after.game['inventory']=[{'slot':0,'item':'minecraft:dirt','count':1}]
        f=Feedback({});r=f.record(before,after,parse_action(NOOP_ACTION_TEXT))
        self.assertEqual(r['changes'],['inventory changed']);self.assertEqual(r['phase'],'observing')
        self.assertNotIn('completed',f.last)
    def test_cancelled_action_cannot_advance_or_recover(self):
        f=Feedback({'stalled_decisions':1});r=f.record(observation(),observation('white'),parse_action(NOOP_ACTION_TEXT),False)
        self.assertFalse(r['executed']);self.assertEqual(f.streak,0);self.assertEqual(f.recoveries,0)
    def test_failed_sensor_read_is_unknown_not_inventory_loss(self):
        before=observation(inventory=[{'slot':0,'item':'minecraft:dirt','count':2}]);after=observation(inventory_error='unavailable');after.game.pop('inventory')
        reasons,_=changes(before,after);self.assertNotIn('inventory changed',reasons)
    def test_repeated_two_screen_cycle_has_bounded_recovery(self):
        f=Feedback({'stalled_decisions':2,'recovery_attempts':1});a=parse_action(NOOP_ACTION_TEXT);previous=observation()
        for i in range(12):
            after=observation(screen='InventoryScreen' if i%2 else '');r=f.record(previous,after,a);previous=after
        self.assertTrue(r['screen_cycle_detected']);self.assertEqual(f.phase,'stalled')
    def test_idle_history_coalesces_only_identical_frames_and_actions(self):
        h=collections.deque(maxlen=5);a=parse_action(NOOP_ACTION_TEXT);black=base64.b64encode(picture('black')).decode();white=base64.b64encode(picture('white')).decode()
        append_history(h,black,a);append_history(h,black,a);self.assertEqual(len(h),1)
        append_history(h,white,a);self.assertEqual(len(h),2)
        append_history(h,white,a,False);self.assertEqual(len(h),3)
if __name__=='__main__':unittest.main()
