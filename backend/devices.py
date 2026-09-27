import json
import threading

def dispatch(settings, command):
    # An explicit allowlist remains authoritative regardless of model output.
    if command['device_id']!='alarm-light-01' or command['action']!='TURN_ON' or command['duration_seconds']!=30:
        raise ValueError('Device action rejected by allowlist')
    if settings.device_mode=='mock':
        return {'status':'mock_executed','command_id':command['command_id'],'detail':'模拟警灯已响应；未操作任何真实设备'}
    if settings.device_mode!='mqtt':
        raise ValueError('Unknown device mode')
    import paho.mqtt.client as mqtt
    connected=threading.Event(); acknowledged=threading.Event(); response={}
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    def on_connect(c,u,f,reason,props):
        if reason==0:
            c.subscribe('visionguard/device/alarm-light-01/ack',qos=1)
    def on_subscribe(c,u,mid,reason,props): connected.set()
    def on_message(c,u,msg):
        try: data=json.loads(msg.payload)
        except (ValueError,UnicodeError): return
        if data.get('command_id')==command['command_id'] and data.get('status')=='executed':
            response.update(data); acknowledged.set()
    client.on_connect=on_connect; client.on_subscribe=on_subscribe; client.on_message=on_message
    client.connect(settings.mqtt_host,settings.mqtt_port,keepalive=20); client.loop_start()
    try:
        if not connected.wait(5): raise TimeoutError('MQTT subscription not ready')
        info=client.publish('visionguard/device/alarm-light-01/command',json.dumps(command),qos=1)
        info.wait_for_publish(timeout=5)
        if not acknowledged.wait(8):
            return {'status':'delivery_unknown','command_id':command['command_id'],'detail':'未收到设备ACK；不能据发布成功认定执行成功，也不会自动重复发送'}
        return {'status':'device_acknowledged','command_id':command['command_id'],'detail':response}
    finally:
        client.disconnect(); client.loop_stop()

