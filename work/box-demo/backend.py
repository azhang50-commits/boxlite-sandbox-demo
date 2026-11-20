import hashlib
import contextlib
import io
import json
import os
import runpy
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime,timezone
from pathlib import Path
from experiment import SCRIPT_HASH,SYNTHETIC_VALUE,worker_script,B_TASK_CODE

HERE=Path(__file__).resolve().parent
PRIVATE=Path(os.environ.get('BOX_DEMO_PRIVATE','/home/boxlite/box-meaning-private'))
JOBS={}
LOCK=threading.Lock()

class DemoError(Exception):
    pass

class Engine:
    def __init__(self, config, transport=None):
        self.config=config
        self.transport=transport
        self.deadline=time.monotonic()+65

    def api(self, method,path,data=None,raw=False):
        if self.transport:
            return self.transport(method,path,data,raw)
        remaining=self.deadline-time.monotonic()
        if remaining<=0:
            raise DemoError('本次操作已超过 65 秒，请重试；未生成成功结果')
        req=urllib.request.Request(self.config['url'].rstrip('/')+path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization':'Bearer '+self.config['key'],'Content-Type':'application/json'},method=method)
        try:
            with urllib.request.urlopen(req,timeout=min(8,remaining)) as response:
                payload=response.read()
        except urllib.error.HTTPError as error:
            raise DemoError('BoxLite API 返回 HTTP '+str(error.code)) from None
        except (urllib.error.URLError,TimeoutError):
            raise DemoError('BoxLite API 连接暂时失败，请稍后重新运行') from None
        return payload if raw else json.loads(payload) if payload else {}

    def ensure_running(self):
        box=self.api('GET','/v1/boxes/'+self.config['worker'])
        if box.get('status') in ('stopped','configured','created'):
            self.api('POST','/v1/boxes/'+self.config['worker']+'/start',{})

    def run_worker(self, base, shared, phase):
        output=base+'/result.json'
        result=self.execute_json(worker_script(base,shared,output),output)
        result['phase']=phase
        if result.get('script_sha256')!=SCRIPT_HASH:
            raise DemoError('脚本指纹不一致')
        return result

    def execute_json(self,code,output):
        execution=self.api('POST','/v1/boxes/'+self.config['worker']+'/exec',
            {'command':'python3','args':['-c',code],'user':'root','timeout_secs':30})
        eid=execution['execution_id']
        until=time.monotonic()+18
        while time.monotonic()<until:
            state=self.api('GET','/v1/boxes/'+self.config['worker']+'/executions/'+eid)
            if state.get('status')=='completed':
                if state.get('exit_code')!=0:
                    raise DemoError('实验脚本执行失败，退出码 '+str(state.get('exit_code')))
                break
            time.sleep(.5)
        else:
            raise DemoError('实验执行超时，未生成通过结果')
        archive=self.api('GET','/v1/boxes/'+self.config['worker']+'/files?'+urllib.parse.urlencode({'path':output}),raw=True)
        with tarfile.open(fileobj=io.BytesIO(archive),mode='r:*') as files:
            member=next((m for m in files.getmembers() if m.isfile() and m.name.endswith(Path(output).name)),None)
            if member is None:
                raise DemoError('结果文件未返回')
            result=json.load(files.extractfile(member))
        result.update({'box_id':self.config['worker'],'execution_id':eid})
        return result

    def run(self, notify=lambda *args:None):
        run_id=uuid.uuid4().hex[:12]
        root='/home/boxlite/isolation-lab/'+run_id
        notify('starting','启动独立执行环境')
        self.ensure_running()
        notify('shared','实测：两个任务使用同一个文件系统')
        shared=self.run_worker(root+'/shared',True,'shared')
        notify('isolated','实测：将客户 B 的文件放入另一台 microVM')
        # This code runs in the trusted controller Box, outside the worker microVM.
        private=Path(root+'/isolated/customer-b/private.txt')
        private.parent.mkdir(parents=True,exist_ok=True)
        private.write_text(SYNTHETIC_VALUE)
        b_task=private.with_name('task_b.py')
        b_task.write_text(B_TASK_CODE)
        before=hashlib.sha256(private.read_bytes()).hexdigest()
        isolated=self.run_worker(root+'/isolated',False,'isolated')
        after=hashlib.sha256(private.read_bytes()).hexdigest() if private.exists() else None
        with contextlib.redirect_stdout(io.StringIO()):
            b_result=runpy.run_path(str(b_task))['result']
        manager_kernel=hashlib.sha256(Path('/proc/sys/kernel/random/boot_id').read_bytes()).hexdigest()[:12]
        isolated.update({'b_box_id':self.config['controller'],'b_file_exists_after':private.exists(),
            'b_file_unchanged':before==after,'b_kernel_fingerprint':manager_kernel,
            'b_base_path':str(private.parent),'b_task':b_result,'b_files':[{'path':'task_b.py','content':b_task.read_text()},{'path':'private.txt','content':private.read_text()}]})
        valid=(shared.get('leads')==70 and isolated.get('leads')==70 and shared['cross_read']['succeeded']
            and shared['cross_delete']['succeeded'] and not isolated['cross_read']['succeeded']
            and not isolated['cross_delete']['succeeded'] and isolated['b_file_unchanged'])
        return {'run_id':run_id,'checked_at':datetime.now(timezone.utc).isoformat(),'verified':valid,
            'live':True,'script_sha256':SCRIPT_HASH,'shared':shared,'isolated':isolated,
            'scope':'Synthetic filesystem read/delete experiment, not a complete security audit. Shared baseline intentionally has no per-task filesystem access control.'}

def config():
    return json.loads((PRIVATE/'config.json').read_text())

def status():
    return {'configured':(PRIVATE/'config.json').is_file(),'model_configured':bool(os.environ.get('MODEL_API_KEY')),
        'model_interface':'OpenAI-compatible chat completions','script_sha256':SCRIPT_HASH}

def launch():
    if not (PRIVATE/'config.json').is_file():
        raise DemoError('运行环境尚未配置')
    if not LOCK.acquire(blocking=False):
        raise DemoError('已有实验正在运行，请等待完成')
    try:
        quota_file=PRIVATE/'quota.json'
        quota=json.loads(quota_file.read_text()) if quota_file.exists() else {}
        day=datetime.now(timezone.utc).date().isoformat()
        if quota.get('day')!=day:
            quota={'day':day,'count':0,'last':0}
        if quota['count']>=30:
            raise DemoError('今日演示次数已用完')
        if time.time()-quota.get('last',0)<30:
            raise DemoError('请在上次运行 30 秒后重试')
        quota.update(count=quota['count']+1,last=time.time())
        quota_file.write_text(json.dumps(quota))
        job_id=uuid.uuid4().hex
        JOBS[job_id]={'state':'running','step':'starting','message':'准备连接 BoxLite'}
        def work():
            try:
                def notify(step,message):
                    JOBS[job_id].update(step=step,message=message)
                report=Engine(config()).run(notify)
                report['job_id']=job_id
                temporary=HERE/'last-run.tmp'
                temporary.write_text(json.dumps(report,ensure_ascii=False))
                temporary.replace(HERE/'last-run.json')
                JOBS[job_id]={'state':'done','report':report}
            except Exception as error:
                message=str(error) if isinstance(error,DemoError) else '实验未完成，未生成成功结果。可稍后重试。'
                JOBS[job_id]={'state':'error','message':message}
            finally:
                LOCK.release()
        threading.Thread(target=work,daemon=True).start()
        return job_id
    except Exception:
        LOCK.release()
        raise
