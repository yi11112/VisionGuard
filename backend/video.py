import uuid
from pathlib import Path
import cv2
import numpy as np

def analyze_video(path, settings, store, polygon, stride=3):
    from ultralytics import YOLO
    import torch
    if not Path(settings.yolo_weights).is_file():
        raise ValueError('YOLO weights missing; place yolo11n.pt in models/')
    model=YOLO(settings.yolo_weights)
    cap=cv2.VideoCapture(str(path))
    if not cap.isOpened(): raise ValueError('Unable to decode video')
    fps=cap.get(cv2.CAP_PROP_FPS)
    if not 1<=fps<=240: cap.release(); raise ValueError('Invalid video FPS')
    tracks={}; emitted=set(); events=[]; frame_no=0
    snapshots=settings.data_dir/'snapshots'; snapshots.mkdir(parents=True,exist_ok=True)
    try:
        while frame_no<round(fps*120):
            ok,frame=cap.read()
            if not ok: break
            frame_no+=1
            if frame_no%stride: continue
            height,width=frame.shape[:2]
            zone=np.array([[int(x*width),int(y*height)] for x,y in polygon],np.int32)
            result=model.track(frame,persist=True,classes=[0],conf=0.45,tracker='bytetrack.yaml',
                               device=0 if torch.cuda.is_available() else 'cpu',verbose=False)[0]
            current=frame_no/fps; seen=set()
            if result.boxes.id is None: tracks.clear(); continue
            for box,tid,confidence in zip(result.boxes.xyxy.cpu().tolist(),result.boxes.id.int().cpu().tolist(),result.boxes.conf.cpu().tolist()):
                x1,y1,x2,y2=box; foot=((x1+x2)/2,y2)
                if cv2.pointPolygonTest(zone,foot,False)<0: continue
                seen.add(tid)
                history=tracks.setdefault(tid,{'start':current,'last':current})
                if current-history['last']>2*stride/fps: history['start']=current
                history['last']=current; duration=current-history['start']
                if duration<3 or tid in emitted: continue
                annotated=frame.copy(); cv2.polylines(annotated,[zone],True,(0,0,255),3)
                cv2.rectangle(annotated,(int(x1),int(y1)),(int(x2),int(y2)),(0,255,0),2)
                snapshot=uuid.uuid4().hex+'.jpg'; cv2.imwrite(str(snapshots/snapshot),annotated)
                event={'event_type':'INTRUSION','zone':'自定义限制区','camera_id':'uploaded-video',
                       'confidence':float(confidence),'duration':round(duration,2),'source':'video',
                       'description':'人员脚点进入指定多边形，持续至少3秒。','track_id':tid,'snapshot':snapshot,
                       'observations':[{'video_second':round(current,2),'foot_point':foot,'polygon':polygon}]}
                events.append(store.add(event)); emitted.add(tid)
            tracks={tid:h for tid,h in tracks.items() if tid in seen}
    finally: cap.release()
    return {'events':events,'processed_seconds':round(frame_no/fps,2),'limit_seconds':120,
            'note':'仅单摄像头人员禁区检测；不做人脸识别、安全帽检测或跨摄像头身份关联'}
