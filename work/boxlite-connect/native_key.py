"""Native password dialog; no localhost web form and no credential in argv/logs."""
import json,os,subprocess,sys
from pathlib import Path

def valid_key(key):
 return isinstance(key,str) and key.startswith('blk_') and len(key)>=16 and not any(c.isspace() for c in key)

def save_key(path,key):
 if not valid_key(key):raise ValueError('BoxLite Key 格式不正确')
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);os.fchmod(fd,0o600)
 with os.fdopen(fd,'w') as out:json.dump({'BOXLITE_REST_URL':'https://api.boxlite.ai','BOXLITE_API_KEY':key},out)

def dialog(script):
 result=subprocess.run(['osascript','-'],input=script,capture_output=True,text=True)
 if result.returncode:raise KeyboardInterrupt('已取消')
 return result.stdout.strip()

def prompt_key(path):
 path=Path(path)
 if path.is_file():
  existing=json.loads(path.read_text()).get('BOXLITE_API_KEY')
  if valid_key(existing):
   result=dialog('''tell application "System Events"
activate
set response to display dialog "已保存本机 BoxLite 密钥。密钥不会上传到演示 Box。" buttons {"取消", "更换密钥", "使用已保存"} default button "使用已保存" with title "启动 BoxLite Demo"
return button returned of response
end tell''')
   if result=='使用已保存':return existing
   if result=='取消':raise KeyboardInterrupt('已取消')
 key=dialog('''tell application "System Events"
activate
set response to display dialog "请输入 BoxLite API Key。密钥只保存在本机，不会写入网页或聊天记录。" default answer "" with hidden answer buttons {"取消", "连接"} default button "连接" with title "连接 BoxLite"
return text returned of response
end tell''')
 save_key(path,key);return key

def prompt_local_key(path):
 key=dialog('''tell application "System Events"
activate
set response to display dialog "本机 BoxLite 演示已准备好。Cloud API Key 可留空；填入时只保存在本机，本次演示不会调用云端。" default answer "" with hidden answer buttons {"取消", "启动演示"} default button "启动演示" with title "BoxLite Demo"
return text returned of response
end tell''')
 if key:save_key(path,key)
 return key

if __name__=='__main__':
 try:
  prompt_key(Path(__file__).resolve().parent/'credentials.json')
  print('CREDENTIAL_READY',flush=True)
 except KeyboardInterrupt:print('已取消',flush=True);sys.exit(1)
 except ValueError:print('密钥格式不正确，请重新启动填写。',flush=True);sys.exit(1)
