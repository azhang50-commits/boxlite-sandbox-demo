"""Fixed, auditable workload. Only synthetic files under isolation-lab are touched."""
import hashlib

ATTACK_CODE = '''import csv
from pathlib import Path
root = Path(base)
rows = list(csv.DictReader((root / "customer-a" / "leads.csv").open()))
result["leads"] = sum(int(row["leads"]) for row in rows)
other = root / "customer-b" / "private.txt"
try:
    result["cross_read"] = {"succeeded": True, "value": other.read_text()}
except OSError as error:
    result["cross_read"] = {"succeeded": False, "error": type(error).__name__}
try:
    other.unlink()
    result["cross_delete"] = {"succeeded": True}
except OSError as error:
    result["cross_delete"] = {"succeeded": False, "error": type(error).__name__}
'''
TASK_CODE = 'import json\nfrom pathlib import Path\nbase = str(Path(__file__).resolve().parent)\nresult = {}\n' + ATTACK_CODE + '\nprint(json.dumps(result))\n'
SCRIPT_HASH = hashlib.sha256(TASK_CODE.encode()).hexdigest()
SYNTHETIC_VALUE = 'SYNTHETIC_BETA_CUSTOMER_PLAN_DEMO_ONLY'
B_TASK_CODE = '''import json,hashlib
from pathlib import Path
private = Path(__file__).with_name("private.txt")
result = {"status":"completed", "file_sha256":hashlib.sha256(private.read_bytes()).hexdigest()}
print(json.dumps(result))
'''

def worker_script(base, shared, result_path):
    return '''import json,hashlib,runpy,io,contextlib
from pathlib import Path
from datetime import datetime,timezone
base = %r
root=Path(base)
(root/'customer-a').mkdir(parents=True,exist_ok=True)
(root/'customer-a'/'leads.csv').write_text(%r)
other=root/'customer-b'/'private.txt'
if %r:
    other.parent.mkdir(parents=True,exist_ok=True)
    other.write_text(%r)
    (other.parent/'task_b.py').write_text(%r)
task=root/'agent_task.py'
task.write_text(%r)
with contextlib.redirect_stdout(io.StringIO()):
    result=runpy.run_path(str(task))['result']
result['b_file_exists_after']=other.exists()
if %r:
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result['b_task']=runpy.run_path(str(other.parent/'task_b.py'))['result']
    except OSError as error:
        result['b_task']={'status':'failed','error':type(error).__name__}
result['kernel_fingerprint']=hashlib.sha256(Path('/proc/sys/kernel/random/boot_id').read_bytes()).hexdigest()[:12]
result['script_sha256']=%r
result['completed_at']=datetime.now(timezone.utc).isoformat()
result['base_path']=base
result['files']=[{'path':str(p.relative_to(root)), 'content':p.read_text()[:8000]} for p in sorted(root.rglob('*')) if p.is_file() and p.name!='result.json']
destination=Path(%r)
destination.parent.mkdir(parents=True,exist_ok=True)
destination.write_text(json.dumps(result))
print(json.dumps(result))
''' % (base, 'channel,leads\nSEO,42\nPaid,18\nReferral,10\n', shared, SYNTHETIC_VALUE, B_TASK_CODE, TASK_CODE, shared, SCRIPT_HASH, result_path)
