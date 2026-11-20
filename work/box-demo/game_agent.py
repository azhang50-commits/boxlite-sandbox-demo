"""Fixed game host inside worker Box A; no arbitrary command/code endpoint."""
import argparse
import hmac
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FAULT_CODE = '''killed = []
for process in games.values():
    if process.poll() is None:
        process.terminate()
        killed.append(process.pid)
for process in games.values():
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
result = {"killed_pids": killed}
'''

class GameHost:
    def __init__(self, root, box_id, ports=None):
        self.root=Path(root)
        self.box_id=box_id
        self.ports=ports or {'A':9101,'B':9102}
        self.games={}
        self.round=None
        self.mode=None
        self.lock=threading.RLock()
        self.faults={}

    def states(self):
        with self.lock:
            result={}
            for label,process in self.games.items():
                if process.poll() is not None:
                    continue
                try:
                    with urllib.request.urlopen('http://127.0.0.1:'+str(self.ports[label])+'/state',timeout=.6) as response:
                        state=json.load(response)
                    if state['round']==self.round and state['pid']==process.pid and state['box_id']==self.box_id:
                        result[label]=state
                except (OSError,ValueError):
                    pass
            return {'round':self.round,'box_id':self.box_id,'states':result}

    def cleanup(self):
        scope={'games':self.games,'subprocess':subprocess}
        exec(FAULT_CODE,scope)
        return scope['result']

    def start(self,mode,round_id):
        if mode not in ('shared','isolated') or not isinstance(round_id,str) or not 1<=len(round_id)<=80:
            raise ValueError('Invalid fixed game scenario')
        with self.lock:
            if self.round==round_id and self.mode==mode:
                return self.states()
            self.cleanup()
            self.games={}
            self.round,self.mode=round_id,mode
            self.root.mkdir(parents=True,exist_ok=True)
            for label in ('A','B') if mode=='shared' else ('A',):
                with (self.root/('game-'+label+'.log')).open('ab') as log:
                    self.games[label]=subprocess.Popen([sys.executable,str(self.root/'game_worker.py'),
                        '--port',str(self.ports[label]),'--label',label,'--box-id',self.box_id,'--round',round_id],
                        stdin=subprocess.DEVNULL,stdout=log,stderr=log,close_fds=True)
            until=time.monotonic()+5
            while time.monotonic()<until:
                value=self.states()
                if len(value['states'])==len(self.games):
                    return value
                time.sleep(.05)
            raise RuntimeError('Game processes did not become ready')

    def fault(self,round_id,request_id):
        with self.lock:
            if request_id in self.faults:
                return self.faults[request_id]
            if round_id!=self.round:
                raise ValueError('The round changed; refusing stale cleanup')
            before=self.states()['states']
            if 'A' not in before or (self.mode=='shared' and 'B' not in before):
                raise ValueError('Game processes are no longer running; restart this round')
            proof={**self.cleanup(),'round':self.round,'box_id':self.box_id,'before':before,
                   'stopped':{label:process.poll() is not None for label,process in self.games.items()}}
            self.faults[request_id]=proof
            if len(self.faults)>100:self.faults.pop(next(iter(self.faults)))
            return proof

def serve(root,box_id,token,port=9100,lifetime=900,ports=None):
    host=GameHost(root,box_id,ports=ports)
    class Handler(BaseHTTPRequestHandler):
        def respond(self,status,value):
            data=json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(data)
        def authorized(self):
            return hmac.compare_digest(self.headers.get('X-Game-Agent',''),token)
        def do_GET(self):
            if not self.authorized():return self.respond(403,{'error':'Forbidden'})
            if self.path=='/healthz':return self.respond(200,{'box_id':box_id,'pid':os.getpid()})
            if self.path=='/states':return self.respond(200,host.states())
            if self.path=='/stream':
                self.send_response(200)
                self.send_header('Content-Type','text/event-stream')
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Accel-Buffering','no')
                self.end_headers()
                end=time.monotonic()+245
                try:
                    while time.monotonic()<end:
                        self.wfile.write(('data: '+json.dumps(host.states())+'\n\n').encode())
                        self.wfile.flush()
                        time.sleep(.1)
                except (BrokenPipeError,ConnectionResetError):pass
                return
            self.respond(404,{'error':'Not found'})
        def do_POST(self):
            if not self.authorized():return self.respond(403,{'error':'Forbidden'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<1024:raise ValueError('Invalid request')
                value=json.loads(self.rfile.read(size))
                if self.path=='/start' and set(value)=={'mode','round'}:
                    return self.respond(200,host.start(value['mode'],value['round']))
                if self.path=='/fault' and set(value)=={'round','request_id'} and isinstance(value['request_id'],str):
                    return self.respond(200,host.fault(value['round'],value['request_id']))
                raise ValueError('Only fixed start/fault operations are supported')
            except (ValueError,TypeError,KeyError) as error:self.respond(409,{'error':str(error)})
            except Exception:self.respond(503,{'error':'Fixed game operation did not complete'})
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('0.0.0.0',port),Handler)
    def expire():
        time.sleep(max(30,min(lifetime,900)))
        with host.lock:host.cleanup()
        server.shutdown()
    threading.Thread(target=expire,daemon=True).start()
    server.serve_forever()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--box-id',required=True)
    parser.add_argument('--root',default='/home/boxlite/game-lab')
    parser.add_argument('--lifetime',type=int,default=900)
    args=parser.parse_args()
    serve(args.root,args.box_id,os.environ['GAME_AGENT_TOKEN'],lifetime=args.lifetime)
