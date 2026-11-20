"""Operator-managed real Cloud demo. API credential stays on the operator computer."""
import argparse,asyncio,base64,json,os,secrets,subprocess,time,zlib
from pathlib import Path
import boxlite
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'box-demo'

class Cloud:
 def __init__(self,key,url='https://api.boxlite.ai'):self.key,self.url=key,url.rstrip('/')
 def call(self,method,path,payload=None):
  cfg='header = '+json.dumps('Authorization: Bearer '+self.key)+'\n'
  args=['/usr/bin/curl','--config','-','-sS','--connect-timeout','8','--max-time','25','-X',method,'-w','\n%{http_code}']
  if payload is not None:cfg+='header = "Content-Type: application/json"\ndata = '+json.dumps(json.dumps(payload))+'\n'
  r=subprocess.run(args+[self.url+path],input=cfg,text=True,capture_output=True)
  if r.returncode:raise RuntimeError('云端连接超时或中断（'+str(r.returncode)+'）')
  body,_,status=r.stdout.rpartition('\n')
  try:value=json.loads(body) if body else {}
  except ValueError:value={}
  if not status.startswith('2'):
   reason=value.get('message',value.get('error',{}))
   if isinstance(reason,dict):reason=reason.get('message','')
   raise RuntimeError('云端 HTTP '+status+': '+str(reason)[:180])
  return value

async def execute(box,code,timeout=30):
 e=await box.exec('python3',args=['-u','-c',code],timeout_secs=timeout,user='root')
 errors=[]
 async def drain(stream):
  async for line in stream:errors.append(str(line))
 results=await asyncio.gather(drain(e.stdout()),drain(e.stderr()),e.wait())
 if results[-1].exit_code!=0:raise RuntimeError('云端部署执行失败：'+str(results[-1].exit_code)+' '+''.join(errors).splitlines()[-1][:180])
 return e.id()

def packed(files):
 return base64.b64encode(zlib.compress(json.dumps({name:base64.b64encode(data).decode() for name,data in files.items()}).encode())).decode()

def unpack_code(files):
 return "import base64,json,zlib;from pathlib import Path\nfor name,data in json.loads(zlib.decompress(base64.b64decode("+repr(packed(files))+"))).items():\n p=Path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(data))\n"

class DemoSession:
 def __init__(self,key,worker,controller,duration=900,notify=print):
  self.cloud=Cloud(key);self.worker_id=worker;self.controller_id=controller
  self.duration=duration;self.notify=notify;self.stop=asyncio.Event();self.tasks=[];self.origin=None
  self.rt=boxlite.Boxlite.rest(boxlite.BoxliteRestOptions(url=self.cloud.url,credential=boxlite.ApiKeyCredential(key)))
 async def start(self):
  self.notify('连接已有云端演示环境…')
  for bid in (self.worker_id,self.controller_id):
   await asyncio.to_thread(self.cloud.call,'POST','/v1/boxes/'+bid+'/start',{})
   await asyncio.to_thread(self.cloud.call,'POST','/box/'+bid+'/last-activity',{})
  worker=await self.rt.get(self.worker_id);controller=await self.rt.get(self.controller_id)
  token=secrets.token_urlsafe(32)
  agent=(await worker.network.tunnel(('127.0.0.1',9100))).uri()
  a=(await worker.network.tunnel(('127.0.0.1',9101))).uri()
  shared_b=(await worker.network.tunnel(('127.0.0.1',9102))).uri()
  self.origin=(await controller.network.tunnel(('127.0.0.1',8080))).uri()
  isolated_b=(await controller.network.tunnel(('127.0.0.1',9102))).uri()
  files={f'/home/boxlite/game-lab/{name}':(SOURCE/name).read_bytes() for name in ('game_worker.py','game_agent.py')}
  code=unpack_code(files)+'''import os,signal,sys
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=p.read_bytes().split(bytes([0]))
  own_script=any(arg in (b'/home/boxlite/game-lab/game_agent.py',b'/home/boxlite/game-lab/game_worker.py') for arg in args[1:3])
  old_bootstrap=len(args)>3 and args[1:3]==[b'-u',b'-c'] and b"serve('/home/boxlite/game-lab'," in args[3]
  if int(p.parent.name)!=os.getpid() and (own_script or old_bootstrap):os.kill(int(p.parent.name),signal.SIGTERM)
 except OSError:pass
sys.path.insert(0,'/home/boxlite/game-lab')
'''+f"os.environ['GAME_AGENT_TOKEN']={token!r}\nos.execv(sys.executable,[sys.executable,'-u','/home/boxlite/game-lab/game_agent.py','--box-id',{self.worker_id!r},'--lifetime',{str(self.duration)!r}])"
  self.worker_execution=await worker.exec('python3',args=['-u','-c',code],timeout_secs=self.duration+20,user='root')
  async def watch_worker():
   async def drain(stream):
    async for _ in stream:pass
   results=await asyncio.gather(drain(self.worker_execution.stdout()),drain(self.worker_execution.stderr()),self.worker_execution.wait())
   return results[-1].exit_code
  self.worker_task=asyncio.create_task(watch_worker());self.tasks.append(self.worker_task)
  config={'worker':self.worker_id,'controller':self.controller_id,'origin':self.origin,
   'game_urls':{'a':a,'shared_b':shared_b,'isolated_b':isolated_b},'agent_url':agent,'agent_token':token,'agent_managed':True}
  self.agent_url,self.agent_token=agent,token
  assert not any(k in config for k in ('key','BOXLITE_API_KEY'))
  controller_files={}
  for p in SOURCE.rglob('*'):
   if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.html','.css','.js'):
    controller_files['/app/isolation/'+str(p.relative_to(SOURCE))]=p.read_bytes()
  controller_files['/app/server.py']=(ROOT.parent/'box-root/server.py').read_bytes()
  controller_files['/home/boxlite/box-meaning-private/config.json']=json.dumps(config).encode()
  code=unpack_code(controller_files)+'''import os,signal
Path('/home/boxlite/box-meaning-private/config.json').chmod(0o600)
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=p.read_bytes().split(bytes([0]))
  if args[:3]==[b'python3',b'-u',b'/app/server.py']:os.kill(int(p.parent.name),signal.SIGTERM)
 except OSError:pass
'''
  self.notify('部署固定游戏服务和真实帧推送…')
  await asyncio.wait_for(execute(controller,code),45)
  self.tasks.append(asyncio.create_task(self.heartbeat()))
  # External readiness, not merely successful file delivery.
  async def ready():
   def probe():
    r=subprocess.run(['/usr/bin/curl','-fsS','--max-time','6',self.origin+'/isolation/api/game/status'],capture_output=True,text=True)
    return not r.returncode and json.loads(r.stdout).get('configured')
   for _ in range(8):
    try:
     if await asyncio.to_thread(probe) and await asyncio.to_thread(self.worker_healthy):return
    except (ValueError,OSError):pass
    await asyncio.sleep(1)
   raise RuntimeError('网页服务尚未就绪')
  await ready();self.notify('DEMO_READY '+self.origin+'/isolation/play/')
  return self.origin+'/isolation/play/'
 async def heartbeat(self):
  while not self.stop.is_set():
   for bid in (self.worker_id,self.controller_id):
    await asyncio.to_thread(self.cloud.call,'POST','/box/'+bid+'/last-activity',{})
   try:await asyncio.wait_for(self.stop.wait(),60)
   except asyncio.TimeoutError:pass
 def worker_healthy(self):
  cfg='header = '+json.dumps('X-Game-Agent: '+self.agent_token)+'\n'
  r=subprocess.run(['/usr/bin/curl','--config','-','-fsS','--max-time','6',self.agent_url+'/healthz'],input=cfg,text=True,capture_output=True)
  return not r.returncode and json.loads(r.stdout).get('box_id')==self.worker_id
 async def health_monitor(self):
  failures=0
  while not self.stop.is_set():
   await asyncio.sleep(10)
   try:healthy=await asyncio.to_thread(self.worker_healthy)
   except (OSError,ValueError):healthy=False
   failures=0 if healthy else failures+1
   if failures>=3:raise RuntimeError('云端游戏连接中断，请重新启动演示')
 async def run(self):
  await self.start()
  self.notify('演示会话运行中；API 密钥只在本机。保持启动器打开。')
  end=asyncio.create_task(self.stop.wait())
  monitor=asyncio.create_task(self.health_monitor());self.tasks.append(monitor)
  done,_=await asyncio.wait([end,*self.tasks[1:]],timeout=self.duration,return_when=asyncio.FIRST_COMPLETED)
  for task in done:
   if task is not end:
    result=task.result()
    if task is self.worker_task and result not in (0,None):raise RuntimeError('演示 Worker 中断：'+str(result))
  self.stop.set();end.cancel()
  for task in self.tasks:
   if not task.done():task.cancel()
  self.notify('演示会话已结束；保留 Box，按原闲置策略停止。')

async def main():
 p=argparse.ArgumentParser();p.add_argument('--worker',required=True);p.add_argument('--controller',required=True);p.add_argument('--seconds',type=int,default=900)
 a=p.parse_args();c=json.loads((ROOT/'credentials.json').read_text())
 session=DemoSession(c['BOXLITE_API_KEY'],a.worker,a.controller,a.seconds)
 await session.run()
if __name__=='__main__':asyncio.run(main())
