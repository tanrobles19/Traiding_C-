import websocket
import sqlite3
import json
from datetime import datetime, timedelta
import pytz

def save_finnhub_websocket_news_to_db(data):
    # Conexión a la base de datos
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    for noticia in data["data"]:
        new_id = noticia["id"]
        title = noticia["headline"]
        related = noticia["related"]
        category = noticia["category"]
        source = noticia["source"]
        summary = noticia["summary"]
        url = noticia["url"]

        # Convertir la fecha a hora de Costa Rica
        utc_dt = datetime.utcfromtimestamp(noticia["datetime"]).replace(tzinfo=pytz.utc)
        cr_time = utc_dt.astimezone(pytz.timezone('America/Costa_Rica')).strftime('%Y-%m-%d %H:%M:%S')

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Fecha actual

        # Verificar si ya existe el `new_id` en la base de datos
        cursor.execute("SELECT 1 FROM Finnhub_websocket_news WHERE new_id = ?", (new_id,))
        if cursor.fetchone():
            continue  # Saltar si la noticia ya está en la base de datos

        # Insertar la noticia en la base de datos
        cursor.execute('''
            INSERT INTO Finnhub_websocket_news (new_id, title, date, link, stocks, timestamp, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (new_id, title, cr_time, url, related, timestamp, "finnhub_websocket"))

    # Guardar los cambios y cerrar la conexión
    conn.commit()
    conn.close()

def on_message(ws, message):
    print("Received message: ##########")
    print(message)
    print(" ")
    print("Received message: ##########")
    try:
        data = json.loads(message)

        if "data" in data:
            save_finnhub_websocket_news_to_db(data)
            for noticia in data["data"]:
                new_id = noticia.get("id", "N/A")
                category = noticia.get("category", "N/A")
                headline = noticia.get("headline", "No headline")
                source = noticia.get("source", "No source")
                summary = noticia.get("summary", "No summary")
                url = noticia.get("url", "No URL")
                related = noticia.get("related", "No related symbol")
                
                # Convertir el timestamp 'datetime' a formato legible (hora UTC)
                datetime_utc = datetime.utcfromtimestamp(noticia["datetime"])

                # Restar 6 horas para ajustar a la hora de Costa Rica (UTC-6)
                datetime_cr = datetime_utc - timedelta(hours=6)

                # Convertir a formato legible de fecha y hora
                datetime_str = datetime_cr.strftime('%Y-%m-%d %H:%M:%S')

                # Imprimir la información de la noticia con el símbolo relacionado
                print(f"ID: {new_id}")                
                print(f"Symbol: {related}")
                print(f"Category: {category}")
                print(f"Headline: {headline}")
                print(f"Date (Costa Rica): {datetime_str}")
                print(f"Source: {source}")
                print(f"Summary: {summary}")
                print(f"URL: {url}")
                print("-" * 80)  # Separador para mejorar la legibilidad

        # Si se recibe un mensaje de tipo ping, responder con pong automáticamente (WebSocket)
        elif "type" in data and data["type"] == "ping":
            print("Received ping, sending pong...")
            ws.send('{"type":"pong"}')

    except Exception as e:
        print(f"Error while processing message: {e}")

def on_error(ws, error):
    print(error)

def on_close(ws):
    print("### closed ###")

def on_open(ws, symbols):
    # Suscribir a noticias para cada símbolo recibido como parámetro
    for symbol in symbols:
        ws.send(f'{{"type":"subscribe-news","symbol":"{symbol}"}}')

def load_database():
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    cursor.execute("SELECT ticker FROM Stocks")
    tickers = cursor.fetchall()

    symbols = [ticker[0] for ticker in tickers]

    conn.close()
    
    return symbols

def run_finnhub_websocket(token):
    websocket.enableTrace(True)

    symbols = load_database()

    ws = websocket.WebSocketApp(
        f"wss://ws.finnhub.io?token={token}",
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    
    ws.on_open = lambda ws: on_open(ws, symbols)
    
    ws.run_forever()

if __name__ == "__main__":
    token = "d1aq0a1r01qjhvtqlbbgd1aq0a1r01qjhvtqlbc0"   
    run_finnhub_websocket(token)
