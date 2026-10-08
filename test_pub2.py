import paho.mqtt.client as mqtt
client = mqtt.Client()
client.connect('localhost', 1883)
client.publish('driver/CAM_001/telemetry', '{"is_sleeping": true, "sleep_score": 90}')
client.disconnect()
