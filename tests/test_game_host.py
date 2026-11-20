"""Exercise actual game processes and the fixed cleanup, without cloud credentials."""
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/'work'/'box-demo'
sys.path.insert(0,str(SOURCE))
from game_agent import GameHost

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]

class GameHostTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        shutil.copyfile(SOURCE/'game_worker.py',self.root/'game_worker.py')
        a=free_port();b=free_port()
        while b==a:b=free_port()
        self.host=GameHost(self.root,'test-worker',{'A':a,'B':b})
    def tearDown(self):
        self.host.cleanup()
        self.tmp.cleanup()
    def test_real_shared_games_advance_then_both_processes_stop(self):
        first=self.host.start('shared','shared-round')
        time.sleep(.2)
        later=self.host.states()
        self.assertEqual(set(first['states']),{'A','B'})
        for label in ('A','B'):
            self.assertGreater(later['states'][label]['tick'],first['states'][label]['tick'])
            self.assertNotEqual(later['states'][label]['x'],first['states'][label]['x'])
        proof=self.host.fault('shared-round','one-fault')
        self.assertEqual(set(proof['killed_pids']),{first['states']['A']['pid'],first['states']['B']['pid']})
        self.assertTrue(all(proof['stopped'].values()))
        self.assertEqual(self.host.states()['states'],{})
        self.assertEqual(self.host.fault('shared-round','one-fault'),proof)
    def test_stale_round_refused_and_other_process_not_touched(self):
        unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
        try:
            self.host.start('isolated','new-round')
            with self.assertRaises(ValueError):self.host.fault('old-round','stale')
            self.assertIn('A',self.host.states()['states'])
            proof=self.host.fault('new-round','current')
            self.assertEqual(set(proof['stopped']),{'A'})
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate();unrelated.wait(timeout=3)

if __name__=='__main__':unittest.main()
