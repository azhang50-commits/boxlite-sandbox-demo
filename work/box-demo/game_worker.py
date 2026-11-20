"""Actual server-side breakout game. Browser only renders state returned by this process."""
import argparse
import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

parser=argparse.ArgumentParser()
parser.add_argument('--port',type=int,required=True)
parser.add_argument('--label',required=True)
parser.add_argument('--box-id',required=True)
parser.add_argument('--round',required=True)
parser.add_argument('--max-seconds',type=int,default=240)
args=parser.parse_args()
LOCK=threading.Lock()
state={'label':args.label,'box_id':args.box_id,'round':args.round,'pid':os.getpid(),
    'tick':0,'score':0,'x':220.0,'y':235.0,'vx':140.0,'vy':-155.0,'paddle':220.0,'bricks':[],'server_time':time.time()}

def reset_bricks():
    state['bricks']=[{'x':25+c*65,'y':50+r*25,'w':56,'h':16,'row':r} for r in range(3) for c in range(6)]

def loop():
    reset_bricks()
    last=time.monotonic()
    deadline=last+max(1,min(args.max_seconds,240))
    while time.monotonic()<deadline:
        now=time.monotonic()
        dt=min(now-last,.05)
        last=now
        with LOCK:
            state['tick']+=1
            state['server_time']=time.time()
            state['x']+=state['vx']*dt
            state['y']+=state['vy']*dt
            if state['x']<10 or state['x']>430:
                state['vx']*=-1
                state['x']=max(10,min(430,state['x']))
            if state['y']<18:
                state['vy']=abs(state['vy'])
            # Autoplay is intentional: the audience can watch both games while triggering a fault.
            state['paddle']+=(state['x']-state['paddle'])*min(1,dt*12)
            if state['y']>291 and state['vy']>0:
                state['vy']=-abs(state['vy'])
                state['y']=291
                state['score']+=1
            for brick in state['bricks']:
                if brick['x']-5<=state['x']<=brick['x']+brick['w']+5 and brick['y']-5<=state['y']<=brick['y']+brick['h']+5:
                    state['bricks'].remove(brick)
                    state['vy']*=-1
                    state['score']+=10
                    break
            if not state['bricks']:
                reset_bricks()
        time.sleep(.025)
    os._exit(0)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/state','/healthz'):
            self.send_error(404)
            return
        with LOCK:
            payload=json.dumps(state).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self,*args):
        pass

threading.Thread(target=loop,daemon=True).start()
ThreadingHTTPServer(('0.0.0.0',args.port),Handler).serve_forever()
