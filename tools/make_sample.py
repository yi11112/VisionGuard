"""Generate a repeated-frame pipeline fixture, not a real tracking benchmark."""
from pathlib import Path
import cv2
import ultralytics

root=Path(__file__).resolve().parents[1]
source=Path(ultralytics.__file__).parent/'assets'/'bus.jpg'
frame=cv2.imread(str(source))
if frame is None: raise RuntimeError('Ultralytics bus.jpg test asset is unavailable')
frame=cv2.resize(frame,(540,720))
cv2.putText(frame,'SYNTHETIC LOOP - PIPELINE TEST',(8,24),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,255),1)
directory=root/'samples'; directory.mkdir(exist_ok=True)
target=directory/'pipeline-test.mp4'
writer=cv2.VideoWriter(str(target),cv2.VideoWriter_fourcc(*'mp4v'),10,(540,720))
if not writer.isOpened(): raise RuntimeError('MP4 encoder unavailable')
try:
    for _ in range(60): writer.write(frame)
finally: writer.release()
print(target)
print('Source: Ultralytics packaged bus.jpg; repeated frames, NOT real surveillance footage.')
