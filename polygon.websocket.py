from polygon import WebSocketClient
from polygon.websocket.models import WebSocketMessage
from typing import List
import sqlite3
from datetime import datetime
from datetime import date
from datetime import datetime, timedelta
import pytz
import pandas as pd
import numpy as np
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from polygon import RESTClient
from playsound import playsound
from polygon_news import get_polygon_news
from benzinga_news import get_benzinga_news
from globenewswire import get_globenewswire_news
from finnhub_news import get_finnhub_news
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class News:
    id: int
    author: Optional[str]
    created: str  # Fecha y hora completa legible en Costa Rica
    created_hour_cr: int
    created_minute_cr: int
    title: str
    url: str

# def put_order_interactive_brokers(symbol, ib):

#     print("put_order_interactive_brokers *******")

#     stock = Stock(symbol, 'SMART', 'USD')

#     order = MarketOrder('BUY', 1)

#     trade = ib.placeOrder(stock, order)

#     time.sleep(2)

#     print("Estado de la orden")
#     print(trade.orderStatus.status)

def print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]

def get_average_volume_excluding_last_record(ticker):
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    query = '''
    SELECT volume FROM MinuteCandles
    WHERE ticker = ?
    ORDER BY id
    '''
    cursor.execute(query, (ticker,))

    records = cursor.fetchall()
    if len(records) <= 1:
        return 0

    records_without_last = records[:-1]

    total_volume = sum([record[0] for record in records_without_last])
    average_volume = total_volume / len(records_without_last)

    conn.close()

    return average_volume

def get_max_volume_excluding_last(ticker):
    # Conexión a la base de datos
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    query = '''
    SELECT volume FROM MinuteCandles
    WHERE ticker = ?
    ORDER BY id
    '''
    cursor.execute(query, (ticker,))

    # Obtener los registros de volumen
    records = cursor.fetchall()
    
    if len(records) <= 1:
        return 0

    # Excluir la última vela
    records_without_last = records[:-1]

    # Obtener el volumen máximo de las velas restantes
    max_volume = max(record[0] for record in records_without_last)

    # Cerrar la conexión a la base de datos
    conn.close()

    return max_volume    

# Configuración del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

executor = ThreadPoolExecutor(max_workers=30)

def get_avg_month_volume(ticker: str, conn, cursor) -> int:
    try:
        cursor.execute("SELECT avg_month_volume FROM Stocks WHERE ticker = ?", (ticker,))
        
        row = cursor.fetchone()

        if row:
            return row[0]
        else:
            return -1  # Retorna -1 si no se encuentra el ticker
    except Exception as e:
        print(f"Error al obtener el avg_month_volume para {ticker}: {e}")
        return -1

def get_close_price(ticker: str, conn, cursor) -> float:
    try:
        cursor.execute("SELECT close FROM Stocks WHERE ticker = ?", (ticker,))
        
        row = cursor.fetchone()

        if row:
            return row[0]
        else:
            return -1

    except sqlite3.Error as e:
        print(f"Error al acceder a la base de datos: {e}")
        return -1

def is_symbol_registered(symbol: str, conn, cursor) -> bool:

    try:
        cursor.execute("SELECT COUNT(*) FROM TradeSignalsBuy WHERE symbol = ?", (symbol,))
        
        count = cursor.fetchone()[0]

        return count > 0

    except sqlite3.Error as e:
        print(f"Error al acceder a la base de datos: {e}")
        return False

def get_relative_volume(hour, minute, am_pm, ticker, cursor):
    cursor.execute('''
        SELECT relative_volume
            FROM RelativeVolumeRatio
                WHERE hour = ? 
                AND minute = ?
                AND amPm = ?
                AND symbol =?
    ''', (hour, minute, am_pm, ticker))

    row = cursor.fetchone()
    return row[0] if row is not None else -1

def are_consecutive(v1, v2, v3):

    # Convertir las horas y minutos a enteros
    hour1, minute1, ampm1 = int(v1[0]), int(v1[1]), v1[2]
    hour2, minute2, ampm2 = int(v2[0]), int(v2[1]), v2[2]
    hour3, minute3, ampm3 = int(v3[0]), int(v3[1]), v3[2]

    # Asegurarse de que la hora AM/PM sea consistente (si está en AM o PM, no pueden cruzarse)
    if ampm1 != ampm2 or ampm2 != ampm3:
        return False

    # Comprobar que los minutos de v2 son un minuto después de v1 y los minutos de v3 son un minuto después de v2
    if minute2 == minute1 + 1 and minute3 == minute2 + 1:
        return True

    # Si estamos al final de una hora (por ejemplo, de 1:59 AM a 2:00 AM), entonces también son consecutivos
    if minute1 == 59 and minute2 == 0 and hour2 == hour1 + 1 and minute3 == 0 and hour3 == hour2 + 1:
        return True

    return False

def calculate_relative_volume(symbol, hour, minute, ampm):

    query = """
    SELECT 
        COUNT(*) AS count_result, 
        SUM(volume) / COUNT(*) AS relative_volume
    FROM 
        HistoryByMin
    WHERE 
        stockID = ? 
        AND hour = ? 
        AND minute = ? 
        AND amPm = ?
    """

    print(f"Executing query for symbol: {symbol}, hour: {hour}, minute: {minute}, ampm: {ampm}")

    cursor.execute(query, (symbol, hour, minute, ampm))

    result = cursor.fetchone()

    if result:
        count_result, relative_volume = result
        return count_result, relative_volume
    else:
        return 0, 0.0

def insert_trade_signal(symbol, hour, minute, am_pm, date, close, volume, slope, conn, cursor):
    
    # Contar cuántas veces existe el símbolo
    cursor.execute("SELECT COUNT(*) FROM TradeSignalsBuy WHERE symbol = ?", (symbol,))
    count = cursor.fetchone()[0]
    
    # Primera vez
    if count == 0:
        new_count = 1
        first_time = True
    else:
        new_count = count + 1
        first_time = False

    # Insertar el nuevo registro
    cursor.execute("""
        INSERT INTO TradeSignalsBuy (symbol, hour, minute, amPm, date, close, volume, slope, count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (symbol, hour, minute, am_pm, date, close, volume, slope, new_count))

    conn.commit()

    inserted_id = cursor.lastrowid
    
    return inserted_id, first_time

def insert_momentum_stock(ticker, hour, minute, amPM, current_volume, current_close, last_candle_volume, day_volume_average):
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()
    try:
        # Preparar la consulta SQL para insertar los datos
        query = '''
        INSERT INTO momentumStocks (ticker, hour, minute, amPm, current_volumen, current_close, last_candle_volume, day_volume_average)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        '''
        
        # Ejecutar la consulta con los valores proporcionados
        cursor.execute(query, (ticker, hour, minute, amPM, current_volume, current_close, last_candle_volume, day_volume_average))
        
        # Confirmar los cambios en la base de datos
        conn.commit()
        conn.close()
    
    except Exception as e:
        print(f"[ERROR] Ocurrió un error al insertar los datos: {e}")


def convert_utc_to_cr_time(timestamp):
    utc_zone = pytz.utc
    cr_zone = pytz.timezone('America/Costa_Rica')
    dt_utc = datetime.fromtimestamp(timestamp / 1000, tz=utc_zone)
    dt_cr = dt_utc.astimezone(cr_zone)

    date = dt_cr.strftime('%b %d, %Y')  # May 20, 2025
    hour = dt_cr.strftime('%I')  # 01
    minute = dt_cr.strftime('%M')  # 18
    am_pm = dt_cr.strftime('%p')  # AM/PM

    return date, hour, minute, am_pm

def get_stocks_in_range(start_index, end_index, cursor):

    cursor.execute('''
        SELECT ticker, close, stock_index
        FROM Stocks
        WHERE stock_index BETWEEN ? AND ?
    ''', (start_index, end_index))

    rows = cursor.fetchall()

    tickers = [row[0] for row in rows]
    return tickers

def create_subscription_list(tickers):
    subscriptions = [f"AM.{ticker}" for ticker in tickers]
    return subscriptions    

def webSocketRUN(subscriptionList, cursor, conn, activity_log):

    ws = WebSocketClient(api_key='0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ', subscriptions=subscriptionList)

    def handle_msg(msg: List[WebSocketMessage]):

        for webSocketM in msg:

            date, hour, minute, amPM = convert_utc_to_cr_time(webSocketM.start_timestamp)

            cursor.execute("""
                INSERT INTO MinuteCandles (ticker, hour, minute, close, volume) 
                VALUES (?, ?, ?, ?, ?)
            """, (webSocketM.symbol, hour, minute, webSocketM.close, webSocketM.volume))    

            conn.commit()            

            relative_volume = get_relative_volume(hour, minute, amPM, webSocketM.symbol, cursor)

            if webSocketM.volume >= 50000 and isinstance(relative_volume, (int, float)) and relative_volume != -1:

                if relative_volume == 0:
                    relative_volume = 1000

                close_price = get_close_price(webSocketM.symbol, conn, cursor)
                relative_volume_factor = round(webSocketM.volume / relative_volume, 2)

                if relative_volume_factor >= 8 and webSocketM.close >= close_price * 1.10:
              
                    print(f"{webSocketM.symbol} time {hour}:{minute} {amPM} Relative Volume Ratio: {relative_volume_factor}X Volume {webSocketM.volume} Close {webSocketM.close}")
                        
                    cursor.execute('''
                        INSERT INTO TradeSignalsBuy (
                            symbol, hour, minute, amPm, date, close, volume,
                            relative_volume, polygon_news_id, benzinga_news_id, finnhub_news_id, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        webSocketM.symbol,
                        hour,  # hour
                        minute,  # minute
                        amPM,  # amPm
                        date,     # date — puedes reemplazar esto si tienes la fecha original
                        webSocketM.close,  # close
                        webSocketM.volume,  # volume
                        relative_volume_factor,  # relative_volume
                        None,   # polygon_news
                        None,   # benzinga_news
                        None,    # finnhub_news
                        print_current_time()
                    ))

                    inserted_id = cursor.lastrowid

                    conn.commit()

                    search_news(inserted_id, webSocketM.symbol, relative_volume_factor, webSocketM.volume, webSocketM.close)     
                    executor.submit(search_news, m.symbol, time.localtime().tm_hour, current_minute, m.close, cumulative_volume, relative_volume_factor)

    ws.run(handle_msg=handle_msg)

def get_recent_prices(ticker, limit=7):
    import sqlite3

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    query = """
        SELECT close
        FROM MinuteCandles
        WHERE ticker = ?
        ORDER BY id DESC
        LIMIT ?
    """
    cursor.execute(query, (ticker, limit))
    
    # Invertimos la lista porque se trae en orden descendente
    precios = [row[0] for row in cursor.fetchall()][::-1]

    conn.close()
    return precios if len(precios) >= limit else []    

def get_five_minutes_volume(symbol, hour, minute, amPM):
    import sqlite3

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    query = """
        SELECT SUM(volume) / COUNT(*) AS relative_volume
        FROM HistoryByMin
        WHERE
            stockID = ?
            AND hour = ? 
            AND minute = ? 
            AND amPm = ?
    """
    cursor.execute(query, (symbol, hour, minute, amPM))
    
    row = cursor.fetchone()
    
    if row:
        relative_volume = row[0]
    else:
        relative_volume = 0

    conn.close()
    return relative_volume

def get_prices_from_db(ticker, cursor):
    
    query = """
        SELECT close
        FROM MinuteCandles
        WHERE ticker = ?
    """
    cursor.execute(query, (ticker,))
    
    precios = [row[0] for row in cursor.fetchall()]
        
    return precios

def update_news_flag(tradeSignalID, symbol, source, newId):
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    # Diccionario con las columnas actualizadas
    valid_sources = {
        'polygon': 'polygon_news_id',
        'benzinga': 'benzinga_news_id',
        'finnhub': 'finnhub_news_id',
        'globenewswire': 'globenewswire_id'
    }

    if source not in valid_sources:
        raise ValueError("El parámetro 'source' debe ser 'polygon', 'benzinga', 'finnhub' o 'globenewswire'")

    column = valid_sources[source]

    # Verificar si ya existe un registro con ese ID de noticia para el símbolo dado
    cursor.execute(f"""
        SELECT COUNT(*) FROM TradeSignalsBuy
        WHERE {column} = ? AND symbol = ?
    """, (newId, symbol))

    result = cursor.fetchone()
    news_exists = result[0] > 0  # Si el resultado es mayor a 0, significa que ya existe

    if news_exists:
        conn.close()
        return True  # Si ya existe, retorna True

    # Si no existe, actualizar el registro con el nuevo ID de noticia
    cursor.execute(f"""
        UPDATE TradeSignalsBuy
        SET {column} = ?
        WHERE id = ?
    """, (newId, tradeSignalID))
    
    conn.commit()
    conn.close()

    return False

def search_news(tradeSignalId, symbol, relative_volumen_factor, volume, close): 
    today = date.today().isoformat()

    benzinga_news_list = get_benzinga_news(symbol, today)
    polygon_news_list = get_polygon_news(symbol, today)
    finnhub_news_list = get_finnhub_news(symbol)
    blobeNewsID = get_globenewswire_news(symbol)

    detected_sources = []
    thereAre_news_benzinga = True
    thereAre_news_polygon = True
    thereAre_news_finhub = True
    thereAre_news_globenewswire = True

    if blobeNewsID != "none":
        thereAre_news_globenewswire = update_news_flag(tradeSignalID=tradeSignalId, symbol=symbol, source="globenewswire", newId=blobeNewsID)
        detected_sources.append("globenewswire")

    if len(benzinga_news_list) > 0:
        thereAre_news_benzinga = update_news_flag(tradeSignalID=tradeSignalId, symbol=symbol, source="benzinga", newId=benzinga_news_list[0].id)
        detected_sources.append("benzinga")

    if len(polygon_news_list) > 0:
        thereAre_news_polygon = update_news_flag(tradeSignalID=tradeSignalId, symbol=symbol, source="polygon", newId="TEST")
        print(f"Symbol  Poly   = {symbol}")
        detected_sources.append("polygon")

    if len(finnhub_news_list) > 0:
        thereAre_news_finhub = update_news_flag(tradeSignalID=tradeSignalId, symbol=symbol, source="finnhub", newId=finnhub_news_list[0].id)
        print(f"Symbol  Fin   = {symbol}")
        detected_sources.append("finnhub")

    if thereAre_news_benzinga == False or thereAre_news_polygon == False or thereAre_news_finhub == False or thereAre_news_globenewswire == False:
        # if thereAre_news == True:
        sources_message = ", ".join(detected_sources)
        print(" ")                                                                  
        print(f"\033[1;33mNews {symbol} \033[0m {sources_message} \033[1;33m -> NEWS Alert\033[0m")    
        print(f"Symbol     = {symbol}")
        print(f"Relative.V = {relative_volumen_factor}")
        print(f"Volumen    = {volume}")
        print(f"Close      = {close}")
        print_news_summary_benzinga(benzinga_news_list)
        print_news_summary_finnhub(finnhub_news_list)     
        
        print(" ")                                            
        executor.submit(
            play_bell
        )                                     

def print_news_summary_benzinga(news_list: List[News]) -> None:
    for news in news_list:
        hour = news.created_hour_cr
        minute = str(news.created_minute_cr).zfill(2) 
        print(f"Title B = {news.title}")
        print(f"Date = {hour}:{minute}")

def print_news_summary_finnhub(news_list: List[News]) -> None:
    for news in news_list:
        print(f"Title F = {news.title}")
        print(f"Date = {news.created_hour_cr}:{str(news.created_minute_cr).zfill(2)}")

def check_news_for_symbol(symbol: str) -> bool:
    # Conectar a la base de datos
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()   
    
    # Consulta para obtener los registros del símbolo
    cursor.execute("SELECT polygon_news, benzinga_news, finnhub_news FROM TradeSignalsBuy WHERE symbol = ?", (symbol,))
    records = cursor.fetchall()
    
    # Iterar sobre todos los registros obtenidos
    for record in records:
        polygon_news, benzinga_news, finnhub_news = record
        
        # Si alguno de los campos tiene contenido (es decir, no está vacío), retornamos False
        if polygon_news or benzinga_news or finnhub_news:
            conn.close()  # Cerrar la conexión
            return True
    
    # Si todos los registros tienen los campos vacíos, retornamos True
    conn.close()  # Cerrar la conexión
    return False

def play_bell():    
    playsound('new_york_stock_exchange_opening_bell.m4a')                          

conn = sqlite3.connect('histFinanData.db')
cursor = conn.cursor()

start_index = 0
end_index = 2731
tickers = get_stocks_in_range(start_index, end_index, cursor)

subscriptions = create_subscription_list(tickers)
print(f"Subscriptions created: {len(subscriptions)}")
activity_log = defaultdict(list)
webSocketRUN(subscriptions, cursor, conn, activity_log)   
