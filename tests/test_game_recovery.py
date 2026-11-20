"""Regressions for uncertain cloud requests, stale tabs and controller restarts."""
import importlib.util
import json
import io
import tarfile
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'work'/'box-demo'))
import backend
import game_backend as game

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.patches=[patch.object(backend,'PRIVATE',self.root/'private'),patch.object(game,'HERE',self.root)]
        for item in self.patches:item.start()
        game.CURRENT=None
        game.GAME_JOBS.clear()

    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()

    def test_stale_tab_cannot_fault_new_round_or_wrong_mode(self):
        game.CURRENT={'id':'new-round','mode':'isolated','state':'running'}
        with patch.object(game,'fault_games') as execute:
            for mode,round_id in [('shared','new-round'),('isolated','old-round'),('isolated',None)]:
                with self.assertRaises(backend.DemoError):game.launch('fault',mode,round_id)
            execute.assert_not_called()
        self.assertFalse(game.GAME_LOCK.locked())

    def test_restart_restores_session_and_marks_interrupted_job_uncertain(self):
        saved={'id':'round','mode':'isolated','state':'running','a':{'pid':10},'b':{'pid':20}}
        game.CURRENT=saved
        game.save_current()
        game.GAME_JOBS['interrupted']={'state':'running','action':'fault'}
        game.save_jobs()
        game.CURRENT=None
        game.GAME_JOBS.clear()
        game.restore()
        self.assertEqual(game.CURRENT,saved)
        self.assertEqual(game.GAME_JOBS['interrupted']['state'],'error')
        self.assertIsNone(game.status()['active_job'])

    def test_duplicate_request_does_not_restart_game_or_charge_quota_twice(self):
        entered=threading.Event(); release=threading.Event()
        def slow_start(mode,notify):
            entered.set();release.wait(2)
            return {'id':'one','mode':mode}
        with patch.object(game,'start_games',side_effect=slow_start) as start:
            try:
                first=game.launch('start','shared',request_id='same-request')
                self.assertTrue(entered.wait(1))
                self.assertEqual(game.launch('start','shared',request_id='same-request'),first)
                self.assertEqual(json.loads((backend.PRIVATE/'game-quota.json').read_text())['count'],1)
                with self.assertRaises(backend.DemoError):game.launch('start','isolated',request_id='same-request')
            finally:
                release.set()
                end=time.monotonic()+2
                while game.GAME_LOCK.locked() and time.monotonic()<end:time.sleep(.01)
            self.assertFalse(game.GAME_LOCK.locked())
            self.assertEqual(start.call_count,1)
            self.assertEqual(game.GAME_JOBS[first]['state'],'done')
            self.assertEqual(game.launch('start','shared',request_id=first),first)

    def test_dns_wait_cannot_hold_caller_beyond_operation_deadline(self):
        release=threading.Event()
        def blocked(*args,**kwargs):
            release.wait(2)
            raise OSError('offline')
        engine=game.GameEngine({'url':'https://invalid.example','key':'test','worker':'A'})
        engine.deadline=time.monotonic()+.05
        try:
            with patch.object(game.urllib.request,'urlopen',side_effect=blocked):
                began=time.monotonic()
                with self.assertRaises(backend.DemoError):engine.api('POST','/test',{})
                self.assertLess(time.monotonic()-began,.5)
        finally:release.set()

    def test_mutating_request_is_never_retried_after_502(self):
        error=urllib.error.HTTPError('https://invalid.example',502,'unavailable',{},None)
        engine=game.GameEngine({'url':'https://invalid.example','key':'test','worker':'A'})
        with patch.object(game.urllib.request,'urlopen',side_effect=error) as request:
            with self.assertRaises(backend.DemoError):engine.api('POST','/test',{})
            self.assertEqual(request.call_count,1)

if __name__=='__main__':unittest.main()
