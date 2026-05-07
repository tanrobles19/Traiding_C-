from polygon import RESTClient
import pytz
from datetime import datetime, timedelta, date
from benzinga import news_data
from dataclasses import dataclass
from typing import List, Optional
import time
import sqlite3
from playsound import playsound
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
import csv
import pytz
import requests
from polygon import WebSocketClient
import finnhub
from ib_insync import *
from polygon.rest.models import (
    TickerNews,
)

executor = ThreadPoolExecutor(max_workers=10)

# Ajuste de zona horaria a Costa Rica (UTC-6)
CR_TIMEZONE = pytz.timezone("America/Costa_Rica")

def extract_cr_hour_minute(est_str: str) -> tuple[int, int]:
    dt = datetime.strptime(est_str, "%a, %d %b %Y %H:%M:%S %z")
    cr_time = dt.astimezone(CR_TIMEZONE)  # Convertir a hora de Costa Rica
    return cr_time.hour, cr_time.minute

@dataclass
class News:
    id: int
    author: Optional[str]
    created: str
    created_hour_cr: int
    created_minute_cr: int
    title: str
    url: str
    stocks: List[str]

def get_news(symbol: str, minutes_before: int) -> List[News]:
    start_time = time.time()

    today = date.today().isoformat()

    current_time = datetime.now(pytz.utc)  # Obtener la hora UTC
    current_time_cr = current_time.astimezone(CR_TIMEZONE)  # Convertir a hora de Costa Rica

    time_before = current_time_cr - timedelta(minutes=minutes_before)

    start_time_iso = time_before.isoformat()

    api_key = "bz.4KCPALWSMP2MNWOIFFYEHANTDL7ANAMJ"
    paper = news_data.News(api_key)

    # Consultar las noticias de hoy para el símbolo proporcionado
    stories = paper.news(base_date=today, pagesize=100, company_tickers=symbol)

    # Filtrar las noticias que fueron creadas en los últimos 'minutes_before' minutos
    news_list: List[News] = []

    for item in stories:
        created_time = item.get("created")
        
        # Convertir la fecha de creación a hora de Costa Rica
        created_time_obj = datetime.strptime(created_time, "%a, %d %b %Y %H:%M:%S %z")
        created_time_cr = created_time_obj.astimezone(CR_TIMEZONE).isoformat()
        
        # Verificar si la noticia fue creada dentro del rango de los últimos 'minutes_before' minutos
        if created_time_cr >= start_time_iso:
            hour, minute = extract_cr_hour_minute(created_time)
            stock_symbols = [stock.get("name") for stock in item.get("stocks", [])]

            news = News(
                id=item.get("id"),
                author=item.get("author"),
                created=created_time,
                created_hour_cr=hour,
                created_minute_cr=minute,
                title=item.get("title"),
                url=item.get("url"),
                stocks=stock_symbols
            )
            news_list.append(news)

    # Imprimir las noticias de los últimos 'minutes_before' minutos
    for idx, news in enumerate(news_list, start=1):
        print(f"News {idx}: hora: {news.created_hour_cr} minuto: {news.created_minute_cr} "
              f"Stocks: {', '.join(news.stocks) if news.stocks else 'N/A'}")

    # Finalizar el temporizador
    end_time = time.time()

    elapsed_time = end_time - start_time

    return news_list

def get_stocks_in_range(start_index, end_index, cursor):

    cursor.execute('''
        SELECT ticker, close, stock_index
        FROM Stocks
        WHERE stock_index BETWEEN ? AND ?
    ''', (start_index, end_index))

    rows = cursor.fetchall()

    tickers = [row[0] for row in rows]
    return tickers

def save_news_to_csv(news_list: List[News], ticker: str):
    # Guardar las noticias en el archivo obv.csv
    with open('obv.csv', mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # Escribir el encabezado si el archivo está vacío
        if file.tell() == 0:
            writer.writerow(["Ticker", "Title", "URL", "Created Time", "Created Hour", "Created Minute", "Stocks"])
        
        # Escribir las noticias en el archivo CSV
        for news in news_list:
            writer.writerow([ticker, news.title, news.url, news.created, news.created_hour_cr, news.created_minute_cr, ', '.join(news.stocks)])


def get_news_for_all_tickers(cursor, start_index, end_index, minutes_before=1020):

    tickers = get_stocks_in_range(start_index, end_index, cursor)
    print(f"Total tickers: {len(tickers)}")
    
    for ticker in tickers:
        news_list = get_news(ticker, minutes_before)

        if news_list:
            print(f"News for -> {ticker}.")
            print(f"\033[1;33mNews {ticker} \033[0m \033[1;33m -> NEWS Alert\033[0m")
            save_news_to_csv(news_list, ticker)
            # executor.submit(
            #     play_bell
            # )                                                                            

def play_bell():    
    playsound('piece-of-cake.mp3')    

def infinite_news_check():
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    start_index = 0
    end_index = 1710

    while True:
        print("Starting news check...")
    
        get_news_for_all_tickers(cursor, start_index, end_index)

        print("")
        print("")
        print("********************* Waiting 60 seconds before running again...\n")
        print("")
        print("")
        time.sleep(100000)

# infinite_news_check()

def format_benzinga_response(response_text):
    # Parsea la respuesta XML
    root = ET.fromstring(response_text)

    # Extrae las noticias
    news_items = root.findall('item')

    # Lista para almacenar las noticias formateadas
    formatted_news = []

    # Establece las zonas horarias
    ny_tz = pytz.timezone('US/Eastern')
    cr_tz = pytz.timezone('America/Costa_Rica')

    # Formatea cada noticia
    for item in news_items:
        news = {}
        news['Id'] = item.find('id').text
        news['Author'] = item.find('author').text

        # Convierte la fecha y hora
        created_str = item.find('created').text
        created_dt = datetime.strptime(created_str, '%a, %d %b %Y %H:%M:%S %z')  # Convierte a datetime con zona horaria
        created_dt_cr = created_dt.astimezone(cr_tz)  # Convierte a Costa Rica

        # Guarda la fecha y hora convertida
        news['Fecha y hora'] = created_dt_cr.strftime('%a, %d %b %Y %H:%M:%S %z')

        news['Titulo'] = item.find('title').text
        news['Link'] = item.find('url').text

        # Obtener los símbolos de las acciones asociadas
        stocks = [stock.text for stock in item.findall('.//stocks/item/name')]
        news['Stocks'] = ', '.join(stocks)

        # Obtener los canales asociados
        channels = [channel.text for channel in item.findall('.//channels/item/name')]
        news['Channels'] = ', '.join(channels)

        # Agrega a la lista de noticias formateadas
        formatted_news.append(news)

    # Devuelve la lista de noticias formateadas
    return formatted_news

def get_last_candle_close(symbol, date_value):
    # Obtener la hora actual en UTC
    current_time = datetime.utcnow()

    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)    

    aggs = client.list_aggs(symbol, 1, "minute", date_value, date_value, adjusted="true", sort="asc")
    
    aggs = list(aggs)
    
    if aggs:
        last_agg = aggs[-1]
        
        # print(f"Close: {last_agg.close}, Volume: {last_agg.volume}, VWAP: {last_agg.vwap}, Timestamp: {last_agg.timestamp}")
        return last_agg.close
    else:
        return {"error": "No data available for the last 10 minutes"}

def insert_benzinga_news_db(formatted_news, db_connection):
    cursor = db_connection.cursor()
    
    # Lista para almacenar los stocks insertados
    inserted_stocks = []

    for news in formatted_news:
        try:
            # Verificar si el new_id ya existe en la base de datos
            cursor.execute('''
                SELECT COUNT(*) FROM News WHERE new_id = ?
            ''', (news['Id'],))
            count = cursor.fetchone()[0]
            
            if count == 0:  # Si no existe, verificamos si los stocks están en la tabla Stocks
                # Extraer los stocks de la noticia (separados por coma)
                stocks = news['Stocks'].split(', ')  # Asumimos que los stocks están separados por coma y espacio
                
                # Verificar si al menos uno de los stocks existe en la tabla Stocks
                for stock in stocks:
                    cursor.execute('''
                        SELECT COUNT(*) FROM Stocks WHERE ticker = ?
                    ''', (stock,))
                    stock_exists = cursor.fetchone()[0]
                    
                    if stock_exists > 0:
                        # Si el stock existe en la tabla Stocks, insertamos la noticia
                        print(f"*******************************Inserting news: {news['Id']} - {news['Titulo']}")
                        cursor.execute('''
                            INSERT INTO News (new_id, title, date, link, stocks, timestamp, source)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (news['Id'], news['Titulo'], news['Fecha y hora'], news['Link'], news['Stocks'], print_current_time(), "benzinga"))
                        db_connection.commit()
                        
                        # Añadir los stocks a la lista de insertados
                        inserted_stocks.extend(stocks)  # Añadimos todos los stocks asociados a la noticia
                        print_current_time()
                        break  # Salimos del ciclo una vez que encontramos un stock válido

        except sqlite3.Error as e:
            print(f"Error al insertar noticia: {e}")
    
    # Retornar la lista de stocks que fueron insertados
    return inserted_stocks

def print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]

def insert_trade_signal_buy_news(conn, symbol, timestamp_buy, ask_price, last_trade_price):
    try:
        cursor = conn.cursor()

        query = """
        INSERT INTO TradeSignalsBuyNews (symbol, timestamp_buy, ask_price, last_trade_price)
        VALUES (?, ?, ?, ?)
        """
        cursor.execute(query, (symbol, timestamp_buy, ask_price, last_trade_price))

        conn.commit()
        print(f"✅ Registro insertado exitosamente {symbol}")
    except sqlite3.Error as e:
        print(f"❌ Error al insertar el registro: {e}")

def put_order_interactive_brokers(ib, symbol, ask_price):

    print("put_order_interactive_brokers *******")

    stock = Stock(symbol, 'SMART', 'USD')

    order = LimitOrder('BUY', 1, ask_price, outsideRth=True)

    trade = ib.placeOrder(stock, order)

    ib.sleep(2)

    print("Estado de la orden")
    print(trade.orderStatus.status)

def fetch_and_process_news():
    url = "https://api.benzinga.com/api/v2/news"
    querystring = {"token": "bz.4KCPALWSMP2MNWOIFFYEHANTDL7ANAMJ", "pageSize": "20", "displayOutput": "headline"}
    headers = {"accept": "<accept>"}

    conn = sqlite3.connect('histFinanData.db')

    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)

    polygon_client = RESTClient("RfayaUNTghp76By4a7GHbnAJuV2tZ99Y")

    ib = IB()
    # ib.connect('127.0.0.1', 7496, clientId=1)    

    while True:

        print("Fetching news...")
        response = requests.request("GET", url, headers=headers, params=querystring)

        formatted_news = format_benzinga_response(response.text)

        benzinga_inserted_stocks = insert_benzinga_news_db(formatted_news, conn)

        polygon_inserted_stocks = fetch_polygon_news(polygon_client, conn)    

        finnhub_client = finnhub.Client(api_key="d1aq0a1r01qjhvtqlbbgd1aq0a1r01qjhvtqlbc0")
        finnhub_inserted_stocks = save_finnhub_news_to_db(finnhub_client.general_news('general', min_id=0), conn)        

        # print("Benzinga inserted stocks:", benzinga_inserted_stocks)
        # print("Polygon inserted stocks:", polygon_inserted_stocks)
        # print("Finnhub inserted stocks:", finnhub_inserted_stocks)        

        final_inserted_stocks = benzinga_inserted_stocks + polygon_inserted_stocks + finnhub_inserted_stocks

        # Optionally remove duplicates if needed
        final_inserted_stocks = list(set(final_inserted_stocks))

        # Optionally, remove empty strings
        final_inserted_stocks = [stock for stock in final_inserted_stocks if stock]

        # Print the final list
        # print("Final merged stocks list:", final_inserted_stocks)

        for stock in final_inserted_stocks:

            today = datetime.now().strftime('%Y-%m-%d') 

            last_trade_close = client.get_last_trade(stock).price
            print("   ")
            print(f"Symbol: {stock}")
            print(f"Last Trade Close: {last_trade_close}")
            last_candle_close = get_last_candle_close(stock, today)
            # last_trade_close = 2.99
            print(f"Last Candle close: {last_candle_close}")
            print("   ")

            if isinstance(last_candle_close, (int, float)):

                price_difference = (last_trade_close - last_candle_close) / last_candle_close * 100
                print(f"Price difference for {stock}: {price_difference}")
                
                if price_difference >= 10:
                    print(f"El precio de {stock} ha subido más del 10% respecto al cierre de la vela anterior {price_difference}")

                    trade_signal_news_last_trade_close = client.get_last_trade(stock).price
                    trade_signal_news_ask_price = client.get_last_quote(stock).ask_price    

                    # put_order_interactive_brokers(ib, stock, trade_signal_news_ask_price)

                    insert_trade_signal_buy_news(conn, stock, print_current_time(), trade_signal_news_ask_price, trade_signal_news_last_trade_close)                                                 

                    #Aqui tenemos varias opciones. 
                    # 1. Podria registrar este symbolo en un WebSocket en agregaciones por segundo para Verificar aumentos de precio en tiempo real
                    # tambien deberia de acumular el volumen de operaciones para compararlo con el volumen de la vela anterior.
                    # 2. Esto presenta varios desafios ya que deberia suscribir y eliminar activos de un websoquet en tiempo real.
                    # 3. Pero si estop se confirma se podria emitir una alerta y a FUTURO llamar a Interactive Brokers  to BUY.

        print("END")
        print(" ")
        time.sleep(10)

    conn.close()        

def fetch_news():
    url = "https://finnhub.io/api/v1/news"
    querystring = {
        "token": "d1aq0a1r01qjhvtqlbbgd1aq0a1r01qjhvtqlbc0",
        "from": datetime.today().strftime('%Y-%m-%d'),  # Fecha de hoy
        "to": datetime.today().strftime('%Y-%m-%d'),  # Fecha de hoy
    }

    headers = {
        "accept": "application/json"
    }

    while True:
        print("Fetching news...")
        response = requests.get(url, headers=headers, params=querystring)

        print(f"Response status code: {response.status_code}")
        if response.status_code == 200:
            news_data = response.json()
            # print(news_data)
            for news_item in news_data:
                print(f"Headline: {news_item['headline']}")
                print(f"Date: {news_item['datetime']}")
                print(f"URL: {news_item['url']}")
                print("-" * 50)
        else:
            print(f"Failed to fetch news, status code: {response.status_code}")

        # Esperar 60 segundos antes de la siguiente consulta
        time.sleep(10)

def convert_to_cr_time(utc_time_str):
    # Convertir la fecha de UTC a un objeto datetime
    utc_time = datetime.strptime(utc_time_str, '%Y-%m-%dT%H:%M:%SZ')

    # Establecer la zona horaria de Costa Rica (UTC -6)
    cr_timezone = pytz.timezone('America/Costa_Rica')

    # Convertir el tiempo UTC a la hora local de Costa Rica
    cr_time = pytz.utc.localize(utc_time).astimezone(cr_timezone)

    # Regresar el tiempo en formato legible
    return cr_time.strftime('%Y-%m-%d %H:%M:%S')

def save_polygon_news_to_db(news_data, conn):
    cursor = conn.cursor()
    inserted_stocks = []

    for item in news_data:
        # Extraer valores
        new_id = item.id
        title = item.title
        date = item.published_utc
        link = item.article_url
        stocks = item.tickers  # Esta es una lista
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        source = "polygon"

        # Validar que al menos uno de los tickers exista en la tabla Stocks
        valid_stocks = []
        for ticker in stocks:
            cursor.execute("SELECT 1 FROM Stocks WHERE ticker = ?", (ticker,))
            if cursor.fetchone():
                valid_stocks.append(ticker)

        if not valid_stocks:
            # Saltar esta noticia si no hay ningún ticker válido
            continue

        # Verificar si ya existe en la base de datos
        cursor.execute("SELECT COUNT(*) FROM News WHERE new_id = ?", (new_id,))
        result = cursor.fetchone()

        if result[0] == 0:
            stocks_string = ", ".join(valid_stocks)
            cursor.execute('''
            INSERT INTO News (new_id, title, date, link, stocks, timestamp, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (new_id, title, date, link, stocks_string, timestamp, source))
            inserted_stocks.extend(valid_stocks)

    return inserted_stocks     

def fetch_polygon_news(polygon_client, conn):
    # Obtener la fecha de hoy en formato adecuado para la consulta
    today_date = datetime.today().strftime('%Y-%m-%d')

    news = []
    for n in polygon_client.list_ticker_news(
            published_utc=today_date,  # Usar la fecha dinámica de hoy
            order="desc",
            limit="10",
            sort="published_utc",
    ):
        news.append(n)

    return save_polygon_news_to_db(news, conn)

def save_finnhub_news_to_db(news_data, conn):

    cursor = conn.cursor()
    inserted_stocks = []

    for item in news_data:
        new_id = item['id']

        # Verificar si ya existe
        cursor.execute("SELECT 1 FROM News WHERE new_id = ?", (new_id,))
        if cursor.fetchone():
            continue  # Saltar si ya está guardada

        # Convertir fecha UNIX a string en hora de Costa Rica
        utc_dt = datetime.utcfromtimestamp(item['datetime']).replace(tzinfo=pytz.utc)
        cr_time = utc_dt.astimezone(pytz.timezone('America/Costa_Rica')).strftime('%Y-%m-%d %H:%M:%S')

        title = item['headline']
        link = item['url']
        stocks = item.get('related', '') or ''
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Insertar la noticia
        cursor.execute('''
            INSERT INTO News (new_id, title, date, link, stocks, timestamp, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (new_id, title, cr_time, link, stocks, timestamp, "finnhub"))
        stocks_list = [symbol.strip() for symbol in stocks.split(',')]
        inserted_stocks.extend(stocks_list)        

    conn.commit()
    return inserted_stocks

fetch_and_process_news()