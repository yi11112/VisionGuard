"""MQTT-only simulated device. Persistent command IDs prevent duplicate execution."""
import json
import os
import sqlite3
from pathlib import Path
import paho.mqtt.client as mqtt

path=Path(__file__).resolve().parents[1]/'data'/'device.db'
path.parent.mkdir(exist_ok=True)
with sqlite3.connect(path) as db: db.execute('CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY)')
def on_connect(client, userdata, flags, reason, properties):
    if reason==0: client.subscribe('visionguard/device/alarm-light-01/command',qos=1)
def on_message(client, userdata, message):
    try:
        cmd=json.loads(message.payload)
        if cmd.get('device_id')!='alarm-light-01' or cmd.get('action')!='TURN_ON' or cmd.get('duration_seconds')!=30: return
        with sqlite3.connect(path) as db:
            fresh=db.execute('INSERT OR IGNORE INTO commands VALUES(?)',(cmd['command_id'],)).rowcount==1
        if fresh: print('MOCK LIGHT ON for 30s:',cmd['command_id'],flush=True)
        client.publish('visionguard/device/alarm-light-01/ack',json.dumps({'command_id':cmd['command_id'],
                       'status':'executed','simulated':True,'duplicate':not fresh}),qos=1)
    except (ValueError,KeyError): return
client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect=on_connect; client.on_message=on_message
client.connect(os.getenv('MQTT_HOST','127.0.0.1'),int(os.getenv('MQTT_PORT','1884')))
client.loop_forever()
