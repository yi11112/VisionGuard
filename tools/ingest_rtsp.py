"""Capture a bounded RTSP clip and submit it to the local video API."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
import httpx
import imageio_ffmpeg

parser=argparse.ArgumentParser()
parser.add_argument('--url',required=True,help='RTSP URL of a camera you are authorized to access')
parser.add_argument('--seconds',type=int,default=10)
parser.add_argument('--api',default='http://127.0.0.1:8000')
parser.add_argument('--polygon',default='[[0.2,0.2],[0.8,0.2],[0.8,0.95],[0.2,0.95]]')
args=parser.parse_args()
if urlparse(args.url).scheme not in ['rtsp','rtsps']: parser.error('Expected rtsp:// or rtsps:// URL')
if not 3<=args.seconds<=120: parser.error('seconds must be between 3 and 120')
with tempfile.TemporaryDirectory(prefix='visionguard-rtsp-') as folder:
    path=Path(folder)/'capture.mp4'
    command=[imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-loglevel','error','-rtsp_transport','tcp',
             '-i',args.url,'-t',str(args.seconds),'-an','-vf','scale=960:-2','-r','10',
             '-c:v','libx264','-preset','ultrafast','-y',str(path)]
    subprocess.run(command,check=True,timeout=args.seconds+30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    with path.open('rb') as video:
        response=httpx.post(args.api+'/api/videos',files={'file':('capture.mp4',video,'video/mp4')},
                            data={'polygon':args.polygon},timeout=180)
        response.raise_for_status()
    print(json.dumps(response.json(),ensure_ascii=False,indent=2))
