"""Two real local BoxLite microVMs. HTML/physics run inside Boxes, no cloud calls."""
import argparse,asyncio,fcntl,json,os,secrets,subprocess,time,webbrowser
from pathlib import Path
import boxlite
from demo_session import unpack_code
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'box-demo'
STATE=Path(os.environ.get('BOXLITE_DEMO_STATE_DIR',str(ROOT/'private')))

class LocalDemo:
 def __init__(self,duration=900):
  self.duration=duration;self.boxes=[];self.forwarders=[];self.executions=[];self.stop=asyncio.Event()
  STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
  self.rt=boxlite.Boxlite(boxlite.Options(home_dir=str(STATE/'local-runtime')))
 async def forward(self,box,port):
  tunnel=await box.network.tunnel(('127.0.0.1',port))
  forwarder=await tunnel.forward(boxlite.SocketAddress.tcp(host='127.0.0.1',port=0))
  self.forwarders.append(forwarder)
  address=forwarder.local_addr()
  return 'http://127.0.0.1:'+str(address.port)
 async def start(self):
  for role in ('worker','controller'):
   b=boxlite.SimpleBox(runtime=self.rt,image='docker.io/library/python:3.12-alpine',name='boxlite-local-demo-'+role,
     cpus=1,memory_mib=512,auto_remove=False,reuse_existing=True,entrypoint=['sleep','infinity'],
     network=boxlite.NetworkSpec(outbound=boxlite.OutboundNetworkSpec(mode='enabled',allow_net=[]),inbound=boxlite.InboundNetworkSpec(mode='enabled')))
   await b.start();self.boxes.append(b);print('真实本机 Box 已启动：'+role+' '+b.id,flush=True)
  worker,controller=self.boxes
  agent_host=await self.forward(worker,9100)
  a=await self.forward(worker,9101);shared_b=await self.forward(worker,9102)
  self.origin=await self.forward(controller,8080);isolated_b=await self.forward(controller,9102)
  token=secrets.token_urlsafe(32)
  config={'worker':worker.id,'controller':controller.id,'origin':self.origin,'agent_managed':True,
    'agent_url':agent_host.replace('127.0.0.1','host.boxlite.internal'),'agent_token':token,
    'game_urls':{'a':a,'shared_b':shared_b,'isolated_b':isolated_b},'runtime':'local-boxlite'}
  files={f'/home/boxlite/game-lab/{n}':(SOURCE/n).read_bytes() for n in ('game_worker.py','game_agent.py')}
  r=await worker.exec('python3','-c',unpack_code(files))
  if r.exit_code:raise RuntimeError('本机 Worker 写入程序失败：'+r.stderr[-200:])
  controller_files={}
  for p in SOURCE.rglob('*'):
   if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.html','.css','.js'):
    controller_files['/app/isolation/'+str(p.relative_to(SOURCE))]=p.read_bytes()
  controller_files['/app/server.py']=(ROOT.parent/'box-root/server.py').read_bytes()
  controller_files['/home/boxlite/box-meaning-private/config.json']=json.dumps(config).encode()
  reset='''
import time
archive=Path('/home/boxlite/box-meaning-private/history');archive.mkdir(exist_ok=True)
for source in ('/app/isolation/play/last-session.json','/home/boxlite/box-meaning-private/game-jobs.json'):
 p=Path(source)
 if p.exists():p.rename(archive/(str(time.time_ns())+'-'+p.name))
Path('/home/boxlite/box-meaning-private/config.json').chmod(0o600)
'''
  r=await controller.exec('python3','-c',unpack_code(controller_files)+reset)
  if r.exit_code:raise RuntimeError('本机 Controller 写入程序失败：'+r.stderr[-200:])
  # Long-lived executions stay in these actual VMs, not host subprocesses.
  agent=await worker._box.exec('python3',args=['-u','/home/boxlite/game-lab/game_agent.py','--box-id',worker.id,'--lifetime','900'],env=[('GAME_AGENT_TOKEN',token)])
  server=await controller._box.exec('python3',args=['-u','/app/server.py'])
  self.executions=[agent,server]
  async def discard(stream):
   async for _ in stream:pass
  self.drains=[asyncio.create_task(discard(e.stdout())) for e in self.executions]+[asyncio.create_task(discard(e.stderr())) for e in self.executions]
  for _ in range(30):
   try:
    # Verify B can reach the authenticated worker through the local BoxLite gateway.
    probe="import urllib.request,json;req=urllib.request.Request("+repr(config['agent_url']+'/healthz')+",headers={'X-Game-Agent':"+repr(token)+"});assert json.load(urllib.request.urlopen(req,timeout=2))['box_id']=="+repr(worker.id)
    r=await controller.exec('python3','-c',probe)
    response=await asyncio.to_thread(subprocess.run,['/usr/bin/curl','-fsS','--max-time','2',self.origin+'/healthz'],capture_output=True,text=True)
    if r.exit_code==0 and response.returncode==0:break
   except Exception:pass
   await asyncio.sleep(.2)
  else:raise RuntimeError('本机 Box 间的真实游戏通道没有就绪')
  public={'origin':self.origin,'worker':worker.id,'controller':controller.id,'runtime':'local-boxlite','operator_pid':os.getpid(),'expires_at':time.time()+self.duration}
  (STATE/'local-demo.json').write_text(json.dumps(public,indent=2))
  print('DEMO_READY '+self.origin+'/isolation/play/',flush=True)
  return self.origin+'/isolation/play/'
 async def close(self):
  for f in self.forwarders:
   try:await f.close()
   except Exception:pass
  for b in reversed(self.boxes):
   try:await b.stop()
   except Exception:pass
  for t in getattr(self,'drains',[]):t.cancel()
 async def run(self,open_browser=False):
  try:
   try:url=await asyncio.wait_for(self.start(),120)
   except asyncio.TimeoutError:raise RuntimeError('本机 Box 初始化超时，请重新启动') from None
   if open_browser:webbrowser.open(url)
   print('演示运行在两台本机 Box 内。保持此窗口打开，Ctrl+C 结束。',flush=True)
   try:await asyncio.wait_for(self.stop.wait(),min(self.duration,900))
   except asyncio.TimeoutError:print('本次演示会话已结束，可重新启动。',flush=True)
  finally:await self.close()

async def main():
 p=argparse.ArgumentParser();p.add_argument('--no-open',action='store_true');p.add_argument('--no-key-dialog',action='store_true');a=p.parse_args()
 STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
 lock=(STATE/'session.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  state=json.loads((STATE/'local-demo.json').read_text())
  if not a.no_open:webbrowser.open(state['origin']+'/isolation/play/')
  print('已有本机演示正在运行，已打开原会话。',flush=True);return
 if not a.no_key_dialog:
  from native_key import prompt_local_key
  prompt_local_key(STATE/'credentials.json')
 await LocalDemo().run(open_browser=not a.no_open)
if __name__=='__main__':
 try:asyncio.run(main())
 except KeyboardInterrupt:print('本机演示已停止，云端 Box 未改动。',flush=True)
 except (ValueError,RuntimeError) as error:print(str(error),flush=True);raise SystemExit(1)
