from pathlib import Path
import os,subprocess,socket,json,time,urllib.request
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT
PY=Path(os.environ['LOCALAPPDATA'])/'RF-One'/'Bank'/'venv'/'Scripts'/'python.exe'
with socket.socket() as s:
 running=s.connect_ex(('127.0.0.1',5111))==0
if not running:
 env=os.environ.copy();env['PYTHONPYCACHEPREFIX']=str(DATA/'pycache');env['PYTHONIOENCODING']='utf-8'
 proc=subprocess.Popen([str(PY),str(ROOT/'app.py')],cwd=ROOT,env=env,
  stdout=(DATA/'server.log').open('a',encoding='utf-8'),stderr=subprocess.STDOUT,creationflags=0x08000000|0x00000200)
 (DATA/'server.json').write_text(json.dumps({'pid':proc.pid,'url':'http://127.0.0.1:5111','code':str(ROOT)}),encoding='utf-8')
deadline=time.monotonic()+45
while time.monotonic()<deadline:
 try:
  with urllib.request.urlopen('http://127.0.0.1:5111/bank/work',timeout=5) as response:
   if response.status==200:break
 except OSError:time.sleep(.5)
else:raise SystemExit('RFBank non è pronto. Controllare il file server.log nella cartella dati RFBank.')
print('RFBank pronto: http://127.0.0.1:5111/bank/work')
