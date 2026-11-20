"""Verify the public game-host boundary rejects unauthenticated or arbitrary code requests."""
import json
import socket
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/'work'/'box-demo'

class AgentHttpTests(unittest.TestCase):
    def test_one_authenticated_stream_carries_live_frames_and_stopped_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(SOURCE/'game_worker.py',Path(tmp)/'game_worker.py')
            sockets=[socket.socket() for _ in range(3)]
            for sock in sockets:sock.bind(('127.0.0.1',0))
            port,a,b=[sock.getsockname()[1] for sock in sockets]
            for sock in sockets:sock.close()
            code="import sys;sys.path.insert(0,sys.argv[1]);from game_agent import serve;serve(sys.argv[2],'stream-box','test-token',port=int(sys.argv[3]),lifetime=30,ports={'A':int(sys.argv[4]),'B':int(sys.argv[5])})"
            process=subprocess.Popen([sys.executable,'-c',code,str(SOURCE),tmp,str(port),str(a),str(b)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            origin='http://127.0.0.1:'+str(port)
            def request(path,payload=None):
                return urllib.request.urlopen(urllib.request.Request(origin+path,
                    data=json.dumps(payload).encode() if payload else None,
                    headers={'X-Game-Agent':'test-token','Content-Type':'application/json'}),timeout=2)
            try:
                until=time.monotonic()+5
                while True:
                    try:
                        with request('/healthz'):break
                    except OSError:
                        if time.monotonic()>until:raise
                        time.sleep(.05)
                with request('/start',{'mode':'shared','round':'stream-round'}) as response:
                    started=json.load(response)
                def event(stream):
                    while True:
                        line=stream.readline()
                        if not line:raise AssertionError('Stream unexpectedly ended')
                        if line.startswith(b'data: '):return json.loads(line[6:])
                with request('/stream') as stream:
                    first=event(stream);second=event(stream)
                    for label in ('A','B'):
                        self.assertGreater(second['states'][label]['tick'],first['states'][label]['tick'])
                        self.assertEqual(second['states'][label]['pid'],started['states'][label]['pid'])
                    with request('/fault',{'round':'stream-round','request_id':'stop-stream'}) as response:
                        self.assertTrue(all(json.load(response)['stopped'].values()))
                    for _ in range(15):
                        stopped=event(stream)
                        if not stopped['states']:break
                    self.assertEqual(stopped['states'],{})
            finally:
                process.terminate();process.wait(timeout=3)

    def test_authenticated_fixed_operations_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            code="import sys;sys.path.insert(0,sys.argv[1]);from game_agent import serve;serve(sys.argv[2],'test-box','test-only-token',port=int(sys.argv[3]),lifetime=30)"
            process=subprocess.Popen([sys.executable,'-c',code,str(SOURCE),tmp,str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                origin='http://127.0.0.1:'+str(port)
                until=time.monotonic()+5
                while True:
                    try:
                        request=urllib.request.Request(origin+'/healthz',headers={'X-Game-Agent':'test-only-token'})
                        with urllib.request.urlopen(request,timeout=.5) as response:
                            self.assertEqual(json.load(response)['box_id'],'test-box')
                        break
                    except OSError:
                        if time.monotonic()>=until:raise
                        time.sleep(.05)
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(origin+'/states',timeout=.5)
                self.assertEqual(denied.exception.code,403)
                denied.exception.close()
                request=urllib.request.Request(origin+'/run',data=json.dumps({'code':'arbitrary code is forbidden'}).encode(),
                    headers={'X-Game-Agent':'test-only-token','Content-Type':'application/json'},method='POST')
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(request,timeout=.5)
                self.assertEqual(denied.exception.code,409)
                denied.exception.close()
            finally:
                process.terminate();process.wait(timeout=3)

if __name__=='__main__':unittest.main()
