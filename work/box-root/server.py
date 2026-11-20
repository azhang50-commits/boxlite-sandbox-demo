import json
import sys
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'isolation'))
import backend
import game_backend

class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):
        # Live frame polling must not fill the entrypoint's output channel.
        pass

    def send_json(self,status,value):
        data=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route=urllib.parse.urlparse(self.path)
        if route.path=='/healthz':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
        elif route.path=='/isolation/api/status':
            self.send_json(200,backend.status())
        elif route.path=='/isolation/api/game/status':
            self.send_json(200,game_backend.status())
        elif route.path=='/isolation/api/game/frame':
            query=urllib.parse.parse_qs(route.query)
            try:
                self.send_json(200,game_backend.frame(query.get('which',[''])[0],query.get('round',[''])[0]))
            except backend.DemoError as error:
                self.send_json(503,{'error':str(error)})
        elif route.path=='/isolation/api/game/stream':
            round_id=urllib.parse.parse_qs(route.query).get('round',[''])[0]
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Accel-Buffering','no')
            self.end_headers()
            try:
                for event in game_backend.stream_frames(round_id):
                    self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode())
                    self.wfile.flush()
            except (OSError,ValueError):pass
        elif route.path=='/isolation/api/game/source':
            self.send_json(200,{'fault':game_backend.FAULT_CODE,'game':(ROOT/'isolation'/'game_worker.py').read_text()})
        elif route.path=='/isolation/api/game/job':
            job=game_backend.GAME_JOBS.get(urllib.parse.parse_qs(route.query).get('id',[''])[0])
            self.send_json(200 if job else 404,job or {'error':'本次操作记录不可用，请重新启动演示'})
        elif route.path=='/isolation/api/job':
            job=backend.JOBS.get(urllib.parse.parse_qs(route.query).get('id',[''])[0])
            self.send_json(200 if job else 404,job or {'error':'找不到本次运行，请查看已保存证据'})
        elif route.path.startswith('/isolation/') and route.path.endswith(('.py','.pyc','.tmp')):
            self.send_error(404)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path not in ('/isolation/api/run','/isolation/api/game/start','/isolation/api/game/fault'):
            return self.send_json(404,{'error':'Not found'})
        if self.headers.get('X-Demo-Request')!='1':
            return self.send_json(403,{'error':'Invalid request'})
        origin=self.headers.get('Origin')
        expected=backend.config().get('origin') if backend.status()['configured'] else None
        if origin and origin not in (expected,'http://127.0.0.1:8080','http://localhost:8080'):
            return self.send_json(403,{'error':'Origin not allowed'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<1024:
                return self.send_json(400,{'error':'仅支持固定演示任务'})
            payload=json.loads(self.rfile.read(length))
            if self.path.startswith('/isolation/api/game/'):
                if not isinstance(payload,dict) or 'mode' not in payload or set(payload)-{'mode','session_id','request_id'}:
                    return self.send_json(400,{'error':'仅支持固定游戏演示'})
                job=game_backend.launch(self.path.rsplit('/',1)[1],payload['mode'],payload.get('session_id'),payload.get('request_id'))
                return self.send_json(202,{'job_id':job})
            if payload!={}:
                return self.send_json(400,{'error':'仅支持固定演示任务'})
            job=backend.launch()
            return self.send_json(202,{'job_id':job})
        except backend.DemoError as error:
            return self.send_json(429,{'error':str(error)})
        except (ValueError,TypeError):
            return self.send_json(400,{'error':'Invalid JSON'})
        except Exception:
            return self.send_json(500,{'error':'服务暂时不可用，未启动成功任务'})

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Robots-Tag','noindex, nofollow')
        self.send_header('Cache-Control','no-store')
        super().end_headers()

    def list_directory(self,path):
        self.send_error(404)
        return None

ThreadingHTTPServer(('0.0.0.0',8080),partial(Handler,directory=str(ROOT))).serve_forever()
