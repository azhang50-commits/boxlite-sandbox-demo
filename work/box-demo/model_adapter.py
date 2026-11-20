"""Optional model interface. No model is needed to execute the isolation experiment."""
import json
import os
import urllib.request

def explain_evidence(report, audience='AI agent platform engineer'):
    key=os.environ.get('MODEL_API_KEY')
    if not key:
        raise RuntimeError('Configure MODEL_API_KEY, MODEL_BASE_URL and MODEL_NAME first')
    base=os.environ.get('MODEL_BASE_URL','https://api.openai.com/v1').rstrip('/')
    model=os.environ.get('MODEL_NAME')
    if not model:
        raise RuntimeError('MODEL_NAME is required')
    body={'model':model,'messages':[
        {'role':'system','content':'Explain measured sandbox evidence to the specified audience. Distinguish facts from inferences. Do not claim this is a security audit or that ordinary VMs cannot isolate workloads. Do not generate executable code.'},
        {'role':'user','content':json.dumps({'audience':audience,'evidence':report},ensure_ascii=False)}]}
    req=urllib.request.Request(base+'/chat/completions',data=json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=45) as response:
        return json.load(response)['choices'][0]['message']['content']
