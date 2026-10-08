import time, paho.mqtt.client as mqtt
def on_connect(c, u, f, rc): print('CONNECTED', rc)
client = mqtt.Client()
client.on_connect = on_connect
client.connect('127.0.0.1', 1883)
client.loop_start()
time.sleep(1)
