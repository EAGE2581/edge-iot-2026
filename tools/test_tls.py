"""测试 paho-mqtt 通过 TLS 连接 EMQX 8883。"""
import ssl
import time

import paho.mqtt.client as mqtt

HOST = "localhost"
PORT = 8883
CA = "/home/hldqa/opcua-lab/certs/ca.crt"


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("[TLS] 连接成功")
        client.subscribe("test/tls")
        client.publish("test/tls", "hello over TLS")
    else:
        print(f"[TLS] 连接失败: rc={rc}")


def on_message(client, userdata, msg):
    print(f"[TLS] 收到: {msg.topic} = {msg.payload.decode()}")
    client.disconnect()


ctx = ssl.create_default_context(cafile=CA)
ctx.check_hostname = False   # 用 IP 或 localhost 连接，不检查 hostname
ctx.verify_mode = ssl.CERT_REQUIRED

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.tls_set_context(ctx)
client.on_connect = on_connect
client.on_message = on_message

print(f"[TLS] 连接 {HOST}:{PORT} ...")
client.connect(HOST, PORT, 30)
client.loop_start()
time.sleep(3)
client.loop_stop()
