import websocket
import json

# Reemplaza por tu clave API válida
API_KEY = "bz.4KCPALWSMP2MNWOIFFYEHANTDL7ANAMJ"

def on_open(ws):
    print("🔗 Conectado al WebSocket de noticias...")
    # No se necesita payload extra; la autenticación ocurre en el handshake por token en URL

def on_message(ws, message):
    obj = json.loads(message)
    kind = obj.get("kind")
    data = obj.get("data", {})
    content = data.get("content", {})
    print(f"[{kind}] ID {data.get('id')}: {content.get('title', 'sin título')}")

def on_error(ws, error):
    print("❌ Error:", error)

def on_close(ws, status, msg):
    print("🔌 Conexión cerrada")

# Conexión al WebSocket con token en la URL
url = f"wss://api.benzinga.com/api/v1/news/stream?token={API_KEY}"
ws = websocket.WebSocketApp(url,
                            on_open=on_open,
                            on_message=on_message,
                            on_error=on_error,
                            on_close=on_close)

ws.run_forever()