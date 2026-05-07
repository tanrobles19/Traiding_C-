import polygon
import asyncio
from polygon import RESTClient
import pandas as pd
import sqlite3
import pytz
import time
import random
from datetime import datetime, timezone

from zoneinfo import ZoneInfo  # Requiere Python 3.9+
from real_time_position_manager import sellStock
from ib_insync import IB, Stock


def get_Historical_Data_by_Trades2(year, month, day, hour, minute, symbol):

    print(" ")
    print("History by Second")
    print(" ")

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()
    
    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)

    cursor.execute(f"SELECT ticker FROM Stocks WHERE ticker = '{symbol}'")
    tickers = cursor.fetchall()
    
    print(f"Retrieved {len(tickers)} stocks.")

    total_data_count = 0
    stock_counter = 1



    for (ticker,) in tickers:
        aggregates = []
        
        print(f"Processing stock {ticker}...")
        trades = []

        # dt = datetime(2025, 11, 20, 7, 00, 0)
        dt = datetime(year, month, day, hour, minute, 0)        
        start_ns = int(dt.timestamp() * 1_000_000_000)
        end_ns = start_ns + 60_000_000_000  # Add 59 seconds

        init_date = "2025-12-04"
        end_date = "2025-12-04"


        print(start_ns)
        print(end_ns)

        for t in client.list_trades(
            ticker="KALA", 
            timestamp="2025-12-04", 
            limit=50000):        

            ns_timestamp = t.participant_timestamp

            seconds = ns_timestamp / 1e9        
            dt_utc = datetime.fromtimestamp(seconds, tz=timezone.utc)

            import pytz
            costa_rica_tz = pytz.timezone("America/Costa_Rica")
            dt_local = dt_utc.astimezone(costa_rica_tz)
            # print(t)
            # print(dt_local)

            aggregates.append({
                "price": t.price,
                "size": t.size,
                "timestamp": dt_local,
                "unix_timestamp": t.participant_timestamp,
                "conditions": t.conditions,
                "trade_id": t.id,
                "exchange": t.exchange,
                "trf_id": t.trf_id
            })

    storeTrades2(conn, cursor, aggregates, symbol)

def get_second(time_str):
    parts = time_str.split(":")
    seconds = parts[2].split(".")[0]
    return int(seconds)


def storeTrades2(conn, cursor, aggregates, ticker):
    print(len(aggregates))     

    total_data_count = 0
    stock_counter = 1          

    df = pd.DataFrame(aggregates)

    cursor.execute('BEGIN TRANSACTION')

    print("Storing....")
    for i, (index, row) in enumerate(df.iterrows(), 1):

        date, hour, minute, second, milliseconds, am_pm = "N/A", "00", "00", "00", "000", "AM"

        conds = row.get("conditions") or []
        conditions_str = ", ".join(map(str, conds)) if conds else "None"

        timestamp_str = row['timestamp'].isoformat()        

        # print(row['timestamp'])
        
        exchange = row['exchange']

        if not row['exchange']:
            exchange = "N/A"

        cursor.execute('''
            INSERT INTO RawTrades(symbol, close, volume, date, hour, minute, second, amPm, transactions, timestamp, conditions, trade_id, exchange, trf_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ticker, row['price'], row['size'], date, hour, minute, row['timestamp'].second, am_pm, row['unix_timestamp'], timestamp_str, conditions_str, row['trade_id'], row['exchange'], row['trf_id']))    

    conn.commit()

    total_data_count += len(df)
    
    print(f"{stock_counter}. Saved stock {ticker} with {len(df)} aggregates")
    stock_counter += 1

    conn.close()

    print(f"Total data points saved in HistoryByMin: {total_data_count}") 


def convert_timestamp_to_costa_rica_time(timestamp):
    # Convertir el timestamp (float) a un objeto datetime en UTC
    utc_time = datetime.fromtimestamp(timestamp, pytz.utc)
    
    # Definir la zona horaria de Costa Rica
    costa_rica_tz = pytz.timezone('America/Costa_Rica')

    # Convertir la hora UTC a la hora local de Costa Rica
    local_time = utc_time.astimezone(costa_rica_tz)

    # Formatear la hora incluyendo horas, minutos, segundos y milisegundos
    formatted_time = local_time.strftime("%H:%M:%S") + f":{local_time.microsecond // 1000:03d}"
    
    return formatted_time


def print_current_time_costa_rica_hour_minute():

    utc_time = datetime.now(pytz.utc)

    costa_rica_tz = pytz.timezone('America/Costa_Rica')

    local_time = utc_time.astimezone(costa_rica_tz)

    formatted_time = local_time.strftime("%H:%M")
    
    return formatted_time       


def convert_ns_to_central_time(timestamp_ns):
    timestamp_sec = timestamp_ns / 1_000_000_000

    dt_utc = datetime.fromtimestamp(timestamp_sec, tz=ZoneInfo("UTC"))

    dt_central = dt_utc.astimezone(ZoneInfo("America/Costa_Rica"))

    tz_abbr = dt_central.tzname()

    human = dt_central.strftime('%H:%M:%S.%f')[:-3]

    return f"{human}"
    # return f"{human} {tz_abbr}"    

def print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]

def get_hour_from_timestamp(start_timestamp):
    start_timestamp_seconds = start_timestamp / 1000
    
    start_time_utc = datetime.utcfromtimestamp(start_timestamp_seconds)
    
    cr_tz = pytz.timezone("America/Costa_Rica")
    start_time_cr = start_time_utc.replace(tzinfo=pytz.utc).astimezone(cr_tz)
    
    return int(start_time_cr.strftime("%I"))    

def convert_timestamp_to_timeT(timestamp):
    timestamp_seconds = timestamp / 1000000000.0  # Nanosegundos a segundos
    
    # Convertir a datetime (en UTC)
    dt = datetime.utcfromtimestamp(timestamp_seconds)
    
    # Extraer hora y minuto (en formato UTC)
    hour = dt.strftime('%H')  # Hora en formato 24 horas
    minute = dt.strftime('%M')  # Minuto
    
    return hour, minute

def get_current_positions(ib, real_time_positions):
    positions = ib.positions()
    
    for pos in positions:

        symbol = pos.contract.symbol
        avg_cost = pos.avgCost
        
        real_time_positions[symbol] = avg_cost
        
    print("Posiciones actuales en el hash:")
    print(real_time_positions)

def convert_utc_to_cr_time2(timestamp):
    # Verificar si el timestamp está en nanosegundos (19 dígitos)
    print("Original timestamp:", timestamp)
    if len(str(timestamp)) == 19:
        timestamp_seconds = timestamp / 1000000000.0  # Convertir nanosegundos a segundos
        print("Converted to seconds (nanoseconds):", timestamp_seconds)
    else:
        timestamp_seconds = timestamp / 1000.0  # Si está en milisegundos, usar la conversión normal
    
    # Obtener la zona horaria UTC y Costa Rica
    utc_zone = pytz.utc
    cr_zone = pytz.timezone('America/Costa_Rica')

    try:
        # Convertir el timestamp a datetime con zona horaria UTC
        dt_utc = datetime.utcfromtimestamp(timestamp_seconds).replace(tzinfo=utc_zone)
    except ValueError as e:
        print("Error:", e)
        return None
    
    # Convertir de UTC a Costa Rica
    dt_cr = dt_utc.astimezone(cr_zone)

    # Obtener los valores de fecha, hora, minuto, segundo, milisegundos y AM/PM
    date = dt_cr.strftime('%b %d, %Y')  # May 20, 2025
    hour = dt_cr.strftime('%I')  # 01
    minute = dt_cr.strftime('%M')  # 18
    second = dt_cr.strftime('%S') 
    am_pm = dt_cr.strftime('%p')  # AM/PM
    
    # Milisegundos se calculan usando los microsegundos
    milliseconds = dt_cr.microsecond // 1000  # Extraer los milisegundos de los microsegundos

    return date, hour, minute, second, milliseconds, am_pm  

def convert_utc_to_cr_time(timestamp):
    # Convertir milisegundos a segundos
    timestamp_seconds = timestamp / 1000.0
    
    # Obtener la zona horaria UTC y Costa Rica
    utc_zone = pytz.utc
    cr_zone = pytz.timezone('America/Costa_Rica')

    # Convertir el timestamp a datetime con zona horaria UTC
    dt_utc = datetime.utcfromtimestamp(timestamp_seconds).replace(tzinfo=utc_zone)
    
    # Convertir de UTC a Costa Rica
    dt_cr = dt_utc.astimezone(cr_zone)

    # Obtener los valores de fecha, hora, minuto, segundo, milisegundos y AM/PM
    date = dt_cr.strftime('%b %d, %Y')  # May 20, 2025
    hour = dt_cr.strftime('%I')  # 01
    minute = dt_cr.strftime('%M')  # 18
    second = dt_cr.strftime('%S') 
    am_pm = dt_cr.strftime('%p')  # AM/PM
    
    # Milisegundos se calculan usando los microsegundos
    milliseconds = dt_cr.microsecond // 1000  # Extraer los milisegundos de los microsegundos

    return date, hour, minute, second, milliseconds, am_pm  

def hour_min_sec_from_ns(ns: int, tz_name: str = "UTC"):
    # ns -> segundos enteros + resto en ns (evita errores por float)
    sec, ns_rem = divmod(int(ns), 1_000_000_000)
    dt = datetime.fromtimestamp(sec, tz=timezone.utc) + timedelta(microseconds=ns_rem // 1000)
    if tz_name and tz_name != "UTC":
        dt = dt.astimezone(pytz.timezone(tz_name))  # p.ej. "America/Costa_Rica"
    return dt.strftime("%H"), dt.strftime("%M"), dt.strftime("%S")

def get_last_trade(symbol):

    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)

    last_trade_price = client.get_last_trade(symbol)

    return last_trade_price


def get_Historical_Data_by_Trades(year, month, day, hour, minute, symbol):

    print(" ")
    print("History by Second")
    print(" ")

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()
    
    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)

    cursor.execute(f"SELECT ticker FROM Stocks WHERE ticker = '{symbol}'")
    tickers = cursor.fetchall()
    
    print(f"Retrieved {len(tickers)} stocks.")

    total_data_count = 0
    stock_counter = 1

    for (ticker,) in tickers:
        aggregates = []
        
        # print(f"Processing stock {ticker}...")
        trades = []

        # dt = datetime(2025, 11, 20, 7, 00, 0)
        dt = datetime(year, month, day, hour, minute, 0)        
        start_ns = int(dt.timestamp() * 1_000_000_000)
        end_ns = start_ns + 60_000_000_000  # Add 59 seconds

        print(start_ns)
        print(end_ns)

        for t in client.list_trades(
            ticker=ticker,
            timestamp_gte=start_ns,
            timestamp_lte=end_ns,
            order="asc",
            limit=10,
            sort="timestamp",
        ):        

            ns_timestamp = t.participant_timestamp

            seconds = ns_timestamp / 1e9        
            dt_utc = datetime.fromtimestamp(seconds, tz=timezone.utc)

            import pytz
            costa_rica_tz = pytz.timezone("America/Costa_Rica")
            dt_local = dt_utc.astimezone(costa_rica_tz)
            print(t)
            # print(dt_local)

            aggregates.append({
                "price": t.price,
                "size": t.size,
                "timestamp": dt_local,
                "unix_timestamp": t.participant_timestamp,
                "conditions": t.conditions,
                "trade_id": t.id,
                "exchange": t.exchange,
                "trf_id": t.trf_id
            })
    storeTrades(conn, cursor, aggregates, symbol)

def get_second(time_str):
    parts = time_str.split(":")
    seconds = parts[2].split(".")[0]
    return int(seconds)


def storeTrades(conn, cursor, aggregates, ticker):
    print(len(aggregates))     

    total_data_count = 0
    stock_counter = 1          

    df = pd.DataFrame(aggregates)

    cursor.execute('BEGIN TRANSACTION')

    print("Storing....")
    for i, (index, row) in enumerate(df.iterrows(), 1):

        date, hour, minute, second, milliseconds, am_pm = "N/A", "00", "00", "00", "000", "AM"

        conds = row.get("conditions") or []
        conditions_str = ", ".join(map(str, conds)) if conds else "None"

        timestamp_str = row['timestamp'].isoformat()        

        print(row['timestamp'])
        

        exchange = row['exchange']

        if not row['exchange']:
            exchange = "N/A"

        cursor.execute('''
            INSERT INTO RawTrades(symbol, close, volume, date, hour, minute, second, amPm, transactions, timestamp, conditions, trade_id, exchange, trf_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ticker, row['price'], row['size'], date, hour, minute, row['timestamp'].second, am_pm, row['unix_timestamp'], timestamp_str, conditions_str, row['trade_id'], row['exchange'], row['trf_id']))    

    conn.commit()

    total_data_count += len(df)
    
    print(f"{stock_counter}. Saved stock {ticker} with {len(df)} aggregates")
    stock_counter += 1

    conn.close()

    print(f"Total data points saved in HistoryByMin: {total_data_count}")      


def get_Historical_Data_by_Second(init_date, end_date, symbol):

    print(" ")
    print("History by Second")
    print(" ")

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()
    
    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)

    cursor.execute(f"SELECT ticker FROM Stocks WHERE ticker = '{symbol}'")
    tickers = cursor.fetchall()
    
    print(f"Retrieved {len(tickers)} stocks.")

    total_data_count = 0
    stock_counter = 1

    for (ticker,) in tickers:
        aggregates = []
        
        print(f"Processing stock {ticker}...")

        for a in client.list_aggs(
            ticker,
            1,
            "second",
            init_date,
            end_date,            
            adjusted="true",
            sort="asc",
            limit=120,
        ):
            aggregates.append({
                "timestamp": a.timestamp,
                "close": a.open,
                "volume": a.volume,
                "transactions": a.transactions,
                "vwap": a.vwap
            })
            print(a)

        df = pd.DataFrame(aggregates)

        cursor.execute('BEGIN TRANSACTION')

        print("Storing....")
        for i, (index, row) in enumerate(df.iterrows(), 1):

            date, hour, minute, second, milliseconds, am_pm = convert_utc_to_cr_time(row['timestamp'])
            
            timestamp = str(hour) + ":" + str(minute)+ ":" + str(second)+ ":" + str(milliseconds)

            cursor.execute('''
                INSERT INTO AggregatesBySecondExperiment(symbol, close, volume, date, hour, minute, second, amPm, timestamp, transactions, vwap) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ticker, row['close'], row['volume'], date, hour, minute, second, am_pm, timestamp, row['transactions'], row['vwap']))    

        conn.commit()

        total_data_count += len(df)
        
        print(f"{stock_counter}. Saved stock {ticker} with {len(df)} aggregates")
        stock_counter += 1

    conn.close()

    print(f"Total data points saved in HistoryByMin: {total_data_count}")

async def reduce_position():

    PAPER_PORT = 7497
    ib = IB()
    await ib.connectAsync('127.0.0.1', PAPER_PORT, clientId=0)

    real_time_positions = {}
    get_current_positions(ib, real_time_positions)

    print(real_time_positions)

    positions = ib.positions()
    positionSize = 0

    for pos in positions:
        if pos.contract.symbol == "MOVE":
            positionSize = int(pos.position)
            break

    if positionSize == 0:
        return    

    bot_price = real_time_positions['MOVE']
    print(f"bot price = {bot_price}")
    print(f"position Size = {positionSize}")

    while positionSize > 0:
        print(f"Current position size: {positionSize}")
        
        quantity_to_sell = await sellStock(ib, "MOVE", real_time_positions, 1.40, bot_price, positionSize)
        positionSize -= quantity_to_sell        

        sleep_time = random.randint(1, 5)
        print(f"Sleeping for {sleep_time} seconds...\n")
        time.sleep(sleep_time)
    print("Position size reached 0.")    
    
    ib.disconnect()    

# asyncio.run(reduce_position())

init_date = "2025-11-19"
end_date = "2025-11-19"

print("Starting get_Historical_Data_by_Second....")

# get_Historical_Data_by_Second(init_date, end_date, "SEMR")

# SELECT 
#     COUNT(DISTINCT second) AS distinct_seconds
# FROM 
#     RawTrades
# WHERE 
# 	minute = 0
#     AND symbol = "SLE";

# get_Historical_Data_by_Trades(2025, 10, 15, 6, 00, "IBG")    


def format_unix_timestamp(timestamp_ms):

    timestamp_s = timestamp_ms / 1000.0
    
    current_time = datetime.utcfromtimestamp(timestamp_s)
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")
    
    return formatted_time[:-3] 

# print(format_unix_timestamp(1759326780000))

# DURACION = 60  

# inicio = time.time()  # Tiempo inicial
# contador = 0          # Contador de iteraciones

# # Bucle que corre hasta completar 60 segundos
# while time.time() - inicio < DURACION:
#     contador += 1
#     # print(f"Iteración número: {contador}")

# print(f"\nTotal de iteraciones en {DURACION} segundos: {contador}")



# from ib_insync import *
# import pandas as pd

# # Conexión al TWS o IB Gateway
# ib = IB()
# ib.connect('127.0.0.1', 7497, clientId=1)

# # Definí el contrato
# stock = Stock('MVST', 'SMART', 'USD')

# # Pedí las velas de 1 minuto del 7 de octubre de 2024
# bars = ib.reqHistoricalData(
#     stock,
#     endDateTime='20251008 11:00:00',
#     durationStr='1 D',
#     barSizeSetting='1 min',
#     whatToShow='TRADES',
#     useRTH=False   # ⚠️ muy importante
# )

# # Convertí a DataFrame
# df = util.df(bars)

# # Guardá en CSV
# output_file = 'ACXP_1min_20241007.csv'
# df.to_csv(output_file, index=False)

# print(f'Datos guardados en: {output_file}')
# print(df.head())


get_Historical_Data_by_Trades(2026, 1, 26, 15, 10, "PHGE")


api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
client = RESTClient(api_key)


# init_time = time.perf_counter()

# quote = client.get_last_quote("TSLA")

# ask_timestamp = "1761235865389"

# ask_price = quote.ask_price
# bid_price = quote.bid_price



# end_time = time.perf_counter()

# tiempo_ms = (end_time - init_time) * 1000
# print(f"Tiempo transcurrido: {tiempo_ms:.2f} ms")

# init_time = time.perf_counter()   

# # print_current_time_costa_rica_hour_minute()

# # timestamp = int(time.time())

# # print(convert_timestamp_to_costa_rica_time(1764199482.017103))
# # print(convert_timestamp_to_costa_rica_time(1764199482.10462))

# end_time = time.perf_counter()
# time_us = (end_time - init_time) * 1000000 
# print(f"Time measured: {time_us:.3f} μs")
# # print(timestamp)


# from polygon import RESTClient

# Create client with your API key
# client = RESTClient(api_key="<API_KEY>")

# ticker = "TSLA"

# # Get Last Trade (most recent transaction price)
# trade = client.get_last_trade(ticker=ticker)
# print(trade.price)

# Get Last Quote (current bid/ask prices)
# quote = client.get_last_quote(ticker=ticker)
# print(quote)
