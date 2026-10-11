import time, paho.mqtt.client as mqtt
print('Starting...')
client = mqtt.Client()
print('Connecting...')
client.connect('localhost', 1883)
print('Connected!')
