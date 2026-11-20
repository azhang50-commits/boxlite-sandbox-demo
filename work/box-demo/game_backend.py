"""Fixed demo operations only. No arbitrary code or process names are accepted from the browser."""
import base64
import json
import os
import queue
import copy
import urllib.error
import signal
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path
import backend
import game_agent

HERE=Path(__file__).resolve().parent
GAME_ROOT=Path('/home/boxlite/game-lab')
GAME_SCRIPT=str(GAME_ROOT/'game_worker.py')
GAME_JOBS={}
GAME_LOCK=threading.Lock()
CURRENT=None

# This exact fixed cleanup program runs inside the worker Box's game host.
FAULT_CODE=game_agent.FAULT_CODE
SERVICE_INSTANCE=uuid.uuid4().hex
FRAME_CACHE={}
FRAME_LOCK=threading.Lock()

def agent_request(config,path,payload=None,timeout=5):
    result=queue.Queue(maxsize=1)
    req=urllib.request.Request(config['agent_url'].rstrip('/')+path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'X-Game-Agent':config['agent_token'],'Content-Type':'application/json'},
        method='POST' if payload is not None else 'GET')
    def fetch():
        try:
            with urllib.request.urlopen(req,timeout=timeout) as response:
                result.put((json.load(response),None))
        except urllib.error.HTTPError as error:
            result.put((None,'游戏控制服务返回 HTTP '+str(error.code)))
        except Exception:
            result.put((None,'游戏控制服务暂时未连接，请重新启动演示'))
    threading.Thread(target=fetch,daemon=True).start()
    try:
        value,error=result.get(timeout=timeout)
    except queue.Empty:
        raise backend.DemoError('读取 Box 内游戏状态超时，请重新启动演示') from None
    if error:raise backend.DemoError(error)
    return value

class GameEngine(backend.Engine):
    def __init__(self,config):
        super().__init__(config)
        self.deadline=time.monotonic()+65
    def api(self,method,path,data=None,raw=False):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:
            raise backend.DemoError('本次操作超过 65 秒，已停止等待。请重新启动演示。')
        req=urllib.request.Request(self.config['url'].rstrip('/')+path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization':'Bearer '+self.config['key'],'Content-Type':'application/json'},method=method)
        # DNS resolution may outlive urllib's socket timeout. Bound the caller too.
        # Never retry POST: a lost response can still mean the operation was accepted.
        until=min(self.deadline,time.monotonic()+(30 if path.endswith('/start') else 20))
        for attempt in range(3 if method=='GET' else 1):
            result=queue.Queue(maxsize=1)
            def fetch(result=result,req=req,until=until):
                try:
                    with urllib.request.urlopen(req,timeout=max(.1,until-time.monotonic())) as response:
                        result.put((response.read(),None))
                except Exception as error:
                    result.put((None,error))
            threading.Thread(target=fetch,daemon=True).start()
            try:
                payload,error=result.get(timeout=max(.001,until-time.monotonic()))
            except queue.Empty:
                raise backend.DemoError('BoxLite 连接超过等待期限；操作结果尚未确认，请查看状态后重新启动。') from None
            if error is None:
                return payload if raw else json.loads(payload) if payload else {}
            if (method=='GET' and isinstance(error,urllib.error.HTTPError)
                    and error.code in (502,503,504) and attempt<2 and time.monotonic()+.3<until):
                time.sleep(.3)
                continue
            raise backend.DemoError('BoxLite 连接未完成；未生成成功结果，请重新启动演示。') from None

    def ensure_agent(self,notify):
        if self.config.get('agent_managed'):
            notify('唤醒 Box A，等待固定游戏服务就绪')
            while time.monotonic()<self.deadline-5:
                try:
                    health=agent_request(self.config,'/healthz',timeout=4)
                    if health['box_id']==self.config['worker']:return
                except backend.DemoError:
                    time.sleep(.4)
            raise backend.DemoError('Box A 尚未完成唤醒，请重新启动演示')
        try:
            health=agent_request(self.config,'/healthz',timeout=3)
            if health['box_id']==self.config['worker']:return
        except backend.DemoError:
            pass
        notify('唤醒 Box A 的固定游戏服务')
        self.ensure_running()
        source={name:base64.b64encode((HERE/name).read_bytes()).decode()
                for name in ('game_worker.py','game_agent.py')}
        code="""import os,base64,sys
from pathlib import Path
root=Path('/home/boxlite/game-lab')
root.mkdir(parents=True,exist_ok=True)
for name,data in %r.items():
    (root/name).write_bytes(base64.b64decode(data))
os.environ['GAME_AGENT_TOKEN']=%r
sys.argv=[str(root/'game_agent.py'),'--box-id',%r]
exec(compile((root/'game_agent.py').read_text(),str(root/'game_agent.py'),'exec'),{'__name__':'__main__'})
""" % (source,self.config['agent_token'],self.config['worker'])
        self.api('POST','/v1/boxes/'+self.config['worker']+'/exec',
                 {'command':'python3','args':['-c',code],'user':'root'})
        while time.monotonic()<self.deadline-3:
            try:
                health=agent_request(self.config,'/healthz',timeout=3)
                if health['box_id']==self.config['worker']:return
            except backend.DemoError:
                time.sleep(.4)
        raise backend.DemoError('Box A 的游戏服务尚未就绪，请重新启动演示')

def kill_local_games():
    killed=[]
    for entry in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args=entry.read_bytes().split(bytes([0]))
            if len(args)>1 and args[1].decode(errors='ignore')==GAME_SCRIPT:
                pid=int(entry.parent.name)
                os.kill(pid,signal.SIGTERM)
                killed.append(pid)
        except (OSError,ValueError):
            pass
    return killed

def wait_local(port):
    for i in range(25):
        try:
            with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/state',timeout=.25) as response:
                return json.load(response)
        except Exception:
            time.sleep(.1)
    raise backend.DemoError('B 的游戏没有启动成功')

def start_games(mode,notify):
    global CURRENT
    c=backend.config()
    if not c.get('agent_url') or not c.get('agent_token'):
        raise backend.DemoError('游戏控制服务尚未配置')
    engine=GameEngine(c)
    engine.ensure_agent(notify)
    round_id=uuid.uuid4().hex[:12]
    notify('在同一 Box 内启动 A、B' if mode=='shared' else '分别在两个 Box 内启动游戏')
    remote=agent_request(c,'/start',{'mode':mode,'round':round_id},timeout=12)
    kill_local_games()
    if mode=='isolated':
        GAME_ROOT.mkdir(parents=True,exist_ok=True)
        (GAME_ROOT/'game_worker.py').write_bytes((HERE/'game_worker.py').read_bytes())
        with (GAME_ROOT/'game-B.log').open('ab') as log:
            subprocess.Popen([os.sys.executable,GAME_SCRIPT,'--port','9102','--label','B',
                '--box-id',c['controller'],'--round',round_id],stdin=subprocess.DEVNULL,
                stdout=log,stderr=log,start_new_session=True,close_fds=True)
        b=wait_local(9102)
    else:
        b=remote['states']['B']
    a=remote['states']['A']
    CURRENT={'id':round_id,'mode':mode,'state':'running','started_at':time.time(),
        'a':{'box_id':c['worker'],'url':c['game_urls']['a'],'pid':a['pid']},
        'b':{'box_id':c['worker'] if mode=='shared' else c['controller'],
             'url':c['game_urls']['shared_b'] if mode=='shared' else c['game_urls']['isolated_b'],'pid':b['pid']},
        'start_ticks':{'a':a['tick'],'b':b['tick']},'max_game_seconds':240,
        'transport':'fixed in-Box game service; same-origin frame relay'}
    FRAME_CACHE.clear()
    save_current()
    return CURRENT

def fault_games(notify):
    global CURRENT
    if not CURRENT or CURRENT['state']!='running':
        raise backend.DemoError('请先启动两局游戏')
    c=backend.config()
    notify('在 A 所在 Box 内执行同一段错误清理代码')
    result=agent_request(c,'/fault',{'round':CURRENT['id'],'request_id':'fault-'+CURRENT['id']},timeout=10)
    if CURRENT['a']['pid'] not in result['killed_pids'] or not result['stopped'].get('A'):
        raise backend.DemoError('未验证 A 的真实停止状态，请重新启动')
    if CURRENT['mode']=='shared':
        if CURRENT['b']['pid'] not in result['killed_pids'] or not result['stopped'].get('B'):
            raise backend.DemoError('未验证共享游戏 B 的停止状态')
        proof={'b_stopped':True,'verified':True}
    else:
        before=wait_local(9102)
        time.sleep(.4)
        after=wait_local(9102)
        proof={'b_stopped':False,'b_tick_before':before['tick'],'b_tick_after':after['tick'],
            'verified':after['tick']>before['tick'] and before['round']==after['round']==CURRENT['id']
                and before['pid']==after['pid']==CURRENT['b']['pid']}
        if not proof['verified']:raise backend.DemoError('未验证独立游戏 B 的继续运行状态')
    CURRENT.update(state='faulted',fault={'killed_pids':result['killed_pids'],
        'before':result['before'],'agent_box_id':result['box_id'],**proof},faulted_at=time.time())
    FRAME_CACHE.clear()
    save_current()
    return CURRENT

def frame(which,round_id):
    current=CURRENT
    if which not in ('A','B') or not current or current['id']!=round_id:
        raise backend.DemoError('游戏轮次已改变，请重新启动')
    if current['state']=='faulted' and (which=='A' or current['fault']['b_stopped']):
        raise backend.DemoError('此游戏进程已经停止')
    c=backend.config()
    if which=='B' and current['mode']=='isolated':
        try:
            with urllib.request.urlopen('http://127.0.0.1:9102/state',timeout=.6) as response:
                value=json.load(response)
        except (OSError,ValueError):raise backend.DemoError('等待独立 Box B 的新帧') from None
    else:
        with FRAME_LOCK:
            cached=FRAME_CACHE.get('worker')
            if not cached or cached['round']!=round_id or time.monotonic()-cached['at']>.15:
                states=agent_request(c,'/states',timeout=4)
                cached={'round':round_id,'at':time.monotonic(),'states':states['states']}
                FRAME_CACHE['worker']=cached
            value=cached['states'].get(which)
    spec=current[which.lower()]
    if not value or value['round']!=round_id or value['pid']!=spec['pid'] or value['box_id']!=spec['box_id']:
        raise backend.DemoError('尚未收到本轮游戏的真实状态')
    return value

def stream_frames(round_id):
    """One authenticated worker stream per viewer; no per-frame Cloud requests."""
    c=backend.config()
    request=urllib.request.Request(c['agent_url'].rstrip('/')+'/stream',
        headers={'X-Game-Agent':c['agent_token']})
    with urllib.request.urlopen(request,timeout=12) as response:
        for line in response:
            current=CURRENT
            if not current or current['id']!=round_id:return
            if not line.startswith(b'data: '):continue
            remote=json.loads(line[6:])
            states=remote['states'] if remote.get('round')==round_id else {}
            if current['mode']=='isolated':
                try:
                    with urllib.request.urlopen('http://127.0.0.1:9102/state',timeout=.5) as local:
                        states['B']=json.load(local)
                except (OSError,ValueError):pass
            valid={}
            for label,state in states.items():
                spec=current[label.lower()]
                if (state.get('round'),state.get('pid'),state.get('box_id'))==(round_id,spec['pid'],spec['box_id']):
                    if current['state']!='faulted' or (label=='B' and not current['fault']['b_stopped']):
                        valid[label]=state
            yield {'round':round_id,'states':valid}

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False))
    temporary.replace(path)

def save_current():
    atomic_json(HERE/'play'/'last-session.json',CURRENT)

def save_jobs():
    atomic_json(backend.PRIVATE/'game-jobs.json',GAME_JOBS)

def restore():
    global CURRENT
    try:
        saved=json.loads((HERE/'play'/'last-session.json').read_text())
        if saved and saved.get('mode') in ('shared','isolated') and all(k in saved for k in ('id','a','b','state')):
            CURRENT=saved
    except (OSError,ValueError,TypeError):
        pass
    try:
        GAME_JOBS.update(json.loads((backend.PRIVATE/'game-jobs.json').read_text()))
        for job in GAME_JOBS.values():
            if job['state']=='running':
                job.update(state='error',message='控制服务曾重启，操作结果尚未确认。请重新启动演示。')
    except (OSError,ValueError,TypeError):
        pass

restore()

def status():
    active=next(({'job_id':key,**value} for key,value in list(GAME_JOBS.items()) if value['state']=='running'),None)
    try:
        configured=bool(backend.config().get('agent_url'))
    except (OSError,ValueError):
        configured=False
    return {'configured':configured,'session':CURRENT,'active_job':active,'service_instance':SERVICE_INSTANCE,
            'runtime':backend.config().get('runtime','cloud-boxlite') if configured else None}

def launch(action,mode,session_id=None,request_id=None):
    global CURRENT
    if action not in ('start','fault') or mode not in ('shared','isolated'):
        raise backend.DemoError('不支持的演示操作')
    if request_id is not None and (not isinstance(request_id,str) or not 1<=len(request_id)<=80):
        raise backend.DemoError('无效的操作标识')
    if not GAME_LOCK.acquire(blocking=False):
        if request_id in GAME_JOBS:
            old=GAME_JOBS[request_id]
            if (old.get('action'),old.get('mode'),old.get('session_id'))==(action,mode,session_id):
                return request_id
        raise backend.DemoError('上一操作正在执行，请稍等')
    try:
        if request_id in GAME_JOBS:
            old=GAME_JOBS[request_id]
            if (old.get('action'),old.get('mode'),old.get('session_id'))!=(action,mode,session_id):
                raise backend.DemoError('操作标识已被使用，请刷新页面')
            GAME_LOCK.release()
            return request_id
        if action=='fault' and (not CURRENT or CURRENT['state']!='running'
                or CURRENT['mode']!=mode or CURRENT['id']!=session_id):
            raise backend.DemoError('游戏场景已改变，请刷新页面并重新启动，避免影响另一轮演示')
        quota_path=backend.PRIVATE/'game-quota.json'
        day=time.strftime('%Y-%m-%d',time.gmtime())
        quota=json.loads(quota_path.read_text()) if quota_path.exists() else {}
        if quota.get('day')!=day:
            quota={'day':day,'count':0}
        if quota['count']>=100:
            raise backend.DemoError('今日演示操作次数已达上限')
        quota['count']+=1
        atomic_json(quota_path,quota)
        if len(GAME_JOBS)>=100:
            GAME_JOBS.pop(next(iter(GAME_JOBS)))
        job=request_id or uuid.uuid4().hex
        GAME_JOBS[job]={'state':'running','action':action,'mode':mode,'session_id':session_id,
            'message':'正在准备游戏环境','updated_at':time.time()}
        save_jobs()
        if action=='start':
            CURRENT=None
            save_current()
        def run():
            try:
                def notify(message):
                    GAME_JOBS[job].update(message=message,updated_at=time.time())
                session=start_games(mode,notify) if action=='start' else fault_games(notify)
                GAME_JOBS[job].update(state='done',session=copy.deepcopy(session))
            except Exception as error:
                if CURRENT:
                    CURRENT['state']='unconfirmed'
                    save_current()
                message=str(error) if isinstance(error,backend.DemoError) else '本次游戏操作未完成，请重新启动演示'
                GAME_JOBS[job].update(state='error',message=message)
            finally:
                try:
                    save_jobs()
                finally:
                    GAME_LOCK.release()
        threading.Thread(target=run,daemon=True).start()
        return job
    except Exception:
        GAME_LOCK.release()
        raise
