"""Start a local demo, then stop only subprocesses this launcher owns."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import json
import threading
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
TOOLS=Path(r'C:\Users\22081\Documents\Codex\tools\visionguard')
parser=argparse.ArgumentParser()
parser.add_argument('--mqtt',action='store_true',help='Run a real local MQTT broker and simulated device')
parser.add_argument('--open-browser',action='store_true',help='Open the local dashboard in the default browser')
args=parser.parse_args()
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
os.environ['VISIONGUARD_DATA']=str(ROOT/'data')
os.environ['YOLO_CONFIG_DIR']=str(ROOT/'data')
os.environ['YOLO_WEIGHTS']=str(ROOT/'models'/'yolo11n.pt')
os.environ['OLLAMA_MODELS']=str(TOOLS/'models'/'ollama')
os.environ['OLLAMA_HOST']='127.0.0.1:11434'
os.environ['OLLAMA_MAX_LOADED_MODELS']='1'
os.environ['OLLAMA_NUM_PARALLEL']='1'
os.environ['DEVICE_MODE']='mqtt' if args.mqtt else 'mock'
data=ROOT/'data'; data.mkdir(exist_ok=True)
children=[]; logs=[]
def listening(port):
    with socket.socket() as s:
        s.settimeout(.5)
        return s.connect_ex(('127.0.0.1',port))==0
def launch(command,name):
    log=(data/(name+'.log')).open('a',encoding='utf-8'); logs.append(log)
    p=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=log,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    children.append(p); return p
def ready(port,process):
    for _ in range(30):
        if listening(port): return
        if process.poll() is not None: raise RuntimeError(f'Service exited; inspect data/*.log (port {port})')
        time.sleep(.5)
    raise RuntimeError(f'Service did not start on port {port}')
def is_visionguard():
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:8000/openapi.json',timeout=2) as response:
            return json.load(response).get('info',{}).get('title')=='VisionGuard'
    except (OSError,ValueError):
        return False

def open_dashboard_when_ready():
    for _ in range(60):
        if is_visionguard():
            webbrowser.open('http://127.0.0.1:8000/')
            return
        time.sleep(.5)
    print('Browser not opened: server is not ready. Check the error above.',flush=True)

if listening(8000):
    if is_visionguard():
        print('VisionGuard is already running: http://127.0.0.1:8000/')
        if args.open_browser: webbrowser.open('http://127.0.0.1:8000/')
        raise SystemExit(0)
    print('Port 8000 is occupied by another application. Stop that application or change the port.')
    raise SystemExit(1)
try:
    if not listening(11434) and (TOOLS/'ollama'/'ollama.exe').exists():
        ready(11434,launch([str(TOOLS/'ollama'/'ollama.exe'),'serve'],'ollama'))
    if args.mqtt:
        if not listening(1884): ready(1884,launch([sys.executable,'tools/local_broker.py'],'mqtt'))
        launch([sys.executable,'tools/mock_device.py'],'mock-device')
    print('VisionGuard: http://127.0.0.1:8000 | CTRL+C stops this launcher\'s services.',flush=True)
    import uvicorn
    if args.open_browser:
        threading.Thread(target=open_dashboard_when_ready,daemon=True).start()
    uvicorn.run('backend.app:app',host='127.0.0.1',port=8000)
finally:
    for child in reversed(children):
        if child.poll() is None: child.terminate()
        try: child.wait(timeout=5)
        except subprocess.TimeoutExpired: child.kill()
    for log in logs: log.close()
