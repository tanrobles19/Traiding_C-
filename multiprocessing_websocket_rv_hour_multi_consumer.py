from polygon import WebSocketClient
import random
from polygon import RESTClient
from ib_insync import IB, Stock
from ib_insync.order import LimitOrder
import time
from typing import List
import asyncio
import time
import csv
import aiosqlite
from datetime import datetime, timedelta, date, timezone
import pytz
from ib_insync import util
import psutil
import multiprocessing
import os
import time
import sqlite3
import mysql.connector  

from queue import Queue
from multiprocessing import Lock

from real_time_position_manager import check_and_alert_loss
from real_time_position_manager import check_and_take_profits
from datetime import datetime
import pytz

trade_lock = Lock()
trade_lock2 = Lock()


class WebSocketMessage:
    def __init__(self, symbol: str, price: float, size: int):
        self.symbol = symbol
        self.price = price
        self.size = size

class WSClient:
    async def connect(self, on_messages):
        # Aquí va tu implementación real que llama:
        # await on_messages(List[WebSocketMessage])
        pass

def mi_manejador_de_error(ws, error):
    print("Error del WebSocket:", error)

def mi_manejador_de_cierre(ws):
    print("Conexión WebSocket cerrada")

def mi_manejador_de_mensaje(message):
    print("Mensaje recibido:", message)

def get_average_volume_limit(symbol):

    db_connection = mysql.connector.connect(
        host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
        port=3306,
        user="admin",  
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()      

    query = f"""
    SELECT volume, timestamp
    FROM minute_candlesticks
    WHERE stock_symbol = %s
    ORDER BY timestamp DESC
    LIMIT 10;
    """
    
    mysql_cursor.execute(query, (symbol,))
    
    volumes = mysql_cursor.fetchall()

    volume_values = [v[0] for v in volumes]

    if all(v == 0 for v in volume_values):        
        mysql_cursor.close()
        db_connection.close()                
        return -1

    # print(f"symbol = {symbol}")
    # print("Volumes fetched for average calculation:", volumes)
        
    max_volume = max(volume[0] for volume in volumes)

    # print(f"symbol = {symbol}")
    # print("Volumes fetched:", volumes)
    # print(f"Largest volume: {max_volume}")

    mysql_cursor.close()
    db_connection.close()        
    
    return max_volume

def get_news(ib, newsProviders, symbol, tradeSignalId, news_time_window_minutes):

    codes = '+'.join(np.code for np in newsProviders)

    amd = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(amd)

    now = datetime.now()
    start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt   = now

    # Formatear según lo que acepta IB API: “yyyyMMdd HH:mm:ss” con zona horaria opcional
    start_str = start_dt.strftime('%Y%m%d %H:%M:%S')
    end_str   = end_dt.strftime('%Y%m%d %H:%M:%S')

    # print("Requesting news from", start_str, "to", end_str)

    # print(f"Checking news for {symbol}...")


    headlines = ib.reqHistoricalNews(amd.conId, codes, start_str, end_str, 3)

    if not headlines:
        return 0, None

    newsCount = 0
    first_title = None

    today = datetime.now().date()

    # print(f"headlines fetched: {len(headlines)}")

    for headline in headlines:
        
        headline_date = headline.time.date()    
        # print(headline)    
        
        if headline_date == today:

            now_utc = datetime.now(timezone.utc)
            headline_time_utc = headline.time.replace(tzinfo=timezone.utc)

            delta = now_utc - headline_time_utc

            if delta <= timedelta(minutes=news_time_window_minutes):                

                formatted_time = headline_time_utc.strftime('%Y-%m-%d %H:%M:%S')
                # print("")
                # print(f"\n[NOTICIA RECIENTE] Fecha (UTC): {formatted_time}")
                # print(f"Proveedor: {headline.providerCode}")
                # print(f"Titular {symbol}: {headline.headline}")
                # print("")

                if first_title is None:
                    first_title = headline.headline                

                newsCount += 1

    return newsCount, first_title    

def update_newsCount(conn, cursor, tradeSignalID, symbol, newsCount, first_title, attempts_count):

    print("update_newsCount......")

    cursor.execute("""
        SELECT `newsCount` FROM TradeSignalsBuyPerSecond
        WHERE symbol = %s
    """, (symbol,))

    rows = cursor.fetchall()

    if not rows:
        raise ValueError(f"No se encontraron registros con el símbolo '{symbol}'.")

    for row in rows:
        if row[0] is not None:
            return True

    cursor.execute("""
        UPDATE TradeSignalsBuyPerSecond
        SET newsCount = %s, 
            attempts_count = %s,
            news_metadata = %s,
            timestamp_news = %s
        WHERE id = %s AND symbol = %s
        
    """, (newsCount, attempts_count, first_title, print_current_time_costa_rica(), tradeSignalID, symbol))

    conn.commit()
    return False     

def format_number(number):
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    elif number >= 1_000:
        return f"{number / 1_000:.1f}K"
    else:
        return str(number)    

def print_current_time_costa_rica():

    utc_time = datetime.now(pytz.utc)

    costa_rica_tz = pytz.timezone('America/Costa_Rica')

    local_time = utc_time.astimezone(costa_rica_tz)

    formatted_time = local_time.strftime("%H:%M:%S:%f")
    return formatted_time[:-3]     

def print_current_time_costa_rica_hour_minute():

    utc_time = datetime.now(pytz.utc)

    costa_rica_tz = pytz.timezone('America/Costa_Rica')

    local_time = utc_time.astimezone(costa_rica_tz)

    formatted_time = local_time.strftime("%H:%M")
    
    return formatted_time       

def get_current_positions(ib, real_time_positions):
    positions = ib.positions()
    
    for pos in positions:

        symbol = pos.contract.symbol
        avg_cost = pos.avgCost
        
        real_time_positions[symbol] = avg_cost  

def query_stock_float_short_interest(symbol):

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()   

    query = """
    SELECT float, short_percent_float
    FROM Stocks
    WHERE ticker = ?
    """    

    cursor.execute(query, (symbol, ))

    result = cursor.fetchone()

    conn.close()

    if result:
        return {'float': result[0], 'short_percent_float': result[1]}
    else:
        return None                     

def save_order_to_db(symbol, start_timestamp, avgFillPrice, status, tradeLog, orderType, totalQuantity, trade_signals_count, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_map_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close, active_seconds_count):    

    db_connection = mysql.connector.connect(
        host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
        port=3306,
        user="admin",  
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()      

    mysql_cursor.execute('''
        INSERT INTO Orders (`symbol`, `end_timestamp`, `start_timestamp`, `filledPrice`, `status`, `log`, `orderType`, `totalQuantity`, `tradeSignalsCount`, `ask_price`, `ask_timestamp`, `ask_size`, `bid_price`, `bid_size`, `open_price`, `open_timestamp`, `last_trade_price`, `last_trade_timestamp`, `polygon_second_close`, `active_seconds_count`)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (symbol, print_current_time_costa_rica(), start_timestamp, avgFillPrice, status,  str(tradeLog), orderType, totalQuantity, trade_signals_count, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_map_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close, active_seconds_count))

    db_connection.commit()    

    mysql_cursor.close()
    db_connection.close()        


def format_unix_timestamp(timestamp_ms):

    timestamp_s = timestamp_ms / 1000.0
    
    current_time = datetime.utcfromtimestamp(timestamp_s)
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")
    
    return formatted_time[:-3]     
    
def determine_purchase_quantity(investment_amount: float, price_per_share: float) -> int:

    #Determines the number of shares that can be purchased given a certain capital and the current price per share.
    #Returns the maximum whole number of shares that can be bought. If the price per share is zero or negative, returns 0.

    if price_per_share <= 0:
        return 0  
    shares = int(investment_amount // price_per_share)
    return shares    

def get_average_volume(mysql_cursor, stock_id) -> int:
    
    mysql_cursor.execute('''
        SELECT volume
        FROM AggregatesByMin
        WHERE stockID = %s
    ''', (stock_id,))
    
    rows = mysql_cursor.fetchall()
    
    if rows:
        total_volume = sum(row[0] for row in rows)
        average_volume = total_volume // len(rows)
    else:
        average_volume = 0
        
    return average_volume   

def query_all_stock_floats(mysql_cursor):
    stocks_dict = {}

    query = """
    SELECT ticker, float_value
    FROM Stocks
    """

    mysql_cursor.execute(query)
    rows = mysql_cursor.fetchall()

    stocks_dict = {row[0]: row[1] for row in rows if row[1] is not None}

    return stocks_dict 

def get_stocks_in_range(mysql_cursor, float_limit, min_price, max_price):
    mysql_cursor.execute('''
        SELECT ticker, close, stock_index
        FROM Stocks
        WHERE float_value < %s
        AND close > %s 
        AND close < %s
    ''', (float_limit, min_price, max_price))

    rows = mysql_cursor.fetchall()

    tickers = [row[0] for row in rows]
    return tickers

def has_existing_trade_signal_with_News(mysql_cursor, symbol):
    mysql_cursor.execute('''
        SELECT COUNT(*) FROM TradeSignalsBuyPerSecond
        WHERE symbol = %s AND purchasePrediction = 'BUY'
    ''', (symbol,))
    
    result = mysql_cursor.fetchone()

    if result[0] == 0:
        return False 
    return True 

def order_exists(mysql_cursor, symbol: str, status: str, order_type: str) -> bool:
    query = """
        SELECT 1
        FROM Orders
        WHERE symbol = %s AND status = %s AND orderType = %s
        LIMIT 1
    """
    mysql_cursor.execute(query, (symbol, status, order_type))
    return mysql_cursor.fetchone() is not None

def get_record_count_for_symbol(mysql_cursor, symbol):
    mysql_cursor.execute('''
        SELECT COUNT(*) FROM TradeSignalsBuyPerSecond WHERE symbol = %s
    ''', (symbol,))

    row = mysql_cursor.fetchone()
    record_count = row[0] if row else 0

    return record_count    

def has_no_recent_trade_signal(mysql_cursor, symbol, close, relative_volume, stale_threshold_minutes):

    query = """
    SELECT `timestamp`, `close`, `relative_volume`
    FROM `TradeSignalsBuyPerSecond`
    WHERE `symbol` = %s
    ORDER BY `timestamp` DESC
    LIMIT 1
    """
    mysql_cursor.execute(query, (symbol,))
    
    result = mysql_cursor.fetchone()
    
    if result is None:
        return True
    
    last_timestamp = result[0]
    
    today_date = datetime.today().date()
    last_time = datetime.strptime(last_timestamp, '%H:%M:%S:%f')
    last_time = last_time.replace(year=today_date.year, month=today_date.month, day=today_date.day)
    
    current_time = datetime.now()
    
    time_diff = current_time - last_time    
    
    if time_diff > timedelta(minutes=stale_threshold_minutes):
        return True
    else:
        return False      

def initial_config(version_code, port, investment_amount, low_float_stocks, symbols, positions, relative_volume, relative_volume_low_float, min_price, max_price, low_float, high_short_interest_stocks, SHORT_INTEREST_RATIO, INCREASE_FROM_OPEN, MAX_LOSS_TOLERANCE_PER_TRADE, PRICE_SPIKE_RISK_THRESHOLD):

    if port == 7497 or port == 4002:
        print(" ")
        print(f"\033[1;33m-------------------------------------------------------------- \033[0m")          
        print(f"\033[1;33m|                        Paper Trading {version_code}                | \033[0m")          
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"\033[1;33m|\033[0m High Short-Interest Stocks: {len(high_short_interest_stocks)}                             \033[1;33m|\033[0m")     
        print(f"\033[1;33m|\033[0m Short Interest Radio      : {SHORT_INTEREST_RATIO}                           \033[1;33m|\033[0m")             
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Low Float Stocks: {low_float_stocks}")       
        print(f"  Low Float: {format_number(low_float)}")
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Relative Volume           : {relative_volume}x")       
        print(f"  Relative Volume Low Float : {relative_volume_low_float}x")       
        print(f"  Price range               : [${min_price} - ${max_price}]")         
        # print(f"  Capital per Trade         : ${investment_amount}") 
        print(f"  Capital per Trade         : \033[1;31m${investment_amount}\033[0m")

        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Risk Management Config:")                             
        print(f"  Minimum from Open      : {INCREASE_FROM_OPEN}%")                             
        print(f"  Maximum Price Spike    : {PRICE_SPIKE_RISK_THRESHOLD}%")                                             
        print(f"  Maximum Loss tolerance : {MAX_LOSS_TOLERANCE_PER_TRADE}%")                                             
                
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")             
        print(f"  Symbols: {symbols}")
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Positions:")
        print(f" {positions}")        
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Time = {print_current_time_costa_rica()}")
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"\033[1;33m-------------------------------------------------------------- \033[0m")          
        print(" ")

    if port == 7496 or port == 4001:

        print(" ")
        print(f"\033[1;31m-------------------------------------------------------------- \033[0m")          
        print(f"\033[1;31m|                        Live Trading {version_code}                | \033[0m")          
        print(f"\033[1;31m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"\033[1;31m|\033[0m High Short-Interest Stocks: {len(high_short_interest_stocks)}                             \033[1;33m|\033[0m")     
        print(f"\033[1;31m|\033[0m Short Interest Radio      : {SHORT_INTEREST_RATIO}                           \033[1;33m|\033[0m")             
        print(f"\033[1;31m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Low Float Stocks: {low_float_stocks}")       
        print(f"  Low Float: {format_number(low_float)}")
        print(f"\033[1;31m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Relative Volume           : {relative_volume}x")       
        print(f"  Relative Volume Low Float : {relative_volume_low_float}x")       
        print(f"  Price range               : [${min_price} - ${max_price}]")         
        # print(f"  Capital per Trade         : ${investment_amount}")   
        print(f"  Capital per Trade         : \033[1;31m${investment_amount}\033[0m")

        print(f"\033[1;31m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Risk Management Config:")                             
        print(f"  Minimum from Open      : {INCREASE_FROM_OPEN}%")                             
        print(f"  Maximum Price Spike    : {PRICE_SPIKE_RISK_THRESHOLD}%")                                             
        print(f"  Maximum Loss tolerance : {MAX_LOSS_TOLERANCE_PER_TRADE}%")                                             
                
        print(f"\033[1;31m|\033[0m                                                            \033[1;33m|\033[0m")             
        print(f"  Symbols: {symbols}")
        print(f"\033[1;31m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Positions:")
        print(f" {positions}")        
        print(f"\033[1;31m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Time = {print_current_time_costa_rica()}")
        print(f"\033[1;31m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"\033[1;31m-------------------------------------------------------------- \033[0m")          
        print(" ")        

def get_filtered_stocks_short(mysql_cursor, max_float, min_short_percent, min_close, max_close):
    
    query = """
        SELECT ticker, close
        FROM Stocks
        WHERE float_value < %s
          AND short_percent_float > %s
          AND `close` BETWEEN %s AND %s;
    """
    
    mysql_cursor.execute(query, (max_float, min_short_percent, min_close, max_close))
    results = mysql_cursor.fetchall()
    
    stocks_dict = {row[0]: row[1] for row in results}
    
    return stocks_dict   

def get_low_float_stocks(mysql_cursor, max_float, min_close, max_close):

    query = """
        SELECT * FROM Stocks
        WHERE float_value < %s
          AND close >= %s
          AND close <= %s
        ORDER BY close ASC
    """
    mysql_cursor.execute(query, (max_float, min_close, max_close))
    rows = mysql_cursor.fetchall()

    columns = ["ticker", "close", "stock_index", "avg_month_volume", "shares_outstanding", "float_value"]

    result = {row[0]: row[5] for row in rows}
    return result

def print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]

def get_relative_volume(hour, minute, am_pm, mysql_cursor):

    mysql_cursor.execute('''
        SELECT `symbol`, `relative_volume`
        FROM `RelativeVolumeRatio`
        WHERE `hour` = %s 
        AND `minute` = %s
        AND `amPm` = %s
    ''', (hour, minute, am_pm))

    rows = mysql_cursor.fetchall()
    relative_volume_list_hashmap = {row[0]: row[1] for row in rows}
    return relative_volume_list_hashmap

def get_relative_volume_hour(hour, am_pm, mysql_cursor):

    mysql_cursor.execute('''
        SELECT `symbol`, `relative_volume`
            FROM RelativeVolumeRatioHour
                WHERE hour = %s 
                AND amPm = %s
    ''', (hour, am_pm))

    rows = mysql_cursor.fetchall()
    relative_volume_list_hashmap = {row[0]: row[1] for row in rows}
    return relative_volume_list_hashmap    

def insert_queue_behavior(mysql_cursor, conn, queue_id, timestamp, queue_pressure, number_trades, market_trade_latency_offset, old_trades_timestamp):

    mysql_cursor.execute("""
        INSERT INTO QueueBehavior (queue_id, timestamp, queue_pressure, number_trades, market_trade_latency_offset, old_trades_count)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (queue_id, timestamp, queue_pressure, number_trades, market_trade_latency_offset, old_trades_timestamp))
    
    conn.commit()

def persist_trade_signal(mysql_cursor, conn, symbol, consumer_id, trade_activity_seconds, trade_signals_count, end_timestamp, open_price, open_map_timestamp, close, accumulated_volume, vwap, low_float, cumulative_volume, relative_volume_factor, aggregates_per_second, relative_volume_list_hashmap_hour, INCREASE_FROM_OPEN, isShortSqueeze, trade_id, trade_exchange, trade_trf_id, action, trade_signal_persist_queue):

    # print(f"Symbol: {symbol}")

    purchasePrediction = "NO"
    purchasePredictionTEST = "NO"

    if close > open_price: # Check if the last trade price is greater than the open price

        price_increase_percentage = (close - open_price) / open_price * 100

        if price_increase_percentage >= INCREASE_FROM_OPEN: # 4% increase from the open price

            purchasePrediction = "BUY"
 
        else:
            # purchasePrediction = "Price increase less than"
            purchasePrediction = "Price increase less than " + str(INCREASE_FROM_OPEN) + "%"            
    else:
        if close == open_price:         
            purchasePrediction = "Doji Candle"
        else:    
            purchasePrediction = "Bearish Candle"
            # print(f"symbol {symbol}  state -> {purchasePrediction} ")

    low_float_value = "high"

    if low_float is not None and low_float < 5000000:        
        low_float_value = "low"

    # The Orders table contains a column named timestamp_unix, which stores the UTC timestamp 
    # representing the exact moment when a trade occurred on an exchange.

    # Another column, local_tc_timestamp, is calculated by subtracting the local system 
    # timestamp from timestamp_unix.
    # This value represents the latency (in milliseconds) between the moment the trade was 
    # executed on the exchange and when it was received or processed locally.

    # ask_price_value = 0
    local_utc_timestamp_ms = int(time.time() * 1000)

    # if ask_price_timestamp > 0:
    #     ask_price_value = end_timestamp - ask_price_timestamp

    # if ask_price == 0:
    ask_price_value = "---"

    if isShortSqueeze == 1:
        purchasePrediction = "short_squeeze"     

    # mysql_cursor.execute('''
    #     INSERT INTO TradeSignalsBuyPerSecond (
    #         `symbol`, `consumer_id`, `trade_activity_seconds`, `tradeSignalsCount`, `open`, `open_timestamp`, `close`, `last_trade_price`, `ask_price`, `ask_timestamp`, `accumulated_volume`, `low_float`, `vwap`, `volume`,
    #         `relative_volume`, `timestamp`, `averageDayVolume`, `purchasePrediction`, `aggregatesPerSecond`, `news_metadata`, `relative_volume_hour`, `timestamp_unix`, `local_utc_timestamp`, `trade_id`, `exchange`, `trf_id`, `temp_action`
    #     ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    # ''', (
    #     symbol,
    #     consumer_id,
    #     trade_activity_seconds,
    #     trade_signals_count,
    #     open_price,  
    #     open_map_timestamp,
    #     close, 
    #     close,  # Asegúrate de que el "close" sea correctamente asignado aquí
    #     0,  # Este es un valor fijo, tal vez quieras cambiarlo
    #     ask_price_value,
    #     accumulated_volume,
    #     low_float_value,
    #     vwap,
    #     cumulative_volume, 
    #     relative_volume_factor,
    #     print_current_time_costa_rica(),
    #     get_average_volume(mysql_cursor, symbol),
    #     purchasePrediction,
    #     0,  # Este valor está fijo, si tienes un valor, colócalo aquí
    #     "---",  # Este valor es un string fijo, asegúrate de que esto esté bien
    #     relative_volume_list_hashmap_hour,  # Este valor también está fijo, revisa si está bien
    #     # format_unix_timestamp(end_timestamp),  # Si esta función está funcionando bien, descoméntala
    #     end_timestamp,        
    #     local_utc_timestamp_ms - end_timestamp,
    #     trade_id, 
    #     trade_exchange, 
    #     trade_trf_id,
    #     action
    # ))

    # tradeSignalId = mysql_cursor.lastrowid
    # conn.commit()

    # ESTO VA PARA UN QUEUE QUE GUARDA LOS TRADESIGNAL.

    trade_signal_persist_queue.put({
        "symbol": symbol,
        "consumer_id": consumer_id,
        "trade_activity_seconds": trade_activity_seconds,
        "trade_signals_count": trade_signals_count,
        "end_timestamp": end_timestamp,                                    
        "open_price": open_price,
        "open_map_timestamp": open_map_timestamp,
        "close": close,
        "accumulated_volume": accumulated_volume,
        "vwap": vwap,   # tu valor fijo
        "low_float": low_float,
        "cumulative_volume": cumulative_volume,  # placeholder
        "relative_volume_factor": relative_volume_factor,
        "aggregates_per_second": aggregates_per_second,
        "relative_volume_list_hashmap_hour": relative_volume_list_hashmap_hour,
        "INCREASE_FROM_OPEN": INCREASE_FROM_OPEN,
        "isShortSqueeze": isShortSqueeze,
        "trade_id": trade_id,  # placeholder
        "trade_exchange": trade_exchange,
        "trade_trf_id": trade_trf_id,
        "action": action
    })     

    return 1, purchasePrediction

def run_async_trade_signal(mysql_cursor, conn, symbol, consumer_id, trade_activity_seconds, trade_signals_count, end_timestamp, open_price, open_map_timestamp, close, accumulated_volume, vwap, low_float, cumulative_volume, relative_volume_factor, aggregates_per_second, relative_volume_list_hashmap_hour, INCREASE_FROM_OPEN, isShortSqueeze, trade_id, trade_exchange, trade_trf_id, action):    

    purchasePrediction = "NO"
    purchasePredictionTEST = "NO"

    if close > open_price: # Check if the last trade price is greater than the open price

        price_increase_percentage = (close - open_price) / open_price * 100

        if price_increase_percentage >= INCREASE_FROM_OPEN: # 4% increase from the open price

            purchasePrediction = "BUY"
 
        else:
            # purchasePrediction = "Price increase less than"
            purchasePrediction = "Price increase less than " + str(INCREASE_FROM_OPEN) + "%"            
    else:
        if close == open_price:         
            purchasePrediction = "Doji Candle"
        else:    
            purchasePrediction = "Bearish Candle"
            # print(f"symbol {symbol}  state -> {purchasePrediction} ")

    low_float_value = "high"

    if low_float is not None and low_float < 5000000:        
        low_float_value = "low"

    # The Orders table contains a column named timestamp_unix, which stores the UTC timestamp 
    # representing the exact moment when a trade occurred on an exchange.

    # Another column, local_tc_timestamp, is calculated by subtracting the local system 
    # timestamp from timestamp_unix.
    # This value represents the latency (in milliseconds) between the moment the trade was 
    # executed on the exchange and when it was received or processed locally.

    # ask_price_value = 0
    local_utc_timestamp_ms = int(time.time() * 1000)

    # if ask_price_timestamp > 0:
    #     ask_price_value = end_timestamp - ask_price_timestamp

    # if ask_price == 0:
    ask_price_value = "---"

    if isShortSqueeze == 1:
        purchasePrediction = "short_squeeze"     

    mysql_cursor.execute('''
        INSERT INTO TradeSignalsBuyPerSecond (
            `symbol`, `consumer_id`, `trade_activity_seconds`, `tradeSignalsCount`, `open`, `open_timestamp`, `close`, `last_trade_price`, `ask_price`, `ask_timestamp`, `accumulated_volume`, `low_float`, `vwap`, `volume`,
            `relative_volume`, `timestamp`, `averageDayVolume`, `purchasePrediction`, `aggregatesPerSecond`, `news_metadata`, `relative_volume_hour`, `timestamp_unix`, `local_utc_timestamp`, `trade_id`, `exchange`, `trf_id`, `temp_action`
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        symbol,
        consumer_id,
        trade_activity_seconds,
        trade_signals_count,
        open_price,  
        open_map_timestamp,
        close, 
        close,  # Asegúrate de que el "close" sea correctamente asignado aquí
        0,  # Este es un valor fijo, tal vez quieras cambiarlo
        ask_price_value,
        accumulated_volume,
        low_float_value,
        vwap,
        cumulative_volume, 
        relative_volume_factor,
        print_current_time_costa_rica(),
        get_average_volume(mysql_cursor, symbol),
        purchasePrediction,
        0,  # Este valor está fijo, si tienes un valor, colócalo aquí
        "---",  # Este valor es un string fijo, asegúrate de que esto esté bien
        relative_volume_list_hashmap_hour,  # Este valor también está fijo, revisa si está bien
        # format_unix_timestamp(end_timestamp),  # Si esta función está funcionando bien, descoméntala
        end_timestamp,        
        local_utc_timestamp_ms - end_timestamp,
        trade_id, 
        trade_exchange, 
        trade_trf_id,
        action
    ))

    tradeSignalId = mysql_cursor.lastrowid
    conn.commit()    

def condition_affects_ohlcv_v_p(trade_conditions, conditions, index):
    # None = plain vanilla trade => always updates OHLCV
    # index -> 0 updates_open_close
    # index -> 1 updates_high_low(price)
    # index -> 2 updates_volume

    if trade_conditions is None:
        return 1

    if not trade_conditions:
        return 0
    
    affects = 0

    for cond_id in trade_conditions:
        cond = conditions[cond_id]
        if cond and cond[index]:
            affects = 1  # Si alguna condición es verdadera, afecta
            break  # Sale del loop porque ya encontramos al menos una verdadera

    return affects    

def condition_affects_ohlcv_component(trade_conditions, conditions, index):

    # None = plain vanilla trade => always updates OHLCV
    # index -> 0 updates_open_close
    # index -> 1 updates_high_low(price)
    # index -> 2 updates_volume

    if trade_conditions is None:
        return 1

    if not trade_conditions:
        return 0
    
    affects = 0

    for cond_id in trade_conditions:
        cond = conditions[cond_id]
        if cond and cond[index]:
            affects = 1
        else:
            return 0

    return affects  

def load_conditions_bool_map(path: str):
    to_bool = lambda s: s.strip().lower() in ("true", "1", "yes", "y")
    m = {}
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            cid = int(row["id"])
            m[cid] = (
                to_bool(row["updates_open_close"]),
                to_bool(row["updates_high_low"]),
                to_bool(row["updates_volume"]),
            )
    return m    

def get_current_hour():
    # Definir la zona horaria de Costa Rica
    costa_rica_tz = pytz.timezone('America/Costa_Rica')
    
    # Obtener la hora actual en UTC y luego convertirla a la zona horaria de Costa Rica
    utc_now = datetime.now(pytz.utc)
    cr_time = utc_now.astimezone(costa_rica_tz)
    
    # Devolver la hora en formato de 12 horas
    return int(cr_time.strftime("%I"))

def get_current_minute():
    return int(datetime.now().strftime("%M"))

def get_am_pm():
    # Definir la zona horaria de Costa Rica
    costa_rica_tz = pytz.timezone('America/Costa_Rica')
    
    # Obtener la hora actual en UTC y luego convertirla a la zona horaria de Costa Rica
    utc_now = datetime.now(pytz.utc)
    cr_time = utc_now.astimezone(costa_rica_tz)
    
    # Determinar AM o PM con la hora de Costa Rica
    return "AM" if cr_time.hour < 12 else "PM"   

async def get_stocks_from_file(file_path):
    # Lee el archivo y evalúa el contenido (si está en formato lista como mencionas)
    with open(file_path, 'r') as file:
        symbols = file.read().strip()

    # Convierte el string en una lista de símbolos
    symbols_list = eval(symbols)

    return symbols_list

def create_subscription_list(tickers):
    subscriptions = [f"T.{ticker}" for ticker in tickers]    
    return subscriptions

async def trade_execution_consumer(consumer_id, trade_queue: asyncio.Queue,
    trade_signal_queue,
    real_time_positions,
    low_float_stocks_dict,
    trade_signal_limit,     
    news_time_window_minutes,
    relative_volume_low_float,
    stale_threshold_minutes_config,
    stock_float_hashmap,
    increase_open,
    low_float_threshold,
    port,
    ib,
    investment_amount,
    MAX_LOSS_TOLERANCE_PER_TRADE,
    RELATIVE_VOLUME_THRESHOLD,
    high_short_interest_stocks, 
    symbols):    

    trade_count = 0
    queue_max_size = 0
    trade_count_total = 0

    queue_max_size = 0

    current_minute = get_current_minute()
    last_check_time = time.time()

    trade_consumer_close_map = {symbol: 0 for symbol in symbols}
    trade_consumer_volume_map = {symbol: 0 for symbol in symbols}
    trade_consumer_open_map = {symbol: 0 for symbol in symbols}
    trade_consumer_open_map_timestamp = {symbol: 0 for symbol in symbols}    
    trade_per_minute_map = {symbol: 0 for symbol in symbols}
    trade_signals_memory_hashmap = {}    

    trades_by_second_map_set = {symbol: set() for symbol in symbols}    

    async with aiosqlite.connect('histFinanData.db') as conn:     

        cursor = await conn.cursor()
        relative_volume_list_hashmap = await get_relative_volume(get_current_hour(), get_current_minute(), get_am_pm(), cursor) 
        print(get_current_hour())  
        print(get_current_minute())
        print(get_am_pm())  
        print(len(relative_volume_list_hashmap))

        conditions = load_conditions_bool_map("polygon_conditions_trade_stocks.csv")     

        print("Open value")
        print(condition_affects_ohlcv_component([12, 37, 41], conditions, 0))
        print("price")
        print(condition_affects_ohlcv_v_p([12, 37, 41], conditions, 1))
        print("volume")
        print(condition_affects_ohlcv_v_p([12, 37, 41], conditions, 2))

        

        print(f"\033[1;33mStarting Consumer Loop - Consumer ID = {consumer_id}... \033[0m")   
        print("  ")
        
        while True:

            trade = await trade_queue.get()
            symbol = trade["symbol"]
            trade_price  = trade["price"]
            trade_volume = trade["volume"]
            unix_timestamp = trade["timestamp"]
            trade_conditions = trade["conditions"]
            trade_id = trade["id"]
            trade_exchange = trade["exchange"]
            trade_trf_id = trade["trf_id"]                

            # SHORT SQUEEZE RISK MANAGEMENT - ALERT IF PRICE DROPS MORE THAN MAX_LOSS_TOLERANCE_PER_TRADE FROM BOT PURCHASE PRICE

            # if symbol in high_short_interest_stocks:    
            #     if trade_consumer_open_map[symbol] > 0:

            #         open_price = trade_consumer_open_map[symbol]  # Esto debe ser el precio al que se abrió

            #         price_change_percentage = ((price - open_price) / open_price) * 100

            #         if price_change_percentage > 10 and symbol not in trade_signals_memory_hashmap:
            #             trade_signals_memory_hashmap[symbol] = 1
            #             print(f"{symbol} - open price: {open_price} current price: {price} Increased {price_change_percentage:.2f}% ")

            #             active_seconds_count = len(trades_by_second_map_set[symbol]) 

            #             tradeSignalId, purchasePrediction =  await persist_trade_signal(cursor, conn, symbol, consumer_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], price, 0, 10, stock_float_hashmap[symbol],
            #             0, 0, {}, {}, increase_open, ask_map[symbol], ask_map_timestamp[symbol], 1)                                                        


            # if symbol in real_time_positions:

            #     bot_price = real_time_positions[symbol]

            #     if price < bot_price * MAX_LOSS_TOLERANCE_PER_TRADE:                                                
            #         print("")                        
            #         porcentaje_caida = ((bot_price -price) / bot_price) * 100
            #         print("🔻 ALERT 🔻")
            #         print(f"{symbol} ha caído más de ({porcentaje_caida:.2f}%)")
            #         print(f"Precio actual: {price}, Precio de compra: {bot_price}")   

            #         check_and_alert_loss(symbol, price, real_time_positions, port, ib)            
                    
                # if price >= bot_price * 1.10:
                    # check_and_take_profits(symbol, real_time_positions, MAX_LOSS_TOLERANCE_PER_TRADE, port, ib, price, bot_price)


            # Converts the timestamp from milliseconds to seconds, as trading systems 
            # typically operate at the second level for event synchronization.
            timestamp_in_seconds = unix_timestamp // 1000
            # Extracts the second within the current minute by calculating the 
            # remainder when dividing the timestamp in seconds by 60 [timestamp_in_seconds % 60].         
            trades_by_second_map_set[symbol].add(timestamp_in_seconds % 60 )  

            if trade_queue.qsize() > queue_max_size:
                queue_max_size = trade_queue.qsize()
                
            trade_count += 1                  
            trade_count_total += 1

            if trade_consumer_open_map[symbol] == 0:
                if condition_affects_ohlcv_component(trade_conditions, conditions, 0):
                    trade_consumer_open_map_timestamp[symbol] = unix_timestamp
                    trade_consumer_open_map[symbol] = trade_price        

                    trade_consumer_close_map[symbol] = trade_price                  
                    # Cuando se establece un Open se convierte en su close tambien. 

            if condition_affects_ohlcv_v_p(trade_conditions, conditions, 1):
                trade_consumer_close_map[symbol] = trade_price                  

            if condition_affects_ohlcv_v_p(trade_conditions, conditions, 2):
                trade_consumer_volume_map[symbol] += trade_volume
                
            cumulative_volume = trade_consumer_volume_map[symbol]            
            relative_volume = relative_volume_list_hashmap[symbol]         

            if relative_volume == 0:
                relative_volume = 1000                  

            relative_volume_factor = round(cumulative_volume / relative_volume , 2)

            if symbol in low_float_stocks_dict:

                if relative_volume_factor >= relative_volume_low_float:       
                    
                    if symbol not in trade_signals_memory_hashmap:    
                        # print(f"LOW Symbol ={symbol} -> relative_volume_factor = {relative_volume_factor} trade_signals_memory_hashmap = {len(trade_signals_memory_hashmap)}")         
                        trade_signals_memory_hashmap[symbol] = cumulative_volume

                        record_number = await get_record_count_for_symbol(conn, cursor, symbol)
                        exists = order_exists(cursor, symbol, "Filled", "BUY")                

                        if trade_consumer_open_map[symbol] == 0:                    
                            continue

                        if record_number > trade_signal_limit:
                            continue

                        if exists:                    
                            continue         

                        if has_existing_trade_signal_with_News(cursor, symbol) == False:
                                    
                            if has_no_recent_trade_signal(cursor, symbol, trade_consumer_close_map[symbol], relative_volume_factor, stale_threshold_minutes_config):
                                    
                                active_seconds_count = len(trades_by_second_map_set[symbol]) 

                                tradeSignalId, purchasePrediction = persist_trade_signal(cursor, conn, symbol, consumer_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], trade_consumer_close_map[symbol], cumulative_volume, 10, stock_float_hashmap[symbol],
                                cumulative_volume, relative_volume_factor, {}, {}, increase_open, 0, trade_id, trade_exchange, trade_trf_id, "default action" )                                

                                if purchasePrediction == "BUY":

                                    print(f"symbol {symbol}  state -> {purchasePrediction} - LOW FLOAT")      
                                    print(f"time = {print_current_time()}")               
                                    print("   ")                    
                                    print(f"\033[1;33mTRADE SIGNAL -> {symbol} \033[0m")       

                                    if stock_float_hashmap[symbol] is not None and stock_float_hashmap[symbol] < low_float_threshold:
                                        print(f"\033[1;31m     Low Float = {format_number(stock_float_hashmap[symbol])}\033[0m")  
                                        # print(f"     Time = {print_current_time()}")   

                                    await trade_signal_queue.put({
                                        "port": port,
                                        "symbol": symbol,
                                        "second": timestamp_in_seconds % 60,
                                        "active_seconds_count": active_seconds_count,                                    
                                        "trade_signals_count": trade_per_minute_map[symbol],
                                        "timestamp": unix_timestamp,
                                        "minute": current_minute,
                                        "price": trade_consumer_close_map[symbol],
                                        "hardcoded": 111,   # tu valor fijo
                                        "cumulative_volume": cumulative_volume,
                                        "extra": {},  # placeholder
                                        "relative_volume_factor": relative_volume_factor,
                                        "news_time_window_minutes": news_time_window_minutes,
                                        "trade_signal_limit": trade_signal_limit,
                                        "open_map": trade_consumer_open_map,
                                        "open_map_timestamp": trade_consumer_open_map_timestamp[symbol],
                                        "extra2": {},  # placeholder
                                        "increase_open": increase_open,
                                        "stale_threshold_minutes_config": stale_threshold_minutes_config,
                                        "extra3": {},  # placeholder
                                        "investment_amount": investment_amount,
                                    })                                            
            else:

                if relative_volume_factor >= RELATIVE_VOLUME_THRESHOLD:

                    if symbol not in trade_signals_memory_hashmap:    
                        trade_signals_memory_hashmap[symbol] = cumulative_volume

                        record_number = await get_record_count_for_symbol(conn, cursor, symbol)
                        exists = await order_exists( cursor, symbol, "Filled", "BUY")

                        # await persist_trade_signal_raw(cursor, conn, symbol, consumer_id, time.localtime().tm_hour, current_minute, price, cumulative_volume, relative_volume_factor, {}, trade_consumer_open_map[symbol], record_number, exists, trade_signal_buffer)                 
                        
                        if trade_consumer_open_map[symbol] == 0:                    
                            continue

                        if record_number > trade_signal_limit:
                            continue

                        if exists:                    
                            continue

                        if await has_existing_trade_signal_with_News(cursor, symbol) == False:
                                    
                            if await has_no_recent_trade_signal(cursor, symbol, trade_consumer_close_map[symbol], relative_volume_factor, stale_threshold_minutes_config):

                                # stock_info = await query_stock_float_short_interest(symbol)   

                                active_seconds_count = len(trades_by_second_map_set[symbol])                                                                         

                                tradeSignalId, purchasePrediction =  await persist_trade_signal(cursor, conn, symbol, consumer_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], trade_consumer_close_map[symbol], cumulative_volume, 10, stock_float_hashmap[symbol],
                                cumulative_volume, relative_volume_factor, {}, {}, increase_open, 0, trade_id, trade_exchange, trade_trf_id,)                               
                                
                                if purchasePrediction == "BUY":

                                    print(f"symbol {symbol}  state -> {purchasePrediction} ")      
                                    print(f"time = {print_current_time()}")               
                                    print("   ")                    
                                    print(f"\033[1;33mTRADE SIGNAL -> {symbol} \033[0m")       
                                    
                                    if stock_float_hashmap[symbol] is not None and stock_float_hashmap[symbol] < low_float_threshold:
                                        print(f"\033[1;31m     Low Float = {format_number(stock_float_hashmap[symbol])}\033[0m")                                                        
                                        # print(f"     Time = {print_current_time()}")   

                                    await trade_signal_queue.put({
                                        "port": port,
                                        "symbol": symbol,
                                        "second": timestamp_in_seconds % 60,
                                        "active_seconds_count": active_seconds_count,
                                        "trade_signals_count": trade_per_minute_map[symbol],
                                        "timestamp": unix_timestamp,
                                        "minute": current_minute,
                                        "price": trade_consumer_close_map[symbol],
                                        "hardcoded": 111,   # tu valor fijo
                                        "cumulative_volume": cumulative_volume,
                                        "extra": {},  # placeholder
                                        "relative_volume_factor": relative_volume_factor,
                                        "news_time_window_minutes": news_time_window_minutes,
                                        "trade_signal_limit": trade_signal_limit,
                                        "open_map": trade_consumer_open_map,
                                        "open_map_timestamp": trade_consumer_open_map_timestamp[symbol],
                                        "extra2": {},  # placeholder
                                        "increase_open": increase_open,
                                        "stale_threshold_minutes_config": stale_threshold_minutes_config,
                                        "extra3": {},  # placeholder
                                        "investment_amount": investment_amount,
                                    })
                                    # await play_bell()                                              

            if( consumer_id == 1 and current_minute != datetime.now().minute ):                  

                current_minute = datetime.now().minute     
                print(f"Current Minute    = {current_minute}")    
                print(f"Trades per MINUTE = {trade_count}")  
                print(f"Total Trades      = {trade_count_total}")  

                await insert_queue_behavior(cursor, conn, "trade_queue", print_current_time(), queue_max_size, trade_count)                

                trade_count = 0 
                queue_max_size = 0      

                trade_consumer_close_map.clear()
                trade_consumer_volume_map.clear()
                trade_consumer_open_map.clear()
                trade_consumer_open_map_timestamp.clear()
                trade_per_minute_map.clear()
                trade_signals_memory_hashmap.clear()

                trades_by_second_map_set.clear()

                trade_consumer_close_map = {symbol: 0 for symbol in symbols}
                trade_consumer_volume_map = {symbol: 0 for symbol in symbols}
                trade_consumer_open_map = {symbol: 0 for symbol in symbols}
                trade_consumer_open_map_timestamp = {symbol: 0 for symbol in symbols}    
                trade_per_minute_map = {symbol: 0 for symbol in symbols}
                trade_signals_memory_hashmap = {}    

                trades_by_second_map_set = {symbol: set() for symbol in symbols}  

                relative_volume_list_hashmap = await get_relative_volume(get_current_hour(), get_current_minute(), get_am_pm(), cursor)                    
                
                local_utc_timestamp_ms = int(time.time() * 1000)

                print(f"Local UTC = {local_utc_timestamp_ms - unix_timestamp}" )
                print("   ")      

            trade_queue.task_done()

async def quote_update_consumer(quote_queue, ask_map, ask_map_timestamp, ask_size_map):

    queue_max_size = 0
    quote_count_per_minute = 0
    quote_count = 0
    current_minute = get_current_minute()

    last_check_time = time.time()

    async with aiosqlite.connect('histFinanData.db') as conn:
        cursor = await conn.cursor()    

        while True:

            quote = await quote_queue.get()

            if quote_queue.qsize() > queue_max_size:
                queue_max_size = quote_queue.qsize()        

            quote_count += 1
            quote_count_per_minute += 1

            symbol     = quote["symbol"]
            ask_price  = quote["ask_price"]
            ask_size   = quote["ask_size"]
            timestamp  = quote["timestamp"]    

            if ask_price is None:
                print(f"[WARN] Skipping quote with ask_price=None: {quote}")
            else:
                ask_map[symbol] = ask_price
                ask_map_timestamp[symbol] = timestamp
                ask_size_map[symbol] = ask_size

            if(current_minute != datetime.now().minute ):                  

                last_check_time = time.time()  # Actualizamos el tiempo de la última verificación

                current_minute = datetime.now().minute        

                # await insert_queue_behavior(cursor, conn, "quote_queue", print_current_time(), queue_max_size, quote_count_per_minute)
                await insert_queue_behavior(cursor, conn, "quote_queue", print_current_time(), queue_max_size, quote_count_per_minute)

                queue_max_size = 0    
                quote_count_per_minute = 0
            
            quote_queue.task_done()    


def trade_signal_persist_process(trade_signal_consumer):

    print(f"\033[1;33mTrade Signal Persist Process {id}... \033[0m")       

    db_connection = mysql.connector.connect(
        host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
        port=3306,
        user="admin", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()                   

    while True:
        signal = trade_signal_consumer.get()

        run_async_trade_signal(
            mysql_cursor, 
            db_connection, 
            signal["symbol"],
            signal["consumer_id"], 
            signal["trade_activity_seconds"],
            signal["trade_signals_count"], 
            signal["end_timestamp"], 
            signal["open_price"],
            signal["open_map_timestamp"],
            signal["close"],
            signal["accumulated_volume"],
            signal["vwap"],
            signal["low_float"],            
            signal["cumulative_volume"], 
            signal["relative_volume_factor"], 
            signal["aggregates_per_second"],
            signal["relative_volume_list_hashmap_hour"],
            signal["INCREASE_FROM_OPEN"],
            signal["isShortSqueeze"],
            signal["trade_id"],
            signal["trade_exchange"],
            signal["trade_trf_id"],
            signal["action"])
      

def trade_signal_consumer(ib, id, trade_signal_queue, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, real_time_positions, investment_amount, trade_signals_track_stock_price):
    
    print(f"\033[1;33mStarting Trade Signal Consumer {id}... \033[0m")        

    while True:
        signal = trade_signal_queue.get()

        symbol = signal["symbol"]

        process_trade_signal(
            ib,
            signal["port"],
            signal["symbol"],
            signal["second"],
            signal["active_seconds_count"],                        
            signal["trade_signals_count"],            
            signal["timestamp"],
            signal["minute"],
            signal["price"],
            signal["hardcoded"],
            signal["cumulative_volume"],
            signal["extra"],
            signal["relative_volume_factor"],
            signal["news_time_window_minutes"],
            signal["trade_signal_limit"],
            signal["open_map"],
            signal["open_map_timestamp"],
            signal["extra2"],
            signal["increase_open"],
            signal["stale_threshold_minutes_config"],
            real_time_positions,
            min_price_threshold,
            max_price_threshold,
            low_float_threshold,
            price_spike_risk_threshold,
            investment_amount,
            trade_signals_track_stock_price
        )

def sell_off_process(ib, port, selloff_queue, real_time_positions):

    print("SellOff Process...")

    db_connection = mysql.connector.connect(
        host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
        port=3306,
        user="admin", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()              

    while True:
        selloff_stock = selloff_queue.get()

        symbol = selloff_stock["symbol"]
        close = selloff_stock["close"]

        check_and_alert_loss(db_connection, mysql_cursor, real_time_positions, symbol, close)


def take_profits_process(ib, port, selloff_queue, real_time_positions):

    print("Take Profit Process...")

    db_connection = mysql.connector.connect(
        host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
        port=3306,
        user="admin", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()              

    while True:
        selloff_stock = selloff_queue.get()

        symbol = selloff_stock["symbol"]
        close = selloff_stock["close"]
        bot_price = selloff_stock["bot_price"]

        check_and_take_profits(db_connection, mysql_cursor, real_time_positions ,symbol, close, bot_price)

def news_catalyst_analyzer(id, port, id_client, news_queue, news_time_window_minutes):
    print(" ")
    print(f"\033[1;33mCatalyst Analyzer {id}... \033[0m")     

    ib = IB()    

    ib.connect('127.0.0.1', port, clientId=id_client)    

    db_connection = mysql.connector.connect(
        host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
        port=3306,
        user="admin", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()              

    while True:
        news_data = news_queue.get()

        symbol = news_data["symbol"]
        tradeSignalId = news_data["tradeSignalId"]

        test_news(ib, db_connection, mysql_cursor, symbol, tradeSignalId, news_time_window_minutes)

def process_trade_signal(ib, PORT, symbol, second, active_seconds_count, trade_signals_count, end_timestamp, minute, close, accumulated_volume, cumulative_volume, aggregates_per_second, 
    relative_volume_factor, news_time_window_minutes, TRADE_SIGNAL_LIMIT, open_map, open_map_timestamp, relative_volume_list_hashmap_hour, INCREASE_FROM_OPEN, stale_threshold_minutes, real_time_positions, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, investment_amount, trade_signals_track_stock_price):                  

    buyStock(ib, PORT, symbol, second, active_seconds_count, trade_signals_count, close, real_time_positions, investment_amount, open_map, open_map_timestamp, INCREASE_FROM_OPEN, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, close, trade_signals_track_stock_price, cumulative_volume)                                           

def buyStock(ib, PORT, symbol, second, active_seconds_count, trade_signals_count, polygon_second_close, real_time_positions, investment_amount, open_map, open_map_timestamp, INCREASE_FROM_OPEN, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD, LOW_FLOAT_THRESHOLD, PRICE_SPIKE_RISK_THRESHOLD, last_trade_price, trade_signals_track_stock_price, cumulative_volume):

    percentage_change = ((last_trade_price - open_map[symbol]) / open_map[symbol]) * 100

    print(f"     Price    : {last_trade_price}")
    print(f"     Increase : {percentage_change:.2f}%")

    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)

    start_timestamp = print_current_time_costa_rica() 
    print(f"Start Time Costa Rica: {start_timestamp}")

    quote = client.get_last_quote(symbol)

    ask_timestamp = "1761235865389"

    ask_price = quote.ask_price
    bid_price = quote.bid_price

    ask_size = quote.ask_size
    bid_size = quote.bid_size

    open_map_timestamp = 0
    
    percentage = 0.45

    current_time = datetime.now()

    current_second = current_time.second

    elapsed_seconds = current_second - open_map_timestamp

    elapsed_seconds_33_percent = elapsed_seconds * percentage

    stock = Stock(symbol, 'SMART', 'USD')

    totalQuantity = determine_purchase_quantity(investment_amount, ask_price)    

    spread = ask_price - bid_price

    spread = round(ask_price - bid_price, 2)

    print(f"Spread = ${spread}")

    if spread > 0.20:

        log_text = f"Spread is too large: ${spread}. Risk of slippage too high."
        print(" ")          
        print(f"\033[1;31m 🔻 Spread is too large: ${spread}. Risk of slippage too high. 🔻  \033[0m")                    
        print(f"")

        print(" ")          

        save_order_to_db(
            symbol, 
            print_current_time_costa_rica(), 
            0, 
            "Not executed", 
            log_text, 
            "BUY", 
            totalQuantity, 
            trade_signals_count,
            ask_price=ask_price, 
            ask_timestamp=ask_timestamp,
            ask_size=ask_size, 
            bid_price=bid_price, 
            bid_size=bid_size, 
            open_price=open_map[symbol], 
            open_map_timestamp=open_map_timestamp,
            last_trade_price=last_trade_price, 
            last_trade_timestamp=" ",
            polygon_second_close=polygon_second_close, 
            active_seconds_count=active_seconds_count
            )

        return    
    
    if active_seconds_count < elapsed_seconds_33_percent:

        log_text = f"LOW Activity - second = {second} - Active Seconds Count = {active_seconds_count}  <  {round(elapsed_seconds_33_percent, 2)} "
        print(" ")          
        print(f"\033[1;31m 🔻 LOW ACTIVITY 🔻 -> {symbol} \033[0m")                    
        print(" ")          

        save_order_to_db(
            symbol, 
            print_current_time_costa_rica(), 
            0, 
            "Not executed", 
            log_text, 
            "BUY", 
            totalQuantity, 
            trade_signals_count,
            ask_price=ask_price, 
            ask_timestamp=ask_timestamp,
            ask_size=ask_size, 
            bid_price=bid_price, 
            bid_size=bid_size, 
            open_price=open_map[symbol], 
            open_map_timestamp=open_map_timestamp,
            last_trade_price=last_trade_price, 
            last_trade_timestamp=" ",
            polygon_second_close=polygon_second_close, 
            active_seconds_count=active_seconds_count
            )

        return    
    

    average_volume = get_average_volume_limit(symbol)

    if average_volume == -1:
        print("There arent data for the last 5 minutes aggegregates.")
    
    print(f"average_volume = {average_volume}")        
    print(f"cumulative_volume = {cumulative_volume}")                

    if cumulative_volume <= (3 * average_volume):

        log_text = f"Fresh validation:  cumulative_volume ={cumulative_volume}  <=  average_volume {(3 * average_volume)} "
        print(" ")          
        print("No es la explosion de volumen esperada. Saliendo...")
        print(" ")          

        save_order_to_db(
            symbol, 
            print_current_time_costa_rica(), 
            0, 
            "Not executed", 
            log_text, 
            "BUY", 
            totalQuantity, 
            trade_signals_count,
            ask_price=ask_price, 
            ask_timestamp=ask_timestamp,
            ask_size=ask_size, 
            bid_price=bid_price, 
            bid_size=bid_size, 
            open_price=open_map[symbol], 
            open_map_timestamp=open_map_timestamp,
            last_trade_price=last_trade_price, 
            last_trade_timestamp=" ",
            polygon_second_close=polygon_second_close, 
            active_seconds_count=active_seconds_count
            )

        return  


    stock_info = query_stock_float_short_interest(symbol)

    if stock_info.get('float') is not None and stock_info['float'] > LOW_FLOAT_THRESHOLD and PORT == 7496:        
        print(" ")
        print(f"\033[1;31m 🔻 Float menor a 5M 🔻 -> {symbol} \033[0m")    
        print(" ")        

        save_order_to_db(
            symbol, 
            print_current_time_costa_rica(), 
            0, 
            "Not executed", 
            "The order has not been executed in live trading because the asset has a float greater than 5 million shares", 
            "BUY", 
            totalQuantity, 
            trade_signals_count,
            ask_price=ask_price, 
            ask_timestamp=ask_timestamp,
            ask_size=ask_size, 
            bid_price=bid_price, 
            bid_size=bid_size, 
            open_price=open_map[symbol], 
            open_map_timestamp=open_map_timestamp,
            last_trade_price=last_trade_price, 
            last_trade_timestamp=" ",
            polygon_second_close=polygon_second_close,
            active_seconds_count=active_seconds_count
            )

        return

    if ask_price == 0:

        log_text = "Ask price == 0"
        print(" ")
        print(f"\033[1;31m 🔻 Ask price == 0 🔻 -> {symbol} \033[0m")    
        print(" ")          

        save_order_to_db(
            symbol, 
            print_current_time_costa_rica(), 
            0, 
            "Not executed", 
            log_text, 
            "BUY", 
            totalQuantity, 
            trade_signals_count,
            ask_price=ask_price, 
            ask_timestamp=ask_timestamp,
            ask_size=ask_size, 
            bid_price=bid_price, 
            bid_size=bid_size, 
            open_price=open_map[symbol], 
            open_map_timestamp=open_map_timestamp,
            last_trade_price=last_trade_price, 
            last_trade_timestamp=" ",
            polygon_second_close=polygon_second_close,
            active_seconds_count=active_seconds_count
            )

        return

    if ask_price < MIN_PRICE_THRESHOLD or ask_price > MAX_PRICE_THRESHOLD:



        log_text = f"Ask price exceeded configured thresholds [${MIN_PRICE_THRESHOLD} to ${MAX_PRICE_THRESHOLD}]"
        print(" ")
        print(f"\033[1;31m 🔻 Ask price exceeded configured thresholds 🔻 -> {symbol} \033[0m")     
        print(" ")              

        save_order_to_db(
            symbol, 
            print_current_time_costa_rica(), 
            0, 
            "Not executed", 
            log_text, 
            "BUY", 
            totalQuantity, 
            trade_signals_count,
            ask_price=ask_price,
            ask_timestamp=ask_timestamp,
            ask_size=ask_size, 
            bid_price=bid_price, 
            bid_size=bid_size, 
            open_price=open_map[symbol], 
            open_map_timestamp=open_map_timestamp,
            last_trade_price=last_trade_price, 
            last_trade_timestamp=" ",
            polygon_second_close=polygon_second_close, 
            active_seconds_count=active_seconds_count)

        return

    if last_trade_price > open_map[symbol]: # Check if the last trade price is greater than the open price

        price_increase_percentage = (last_trade_price - open_map[symbol]) / open_map[symbol] * 100

        # Calculates the percentage increase from the market open (open_map[symbol]) 
        # to the most recent trade price (last_trade_price). INCREASE_FROM_OPEN = 3% e.g.

        if price_increase_percentage >= INCREASE_FROM_OPEN:

            open_price = open_map[symbol]
            percentage_increase = ((ask_price - open_price) / open_price) * 100

                # Verifies that the increase from open does not exceed the maximum acceptable threshold 
                # (PRICE_SPIKE_RISK_THRESHOLD, e.g., 35%).

                # 🔸 This prevents entering trades where the price has surged too quickly, 
                # which may indicate an artificial or unsustainable spike, reducing the risk 
                # of buying at the top before a potential reversal.

            if percentage_increase < PRICE_SPIKE_RISK_THRESHOLD:

                ask_price = ask_price + 0.02

                order = LimitOrder('BUY', totalQuantity, ask_price, outsideRth=True)

                print(f"Put Limit Order to BUY -> \033[1;31m {symbol}\033[0m")
                print(" ")
                print(f"END Time Costa Rica: {start_timestamp}")
                save_order_to_db(
                    symbol, 
                    start_timestamp, 
                    0, 
                    "", 
                    "Processing", 
                    "placeOrderBUY", 
                    totalQuantity, 
                    trade_signals_count,
                    ask_price= ask_price, 
                    ask_timestamp=ask_timestamp,
                    ask_size=ask_size, 
                    bid_price=bid_price, 
                    bid_size=bid_size, 
                    open_price=open_map[symbol], 
                    open_map_timestamp=open_map_timestamp,
                    last_trade_price=last_trade_price, 
                    last_trade_timestamp="  ",
                    polygon_second_close=polygon_second_close,
                    active_seconds_count=active_seconds_count)    

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_async_tasks(client, symbol, stock, order, real_time_positions, totalQuantity, trade_signals_count, ask_price + 0.01, ask_timestamp, ask_size, bid_price, bid_size, open_map[symbol], open_map_timestamp, last_trade_price, polygon_second_close, active_seconds_count))                    

            else:
                
                log_text = f"Too risky: price increased more than {PRICE_SPIKE_RISK_THRESHOLD}% -> percentage_increase: {percentage_increase}"
                print(" ")
                print(f"\033[1;31m 🔻 Too risky: price increased more than 🔻 -> {symbol} \033[0m")                     
                print(" ")

                save_order_to_db(symbol, print_current_time_costa_rica(), 0, "Not executed", log_text, "BUY", 
                totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, open_price=open_price, open_map_timestamp=open_map_timestamp, 
                last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close, active_seconds_count=active_seconds_count)                

        else:

            log_text = f"Price increase less than %{INCREASE_FROM_OPEN}"
            print(" ")            
            print(f"\033[1;31m 🔻 Price increase less than 🔻 -> {symbol} \033[0m")     
            print(" ")

            save_order_to_db(symbol, print_current_time_costa_rica(), 0, "Not executed", log_text, "BUY", 
            totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, open_price=open_map[symbol], open_map_timestamp=open_map_timestamp, 
            last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close, active_seconds_count=active_seconds_count)

    else:
        
        if last_trade_price == open_map[symbol]:       
            print(" ")  
            print(f"\033[1;31m 🔻 Doji Candle 🔻 -> {symbol} \033[0m")     
            print(" ")
            save_order_to_db(symbol, print_current_time_costa_rica(), 0, "Not executed", "Doji Candle", "BUY", 
            totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, open_price=open_map[symbol], open_map_timestamp=open_map_timestamp,
            last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close, active_seconds_count=active_seconds_count)            
        else:    
            print(" ")            
            print(f"\033[1;31m 🔻 Bearish Candle 🔻 ->{symbol} \033[0m")     
            print(" ")
            save_order_to_db(symbol, print_current_time_costa_rica(), 0, "Not executed", "Bearish Candle", "BUY", 
            totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, 
            open_price=open_map[symbol], open_map_timestamp=open_map_timestamp, last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close, active_seconds_count=active_seconds_count)    

async def run_async_tasks(client, symbol, stock, order, real_time_positions, totalQuantity, trade_signals_count, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_map_timestamp, last_trade_price, polygon_second_close, active_seconds_count):  

    start_timestamp = print_current_time_costa_rica()

    PAPER_PORT_IBKR_GATEWAY = 4002

    ib = IB()

    client_id = random.randint(200, 1000)

    await ib.connectAsync('127.0.0.1', PAPER_PORT_IBKR_GATEWAY, clientId=client_id) 

    trade = ib.placeOrder(stock, order)

    start_time = time.time()


    while not trade.isDone():

        elapsed_time = time.time() - start_time

        if elapsed_time > 10:

            log_text = "More than 10 seconds have passed. Cancelling the order."
            print(f"\033[1;31m*********************************************** \033[0m")                            
            print(log_text)
            print(f"\033[1;31m*********************************************** \033[0m")                  

            ib.cancelOrder(trade.order)
            
            save_order_to_db(
                symbol, 
                start_timestamp, 
                0, 
                "Not executed", 
                log_text, 
                "BUY", 
                totalQuantity, 
                trade_signals_count,
                ask_price= ask_price, 
                ask_timestamp=ask_timestamp,
                ask_size=ask_size, 
                bid_price=bid_price, 
                bid_size=bid_size, 
                open_price=open_price, 
                open_map_timestamp=open_map_timestamp,
                last_trade_price=last_trade_price, 
                last_trade_timestamp=" ",
                polygon_second_close=polygon_second_close,
                active_seconds_count=active_seconds_count
                )            
            break

        quote = client.get_last_quote(symbol)
        last_ask_price = quote.ask_price

        if last_ask_price > ask_price:                    

            log_text =  f"Limit Ask has increased from {round(ask_price, 2)} to new ask_price {round(last_ask_price, 2)}. Cancelling the order."
            print(f"\033[1;31m*********************************************** \033[0m")                  
            print(log_text)
            print(f"\033[1;31m*********************************************** \033[0m")                  

            ib.cancelOrder(trade.order)            

            save_order_to_db(
                symbol, 
                start_timestamp, 
                0, 
                "Not executed", 
                log_text, 
                "BUY", 
                totalQuantity, 
                trade_signals_count,
                ask_price= ask_price, 
                ask_timestamp=ask_timestamp,
                ask_size=ask_size, 
                bid_price=bid_price, 
                bid_size=bid_size, 
                open_price=open_price, 
                open_map_timestamp=open_map_timestamp,
                last_trade_price=last_trade_price, 
                last_trade_timestamp=" ",
                polygon_second_close=polygon_second_close,
                active_seconds_count=active_seconds_count
                )

            break

        # print(f"Symbol = {symbol}")
        # print(f"Ask Price = {ask_price}")
        # print(f"New Ask Price = {last_ask_price}")
        # print(print_current_time_costa_rica())
        
        await asyncio.sleep(0.3)


    if trade.isDone() and trade.orderStatus.status == "Filled":

        print(" ")
        print("🎉 Done! 🎉")                          
        print(f"\033[1;31m*********************************************** \033[0m")                  
        print(f"\033[1;31m* The order has been successfully executed.   * \033[0m")          
        print(f"\033[1;31m* Bought {symbol} at ${trade.orderStatus.avgFillPrice} - Status: {trade.orderStatus.status}       * \033[0m")                  
        print(f"\033[1;31m*********************************************** \033[0m")
        print(" ")          

        real_time_positions[symbol] = trade.orderStatus.avgFillPrice

        save_order_to_db(
            symbol, 
            start_timestamp, 
            trade.orderStatus.avgFillPrice, 
            trade.orderStatus.status, 
            trade, 
            "BUY", 
            totalQuantity, 
            trade_signals_count,
            ask_price= ask_price, 
            ask_timestamp=ask_timestamp,
            ask_size=ask_size, 
            bid_price=bid_price, 
            bid_size=bid_size, 
            open_price=open_price, 
            open_map_timestamp=open_map_timestamp,
            last_trade_price=last_trade_price, 
            last_trade_timestamp=" ",
            polygon_second_close=polygon_second_close,
            active_seconds_count=active_seconds_count
            )

        # if trade.orderStatus.status == "Filled":
        #     real_time_positions[symbol] = trade.orderStatus.avgFillPrice
        #     print(" ")
        #     print(" 💹 UPDATED Real Time Positions after BUY 💹")     
        #     print(f"Real Time Positions: {real_time_positions}")     
        #     print(" ")

    # open_trades = await ib.reqCompletedOrdersAsync(apiOnly=True) 

    # count = 0
    # red_bold = "\033[1;31m"  # Rojo y negrita
    # reset = "\033[0m"  # Restablecer color

    # print("Completed Orders:")      
    # print(" ")      

    # for trade in open_trades:
    #     count = count + 1

    #     symbol = trade.contract.symbol
    #     action = trade.order.action
    #     status = trade.orderStatus.status
    #     lmt_price = trade.order.lmtPrice
    #     total_quantity = trade.order.totalQuantity
    #     order_id = trade.order.orderId
        
    #     # Si el símbolo coincide con el stock, toda la línea se pone en rojo y negrita
    #     if symbol == stock:
    #         display_line = f"{red_bold}   {count:<10} {symbol:<10} | Action: {action:<5} | Status: {status:<12} | " \
    #                        f"Price: {lmt_price:<8} | Quantity: {total_quantity:<5} | Order ID: {order_id} {reset}"
    #     else:
    #         display_line = f"   {count:<10} {symbol:<10} | Action: {action:<5} | Status: {status:<12} | " \
    #                        f"Price: {lmt_price:<8} | Quantity: {total_quantity:<5} | Order ID: {order_id}"

    #     print(display_line)

    # open_trades = await ib.reqAllOpenOrdersAsync()   
    # print("Open Orders:")      
    # print(" ")      

    # for trade in open_trades:

    #     symbol = trade.contract.symbol
    #     action = trade.order.action
    #     status = trade.orderStatus.status
    #     lmt_price = trade.order.lmtPrice
    #     total_quantity = trade.order.totalQuantity
    #     order_id = trade.order.orderId
        
    #     # Si el símbolo coincide con el stock, toda la línea se pone en rojo y negrita
    #     if symbol == stock:
    #         display_line = f"{red_bold}Symbol: {symbol:<10} | Action: {action:<5} | Status: {status:<12} | " \
    #                        f"Price: {lmt_price:<8} | Quantity: {total_quantity:<5} | Order ID: {order_id} {reset}"
    #     else:
    #         display_line = f"Symbol: {symbol:<10} | Action: {action:<5} | Status: {status:<12} | " \
    #                        f"Price: {lmt_price:<8} | Quantity: {total_quantity:<5} | Order ID: {order_id}"

    #     print(display_line)

    # print("-" * 130)

    ib.disconnect()

def market_data_producer(queue, symbols: List[str]):
    print(f"\033[1;33mStarting Market Data Producer Multiprocessing... \033[0m")        
    print(f"Producer, Process ID: {os.getpid()}")  
    pid = os.getpid() 
    p = psutil.Process(pid)
    cpu_affinity = p.cpu_affinity()
    print(f"El proceso {pid} está ejecutándose en los núcleos: {cpu_affinity}")            


    ws = WebSocketClient(
        api_key='hzZItvRA2Rfrri2XEjt2VSyMek9PC1Yu',     
        subscriptions=symbols, 
        process_message=mi_manejador_de_mensaje, 
        error_handler=mi_manejador_de_error, 
        close_handler=mi_manejador_de_cierre)

    ws.on_error = mi_manejador_de_error  
    ws.on_close = mi_manejador_de_cierre

    last_check_time = time.time()

    def handle_msg(msgs):
        nonlocal queue, last_check_time
        # for i in range(1, 20):
        for m in msgs:
            # print(m)
            queue.put({
                "symbol": m.symbol,
                "price": m.price,                
                "volume": m.size,
                "timestamp": m.timestamp,
                "conditions": m.conditions,
                "id": m.id,
                "exchange": m.exchange,
                "trf_id": m.trf_id                                                            
            })   

            if time.time() - last_check_time >= 5:

                last_check_time = time.time()
                
                local_utc_timestamp_ms = int(time.time() * 1000)

                print(f"Local UTC = {local_utc_timestamp_ms - m.timestamp}" )
                print("   ")

    ws.run(handle_msg=handle_msg)

async def run_trading_strategy():

    PAPER_PORT_IBKR_GATEWAY = 4002         # Port used to connect to the IBKR Gateway Paper account.
    PORT_IBKR_GATEWAY = 4001               # Port used for real money trading IBKR - Gateway.
    PAPER_PORT = 7497                      # Port used to connect to the Paper account - Trader Workstation.
    PORT = 7496                            # Port used for real money trading using Trader Workstation.

    RELATIVE_VOLUME_THRESHOLD = 5          # This is the threshold for relative volume to trigger a trade. Ross Cameron recommends at least 5x relative volume.    
    TRADE_CAPITAL = 300                    # This is the budget allocated for a single trade.
    
    news_time_window_minutes = 2           # This is the time window in minutes to look for news related to the stock before executing a trade.    
    TRADE_SIGNAL_LIMIT = 20                # This is the limit of trade signals per symbol to avoid overtrading.    
    STALE_THRESHOLD_MINUTES = 4            # This variable basically defines how often a Trade Signal should be generated, i.e., within what time interval. It helps prevent overloading the system with extremely liquid assets.
    STOCKS_WITH_PREV_CLOSE = 10            # Maximum allowed previous-day closing price for stock selection. Used to filter stocks in SQL queries (e.g., close <= $10).

    #Risk Management Config

    INCREASE_FROM_OPEN = 4                 # This variable indicates the minimum percentage of growth a bullish candle should have to be considered.
    MAX_LOSS_TOLERANCE_PER_TRADE = 0.95    # This is the maximum loss tolerance per trade, expressed as a percentage of the budget. For example, 0.80 means 80% of the budget.    
    PRICE_SPIKE_RISK_THRESHOLD = 15        # Defines the maximum acceptable % increase in price over a short time frame(seconds). 
                                           # If a stock's price increases more than this threshold, it is considered too volatile or risky to enter.
    FLOAT_THRESHOLD = 2000000000             # Maximum float value allowed for momentum Strategy

    # Low Float Config

    MIN_PRICE_THRESHOLD = 0.90               # Min price limits for trade validation. Price range used to filter valid assets after a TradeSignal(BUY). Also used to build the low_float dictionary.
    MAX_PRICE_THRESHOLD = 800                 # Max price limits for trade validation. Price range used to filter valid assets after a TradeSignal(BUY). Also used to build the low_float dictionary.
    LOW_FLOAT_THRESHOLD = 5000000           # Maximum float value allowed when building the low_float dictionary. Stocks below this threshold are more likely to experience extreme price movements.
    RELATIVE_VOLUME_THRESHOLD_LOW_FLOAT = 3  # This is the threshold for relative volume to trigger a trade. FOR Low Float Stocks.    

    # High Short Interest Stocks

    SHORT_INTEREST_RATIO = 0.10

    trade_signal_queue = asyncio.Queue(maxsize=50000)
    trade_queue = asyncio.Queue(maxsize=50000)
    # quote_queue = asyncio.Queue(maxsize=50000)

    low_float_stocks_dict = {}
    high_short_interest_stocks  = {}
    stock_float_hashmap = {}

    async with aiosqlite.connect('histFinanData.db') as conn:

        cursor = await conn.cursor()

        symbols = await get_stocks_in_range(cursor, FLOAT_THRESHOLD, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD)    
        low_float_stocks_dict = await get_low_float_stocks(cursor, LOW_FLOAT_THRESHOLD, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD)    
        stock_float_hashmap = await query_all_stock_floats() 

        high_short_interest_stocks = await get_filtered_stocks_short(
            cursor,
            max_float=LOW_FLOAT_THRESHOLD,
            min_short_percent=SHORT_INTEREST_RATIO,
            min_close=MIN_PRICE_THRESHOLD,
            max_close=MAX_PRICE_THRESHOLD
        )            

    # ask_map = {symbol: 0 for symbol in symbols}
    # ask_size_map = {symbol: 0 for symbol in symbols}
    # ask_map_timestamp = {symbol: 0 for symbol in symbols}

    # trade_consumer_close_map = {symbol: 0 for symbol in symbols}
    # trade_consumer_volume_map = {symbol: 0 for symbol in symbols}
    # trade_consumer_open_map = {symbol: 0 for symbol in symbols}
    # trade_consumer_open_map_timestamp = {symbol: 0 for symbol in symbols}    
    # trade_per_minute_map = {symbol: 0 for symbol in symbols}
    # trade_signals_memory_hashmap = {}    

    # trades_by_second_map_set = {symbol: set() for symbol in symbols}

    ws = WSClient()

    ib = IB()    

    await ib.connectAsync('127.0.0.1', PAPER_PORT_IBKR_GATEWAY, clientId=0)    

    real_time_positions = {}
    get_current_positions(ib, real_time_positions)    

    version_code = "v1.2.1"

    initial_config(version_code, PAPER_PORT, TRADE_CAPITAL, len(low_float_stocks_dict), len(symbols), real_time_positions, RELATIVE_VOLUME_THRESHOLD, RELATIVE_VOLUME_THRESHOLD_LOW_FLOAT, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD, LOW_FLOAT_THRESHOLD, high_short_interest_stocks, SHORT_INTEREST_RATIO, INCREASE_FROM_OPEN, MAX_LOSS_TOLERANCE_PER_TRADE, PRICE_SPIKE_RISK_THRESHOLD)   

    await asyncio.gather(
            market_data_producer(ws, trade_queue, create_subscription_list(symbols)),
            trade_execution_consumer(1, trade_queue, trade_signal_queue, 
            real_time_positions,
            low_float_stocks_dict,
            news_time_window_minutes=news_time_window_minutes,
            trade_signal_limit=TRADE_SIGNAL_LIMIT,
            relative_volume_low_float=RELATIVE_VOLUME_THRESHOLD_LOW_FLOAT,
            stale_threshold_minutes_config = STALE_THRESHOLD_MINUTES,
            stock_float_hashmap=stock_float_hashmap,
            increase_open=INCREASE_FROM_OPEN,
            low_float_threshold=LOW_FLOAT_THRESHOLD,
            port=PAPER_PORT,
            ib=ib,
            investment_amount=TRADE_CAPITAL,
            MAX_LOSS_TOLERANCE_PER_TRADE=MAX_LOSS_TOLERANCE_PER_TRADE,
            RELATIVE_VOLUME_THRESHOLD=RELATIVE_VOLUME_THRESHOLD,
            high_short_interest_stocks=high_short_interest_stocks,
            symbols=symbols),

            trade_signal_consumer(ib, "worker-1", trade_signal_queue, min_price_threshold = MIN_PRICE_THRESHOLD, max_price_threshold = MAX_PRICE_THRESHOLD, low_float_threshold = LOW_FLOAT_THRESHOLD, price_spike_risk_threshold = PRICE_SPIKE_RISK_THRESHOLD, real_time_positions=real_time_positions)
            )      

# asyncio.run(run_trading_strategy())


# Función asíncrona para obtener los símbolos desde la base de datos
async def get_symbols():
    symbols = []
    MAX_LOSS_TOLERANCE_PER_TRADE = 0.95    # This is the maximum loss tolerance per trade, expressed as a percentage of the budget. For example, 0.80 means 80% of the budget.    
    PRICE_SPIKE_RISK_THRESHOLD = 15        # Defines the maximum acceptable % increase in price over a short time frame(seconds). 
                                           # If a stock's price increases more than this threshold, it is considered too volatile or risky to enter.
    FLOAT_THRESHOLD = 30000000             # Maximum float value allowed for momentum Strategy

    # Low Float Config

    MIN_PRICE_THRESHOLD = 0.90               # Min price limits for trade validation. Price range used to filter valid assets after a TradeSignal(BUY). Also used to build the low_float dictionary.
    MAX_PRICE_THRESHOLD = 8                 # Max price limits for trade validation. Price range used to filter valid assets after a TradeSignal(BUY). Also used to build the low_float dictionary.
    LOW_FLOAT_THRESHOLD = 7000000           # Maximum float value allowed when building the low_float dictionary. Stocks below this threshold are more likely to experience extreme price movements.
    RELATIVE_VOLUME_THRESHOLD_LOW_FLOAT = 3  # This is the threshold for relative volume to trigger a trade. FOR Low Float Stocks.        

    async with aiosqlite.connect('histFinanData.db') as conn:
        cursor = await conn.cursor()
        symbols = await get_stocks_in_range(cursor, FLOAT_THRESHOLD, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD)
    return symbols

def test_news(ib, conn, cursor, symbol, tradeSignalId, news_time_window_minutes):

    newsCount = 0
    retries = 0
    max_retries = 2
    delay = 20        
    total_retries = 0    

    newsProviders = ib.reqNewsProviders()    

    while retries < max_retries:

        newsCount, first_title = get_news(ib, newsProviders, symbol, tradeSignalId, news_time_window_minutes)   
        
        if newsCount is not None and newsCount > 0:
            print(f"Found {newsCount} news for {symbol}")
            break 

        if newsCount is not None:
            retries += 1
        
        total_retries += 1

        if retries < max_retries:
            time.sleep(delay)

    if newsCount is not None and newsCount > 0:
        hasNews =  update_newsCount(conn, cursor, tradeSignalId, symbol, newsCount, first_title, total_retries)
        if hasNews == False:
            print(" ")
            print(f"\033[1;31mNEWS ALERT -> {symbol} \033[0m")                             
            print(" ")

def consumer_process(worker_id, ib, queue, trade_signal_queue, news_queue, selloff_queue, take_profit_queue, high_short_interest_stocks, symbols, consumer_id, port, stock_float_hashmap, low_float_stocks_dict, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, RELATIVE_VOLUME_THRESHOLD, trade_signals_track_stock_price, real_time_positions, MAX_LOSS_TOLERANCE_PER_TRADE, RELATIVE_VOLUME_FACTOR, trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap, trades_by_second_map_set, trade_signal_persist_queue, manager):
    print(f"\033[1;33mStarting Consumer... \033[0m")        
    print(f"Consumer, Process(1) id: {os.getpid()}")      
    pid = os.getpid() 
    p = psutil.Process(pid)
    cpu_affinity = p.cpu_affinity()
    print(f"El proceso {pid} está ejecutándose en los núcleos: {cpu_affinity}")            

    db_connection = mysql.connector.connect(
        host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
        port=3306,
        user="admin",  
        password="E_I$S5PFri",
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor() 

    trade_count = 0
    trade_count_total = 0
    last_check_time = time.time()
    current_minute = get_current_minute()
    queue_max_size = 0

    conditions = load_conditions_bool_map("polygon_conditions_trade_stocks.csv")         

    # relative_volume_list_hashmap = get_relative_volume(get_current_hour(), get_current_minute(), get_am_pm(), mysql_cursor) 
    relative_volume_list_hashmap_hour = get_relative_volume_hour(get_current_hour(), get_am_pm(), mysql_cursor)

    print(f"Relative Volume Factor Threshold : {RELATIVE_VOLUME_FACTOR}")
    print(f"Real Time Positions  : {len(real_time_positions)}")
    print("Relative Volume Ratio : ")
    print(len(relative_volume_list_hashmap_hour))
    print( " ")
 
    local_unix_timestamp = time.time()    
    old_trades_timestamp = 0

    # last_time = time.time()  # Obtiene el tiempo actual en segundos


    while True:
        try:

            trade = queue.get()

            # if time.time() - last_time >= 15:
            
            #     last_time = time.time()

                # print("  ")              
                # print(f"Han pasado 15 segundos. El minuto actual es: {datetime.now().minute}")
                # print(f"current_minute =  {current_minute}")              
                # print(f"trade_count =  {trade_count}")              
                # print("  ")              
            init_time = time.perf_counter()
            symbol = trade["symbol"]
            trade_price  = trade["price"]
            trade_volume = trade["volume"]
            unix_timestamp = trade["timestamp"]
            trade_conditions = trade["conditions"]
            trade_id = trade["id"]
            trade_exchange = trade["exchange"]
            trade_trf_id = trade["trf_id"]      


            temp_time_stamp = ((unix_timestamp // 60000) % 60)

            
            if temp_time_stamp < current_minute or ( current_minute == 0 and temp_time_stamp == 59):
                old_trades_timestamp += 1         
            else:
        
                with trade_lock:
                    if trade_consumer_open_map[symbol] == 0:
                        if condition_affects_ohlcv_component(trade_conditions, conditions, 0):

                            # Converts the timestamp from milliseconds to seconds, as trading systems 
                            # typically operate at the second level for event synchronization.
                            timestamp_in_seconds = unix_timestamp // 1000
                            # Extracts the second within the current minute by calculating the 
                            # remainder when dividing the timestamp in seconds by 60 [timestamp_in_seconds % 60].         
                            trades_by_second_map_set[symbol].add(timestamp_in_seconds % 60 )


                            trade_consumer_open_map_timestamp[symbol] = timestamp_in_seconds % 60 
                            trade_consumer_open_map[symbol] = trade_price        

                            trade_consumer_close_map[symbol] = trade_price      


                if condition_affects_ohlcv_v_p(trade_conditions, conditions, 1):

                    if trade_volume >= 100:
                        trade_consumer_close_map[symbol] = trade_price   

                if condition_affects_ohlcv_v_p(trade_conditions, conditions, 2):

                    if trade_volume is not None:
                        # trade_consumer_volume_map[symbol] += trade_volume


                        if trade_volume >= 100:
                            #Al parecer el volumen que es menor a 100 no suma para el total de volumen del trade.    
                            trade_consumer_volume_map[symbol] += trade_volume

                            # Esta validacion nos permite filtar trades con volumen menor a 100 acciones, no deberiamos considerar  como un Segundo de actividad cuando el trade es muy pequeño.
                            #Hipotesis para descartar ruido de mercado.

                            # Converts the timestamp from milliseconds to seconds, as trading systems 
                            # typically operate at the second level for event synchronization.
                            timestamp_in_seconds = unix_timestamp // 1000
                            # Extracts the second within the current minute by calculating the 
                            # remainder when dividing the timestamp in seconds by 60 [timestamp_in_seconds % 60].         
                            trades_by_second_map_set[symbol].add(timestamp_in_seconds % 60 )

                    # else:
                    #     print(" ")
                    #     print(trade)                
                    #     print(F"\033[1;31mWARNING: TRADE_VOLUME IS NONE FOR {symbol}\033[0m")
                    #     print(" ")
                        

                    if symbol in real_time_positions:

                        bot_price = real_time_positions[symbol]

                        if trade_consumer_close_map[symbol] < bot_price * MAX_LOSS_TOLERANCE_PER_TRADE and trade_consumer_close_map[symbol] > 0:     
                            del real_time_positions[symbol]                                    
                            print("")                        
                            drop_percentage = ((bot_price -trade_consumer_close_map[symbol]) / bot_price) * 100
                            print("🔻 ALERT 🔻")
                            print(f"{symbol} has dropped more than {drop_percentage:.2f}%")
                            print(f"Last price  = ${trade_consumer_close_map[symbol]:.2f}")
                            print(f"Entry price = ${bot_price:.2f}")

                            selloff_queue.put({
                                "symbol": symbol,
                                "close": trade_consumer_close_map[symbol]
                            })  

                        if trade_consumer_close_map[symbol] >= bot_price * 1.05:

                            del real_time_positions[symbol]                                    

                            take_profit_queue.put({
                                "symbol": symbol,
                                "close": trade_consumer_close_map[symbol],
                                "bot_price": bot_price
                            })

                cumulative_volume = trade_consumer_volume_map[symbol]            

                relative_volume_hour = relative_volume_list_hashmap_hour[symbol]

                if relative_volume_hour == 0:
                    relative_volume_hour = 10000                              

                relative_volume_factor_hour = round(cumulative_volume / relative_volume_hour , 2) 

                if symbol in high_short_interest_stocks:    
                    
                    if trade_consumer_open_map[symbol] > 0:

                        open_price = trade_consumer_open_map[symbol]  # Esto debe ser el precio al que se abrió

                        price_change_percentage = ((trade_consumer_close_map[symbol] - open_price) / open_price) * 100

                        if price_change_percentage > 1 and symbol not in trade_signals_memory_hashmap and relative_volume_factor_hour >= RELATIVE_VOLUME_FACTOR:

                            # Con solo que price_change_percentage sea mayor a uno vamos a considerarlo una senal de compra. 
                            # relative_volume_factor_hour >= RELATIVE_VOLUME_FACTOR: Una de las variables que debemos tomar en cuenta es el R.V.H porque he visto que hay muchos aumentos de precio increase_open
                            # que terminan en nada.

                            print(f"Short Squeeze - Stock Detected: {symbol} - Open Price: {open_price}, Current Price: {trade_consumer_close_map[symbol]}, Change: {price_change_percentage:.2f}%")                    
                            print(f"Open Price: {open_price}, Current Price: {trade_consumer_close_map[symbol]}, Change: {price_change_percentage:.2f}%")     
                            print(" ")                               
                            trade_signals_memory_hashmap[symbol] = 1

                            active_seconds_count = len(trades_by_second_map_set[symbol]) 

                            tradeSignalId, purchasePrediction = persist_trade_signal(mysql_cursor, db_connection, symbol, worker_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], trade_consumer_close_map[symbol], cumulative_volume, 10, stock_float_hashmap[symbol],
                            cumulative_volume, -1, {}, relative_volume_factor_hour, increase_open, 0, trade_id, trade_exchange, trade_trf_id, "short_squeeze", trade_signal_persist_queue )                                                    

                if symbol in trade_signals_track_stock_price:

                    percentage_change = ((trade_consumer_close_map[symbol] - trade_signals_track_stock_price[symbol]) / trade_signals_track_stock_price[symbol]) * 100       

                    if percentage_change >= increase_open:

                        del trade_signals_track_stock_price[symbol]                           

                        print(f"Tracking Price for {symbol}: {trade_consumer_close_map[symbol]}, Change: {percentage_change:.2f}%")   

                        active_seconds_count = len(trades_by_second_map_set[symbol])    

                        trade_signal_queue.put({
                            "action": "BUY",
                            "port": port,
                            "symbol": symbol,
                            "second": timestamp_in_seconds % 60,
                            "active_seconds_count": active_seconds_count,                                    
                            "trade_signals_count": trade_per_minute_map[symbol],
                            "timestamp": unix_timestamp,
                            "minute": current_minute,
                            "price": trade_consumer_close_map[symbol],
                            "hardcoded": 111,   # tu valor fijo
                            "cumulative_volume": cumulative_volume,
                            "extra": {},  # placeholder
                            "relative_volume_factor": -1,
                            "news_time_window_minutes": 0,
                            "trade_signal_limit": trade_signal_limit,
                            "open_map": trade_consumer_open_map,
                            "open_map_timestamp": trade_consumer_open_map_timestamp[symbol],
                            "extra2": {},  # placeholder
                            "increase_open": increase_open,
                            "stale_threshold_minutes_config": stale_threshold_minutes_config,
                        })     
                        
                        tradeSignalId, purchasePrediction = persist_trade_signal(mysql_cursor, db_connection, symbol, worker_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], trade_consumer_close_map[symbol], cumulative_volume, 10, stock_float_hashmap[symbol],
                        cumulative_volume, -1, {}, relative_volume_factor_hour, increase_open, 0, trade_id, trade_exchange, trade_trf_id, "track_stock_price_increase", trade_signal_persist_queue )                                                 


                if relative_volume_factor_hour >= RELATIVE_VOLUME_FACTOR:

                    with trade_lock2:
                        if symbol not in trade_signals_memory_hashmap:    
                            trade_signals_memory_hashmap[symbol] = cumulative_volume
                            
                            if trade_consumer_open_map[symbol] == 0:                    
                                continue

                            # if record_number > trade_signal_limit:
                            #     continue


                            # exists = order_exists(mysql_cursor, symbol, "Filled", "BUY")
                            # if exists:                    
                            #     continue

                            # if has_existing_trade_signal_with_News(mysql_cursor, symbol) == False:
                            
                            
                            # if has_existing_trade_signal_with_News(mysql_cursor, symbol) == False:
                                        
                            # if has_no_recent_trade_signal(mysql_cursor, symbol, trade_consumer_close_map[symbol], relative_volume_factor, stale_threshold_minutes_config):

                            active_seconds_count = len(trades_by_second_map_set[symbol])   

                            #NO SE ESTA GUARDADN UN TRADE SIGNAL... MOVER A QUEUE...
                            # ESTAS VALIDACIONES DEBEN SER ANALIZADAS
                            # record_number = get_record_count_for_symbol(mysql_cursor, symbol)
                            # exists = order_exists(mysql_cursor, symbol, "Filled", "BUY")
                            
                            # if has_existing_trade_signal_with_News(mysql_cursor, symbol) == False:


                            tradeSignalId, purchasePrediction = persist_trade_signal(mysql_cursor, db_connection, symbol, worker_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], trade_consumer_close_map[symbol], cumulative_volume, 10, stock_float_hashmap[symbol],
                            cumulative_volume, -1, {}, relative_volume_factor_hour, increase_open, 0, trade_id, trade_exchange, trade_trf_id, "----", trade_signal_persist_queue)                               


                            if purchasePrediction == "BUY":

                                print(f"symbol {symbol}  state -> {purchasePrediction} ")      
                                print(f"time = {print_current_time()}")               
                                print("   ")                    
                                print(f"\033[1;33mTRADE SIGNAL -> {symbol} \033[0m")       
                                
                                if stock_float_hashmap[symbol] is not None and stock_float_hashmap[symbol] < low_float_threshold:
                                    print(f"\033[1;31m     Low Float = {format_number(stock_float_hashmap[symbol])}\033[0m")                                                        

                                # news_queue.put({
                                #     "symbol": symbol,
                                #     "tradeSignalId": tradeSignalId
                                # })           
                                #                                                                                                                                                               

                                trade_signal_queue.put({
                                    "action": "BUY",
                                    "port": port,
                                    "symbol": symbol,
                                    "second": timestamp_in_seconds % 60,
                                    "active_seconds_count": active_seconds_count,
                                    "trade_signals_count": trade_per_minute_map[symbol],
                                    "timestamp": unix_timestamp,
                                    "minute": current_minute,
                                    "price": trade_consumer_close_map[symbol],
                                    "hardcoded": 111,   # tu valor fijo
                                    "cumulative_volume": cumulative_volume,
                                    "extra": {},  # placeholder
                                    "relative_volume_factor": -1,
                                    "news_time_window_minutes": 0,
                                    "trade_signal_limit": trade_signal_limit,
                                    "open_map": trade_consumer_open_map,
                                    "open_map_timestamp": trade_consumer_open_map_timestamp[symbol],
                                    "extra2": {},  # placeholder
                                    "increase_open": increase_open,
                                    "stale_threshold_minutes_config": stale_threshold_minutes_config,
                                })

                                end_time = time.perf_counter()

                                tiempo_ms = (end_time - init_time) * 1000
                                print(f"Tiempo transcurrido BUY: {tiempo_ms:.2f} ms")                                         

                            else:

                                end_time = time.perf_counter()

                                tiempo_ms = (end_time - init_time) * 1000
                                print(f"Tiempo transcurrido Ext: {tiempo_ms:.2f} ms")                                         


                                if "Price increase less than" in purchasePrediction:
                                    trade_signals_track_stock_price[symbol] = trade_consumer_open_map[symbol]    

                                    # news_queue.put({
                                    #     "symbol": symbol,
                                    #     "tradeSignalId": tradeSignalId
                                    # })                                                                                                                                                                         


                                if "Doji Candle" in purchasePrediction:                                    
                                    trade_signals_track_stock_price[symbol] = trade_consumer_open_map[symbol]

                                    # news_queue.put({
                                    #     "symbol": symbol,
                                    #     "tradeSignalId": tradeSignalId
                                    # })         
                                    # 
                                    #                                                                                                                                                                

            if queue.qsize() > queue_max_size:
                queue_max_size = queue.qsize()                

            trade_count += 1                  
            trade_count_total += 1  
        
            if( current_minute != datetime.now().minute and worker_id == "1"):    
                
                current_minute = datetime.now().minute                     

                local_utc_timestamp_ms = int(time.time() * 1000)

                insert_queue_behavior(mysql_cursor, db_connection, "trade_queue", print_current_time_costa_rica(), queue_max_size, trade_count, local_utc_timestamp_ms - unix_timestamp, old_trades_timestamp)                            

                init = datetime.now()

                insert_query = """
                INSERT INTO minute_candlesticks (stock_symbol, timestamp, volume, close_price)
                VALUES (%s, %s, %s, %s)
                """

                utc_time = datetime.now(pytz.utc)
                costa_rica_tz = pytz.timezone('America/Costa_Rica')

                local_time = utc_time.astimezone(costa_rica_tz)

                formatted_time = local_time.strftime('%Y-%m-%d %H:%M:%S')

                # print(f"Hora local en Costa Rica: {formatted_time}")                

                timestamp = formatted_time


                values = [(symbol, timestamp, trade_consumer_volume_map[symbol], trade_consumer_close_map[symbol])
                        for symbol in symbols]

                mysql_cursor.executemany(insert_query, values)
                db_connection.commit() 
                
                end = datetime.now()

                # print(init)
                # print(end)
                # print(f"Time to insert minute candlesticks: {end - init}")

                trade_consumer_close_map.clear()
                trade_consumer_volume_map.clear()
                # trade_consumer_open_map.clear()
                trade_consumer_open_map_timestamp.clear()
                trade_per_minute_map.clear()                
                trade_signals_track_stock_price.clear()

                trades_by_second_map_set.clear()

                trade_consumer_close_map = {symbol: 0 for symbol in symbols}
                trade_consumer_volume_map = {symbol: 0 for symbol in symbols}
                
                with trade_lock:
                    for symbol in symbols:
                        trade_consumer_open_map[symbol] = 0

                with trade_lock2:
                    trade_signals_memory_hashmap.clear()

                trade_consumer_open_map_timestamp = {symbol: 0 for symbol in symbols}    
                trade_per_minute_map = {symbol: 0 for symbol in symbols}
                trade_signals_track_stock_price = {}    

                trades_by_second_map_set = {symbol: set() for symbol in symbols}  

                relative_volume_list_hashmap = get_relative_volume(get_current_hour(), get_current_minute(), get_am_pm(), mysql_cursor)              
                relative_volume_list_hashmap_hour = get_relative_volume_hour(get_current_hour(), get_am_pm(), mysql_cursor)

                print(f"⏳ Time ⏳     = {print_current_time_costa_rica_hour_minute()} " )
                print("                       ")       
                print(f"Total Trades   = {trade_count_total}")  
                print(f"Trades per M   = {trade_count}")    

                trade_count = 0 

                latencyOffset = local_utc_timestamp_ms - unix_timestamp

                if latencyOffset > 500:
                    print(f"Latency Offset = \033[1;31m{latencyOffset}\033[0m ⚠️")            
                else:
                    print(f"Latency Offset = {latencyOffset}")                            
                
                print(f"Old Trades     = {old_trades_timestamp}" )
                print(f"Positions      = {len(real_time_positions)}")
                print("----------------------")        
                print("   ")        
                old_trades_timestamp = 0
                queue_max_size = 0

        except Exception as e:
            # Captura cualquier otro error que ocurra dentro del proceso
            print(f"Error en el proceso: {e}")
            # También puedes registrar el error en un archivo de log si lo prefieres
        except KeyboardInterrupt:
            print("Interrupción manual recibida. Cerrando consumidor.")
            break  # Salir del ciclo en caso de interrupción
        except Exception as e:
            print(f"Error inesperado: {e}")            

def run_processes(symbols, ws, port, trade_queue, high_short_interest_stocks, low_float_stocks_dict, stock_float_hashmap, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, min_price_threshold, max_price_threshold, price_spike_risk_threshold, investment_amount, RELATIVE_VOLUME_THRESHOLD, short_interest_ratio, max_loss_tolerance_per_trade, news_time_window_minutes, relative_volume_factor):

    trade_queue = multiprocessing.Queue(maxsize=100000)    
    trade_signal_persist_queue = multiprocessing.Queue(maxsize=100)    
    trade_signal_queue = multiprocessing.Queue(maxsize=100000)
    news_queue = multiprocessing.Queue(maxsize=100000)

    selloff_queue = multiprocessing.Queue(maxsize=100)
    take_profit_queue = multiprocessing.Queue(maxsize=100)

    trade_signals_track_stock_price = {}


    trade_consumer_close_map = {symbol: 0 for symbol in symbols}
    trade_consumer_volume_map = {symbol: 0 for symbol in symbols}
    # trade_consumer_open_map = {symbol: 0 for symbol in symbols}
    # print(trade_consumer_open_map)
    trade_consumer_open_map_timestamp = {symbol: 0 for symbol in symbols}    
    trade_per_minute_map = {symbol: 0 for symbol in symbols}
    # trade_signals_memory_hashmap = {}

    # Initializes a dictionary where each symbol (e.g., a stock symbol) is associated with an empty set. 
    # This set will store unique seconds within a minute in which trading activity occurred. 
    # Using a set ensures that each second is recorded only once, preventing duplicates and improving efficiency.

    # In the context of automated trading strategies, this structure is critical for analyzing the temporal 
    # distribution of market activity. It allows identification of abnormal concentrations of volume and price
    # movement during specific seconds, which is key to detecting false signals or market anomalies.

    # This movement distribution analysis is essential to reduce the likelihood of entering a "pop and drop" scenario. 
    # A "pop and drop" occurs when an asset experiences a sharp price increase (pop) followed by a quick drop (drop), 
    # often driven by a false signal or erratic volatility.        
    trades_by_second_map_set = {symbol: set() for symbol in symbols}    



    ib_zero = IB()    
    ib_zero.connect('127.0.0.1', port, clientId=9)    

    # ib2 = IB()    
    # ib2.connect('127.0.0.1', port, clientId=1)        


    with multiprocessing.Manager() as manager:

        real_time_positions = manager.dict()

        trade_signals_memory_hashmap = manager.dict()

        trade_consumer_open_map = manager.dict()

        for symbol in symbols:
            trade_consumer_open_map[symbol] = 0         

        get_current_positions(ib_zero, real_time_positions)        

        version_code = "v1.6.0"

        initial_config(version_code, port, investment_amount, len(low_float_stocks_dict), len(symbols), real_time_positions, RELATIVE_VOLUME_THRESHOLD, relative_volume_low_float, min_price_threshold, max_price_threshold, low_float_threshold, high_short_interest_stocks, short_interest_ratio, increase_open, max_loss_tolerance_per_trade, price_spike_risk_threshold)   

        process1 = multiprocessing.Process(target=market_data_producer, args=(trade_queue, create_subscription_list(symbols),))
        
        consumer_process_1 = multiprocessing.Process(target=consumer_process, args=("1", ib_zero, trade_queue, trade_signal_queue, news_queue, selloff_queue, take_profit_queue, high_short_interest_stocks, symbols, "worker-id", port, stock_float_hashmap, low_float_stocks_dict, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, RELATIVE_VOLUME_THRESHOLD, trade_signals_track_stock_price, real_time_positions, max_loss_tolerance_per_trade, relative_volume_factor, trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap, trades_by_second_map_set, trade_signal_persist_queue, manager))
        consumer_process_2 = multiprocessing.Process(target=consumer_process, args=("2", ib_zero, trade_queue, trade_signal_queue, news_queue, selloff_queue, take_profit_queue, high_short_interest_stocks, symbols, "worker-id", port, stock_float_hashmap, low_float_stocks_dict, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, RELATIVE_VOLUME_THRESHOLD, trade_signals_track_stock_price, real_time_positions, max_loss_tolerance_per_trade, relative_volume_factor, trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap, trades_by_second_map_set, trade_signal_persist_queue, manager))
        consumer_process_3 = multiprocessing.Process(target=consumer_process, args=("3", ib_zero, trade_queue, trade_signal_queue, news_queue, selloff_queue, take_profit_queue, high_short_interest_stocks, symbols, "worker-id", port, stock_float_hashmap, low_float_stocks_dict, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, RELATIVE_VOLUME_THRESHOLD, trade_signals_track_stock_price, real_time_positions, max_loss_tolerance_per_trade, relative_volume_factor, trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap, trades_by_second_map_set, trade_signal_persist_queue, manager))        
        consumer_process_4 = multiprocessing.Process(target=consumer_process, args=("4", ib_zero, trade_queue, trade_signal_queue, news_queue, selloff_queue, take_profit_queue, high_short_interest_stocks, symbols, "worker-id", port, stock_float_hashmap, low_float_stocks_dict, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, RELATIVE_VOLUME_THRESHOLD, trade_signals_track_stock_price, real_time_positions, max_loss_tolerance_per_trade, relative_volume_factor, trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap, trades_by_second_map_set, trade_signal_persist_queue, manager))        
        consumer_process_5 = multiprocessing.Process(target=consumer_process, args=("5", ib_zero, trade_queue, trade_signal_queue, news_queue, selloff_queue, take_profit_queue, high_short_interest_stocks, symbols, "worker-id", port, stock_float_hashmap, low_float_stocks_dict, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, RELATIVE_VOLUME_THRESHOLD, trade_signals_track_stock_price, real_time_positions, max_loss_tolerance_per_trade, relative_volume_factor, trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap, trades_by_second_map_set, trade_signal_persist_queue, manager))
        consumer_process_6 = multiprocessing.Process(target=consumer_process, args=("6", ib_zero, trade_queue, trade_signal_queue, news_queue, selloff_queue, take_profit_queue, high_short_interest_stocks, symbols, "worker-id", port, stock_float_hashmap, low_float_stocks_dict, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, RELATIVE_VOLUME_THRESHOLD, trade_signals_track_stock_price, real_time_positions, max_loss_tolerance_per_trade, relative_volume_factor, trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap, trades_by_second_map_set, trade_signal_persist_queue, manager))
        consumer_process_7 = multiprocessing.Process(target=consumer_process, args=("7", ib_zero, trade_queue, trade_signal_queue, news_queue, selloff_queue, take_profit_queue, high_short_interest_stocks, symbols, "worker-id", port, stock_float_hashmap, low_float_stocks_dict, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, RELATIVE_VOLUME_THRESHOLD, trade_signals_track_stock_price, real_time_positions, max_loss_tolerance_per_trade, relative_volume_factor, trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap, trades_by_second_map_set, trade_signal_persist_queue, manager))
        consumer_process_8 = multiprocessing.Process(target=consumer_process, args=("8", ib_zero, trade_queue, trade_signal_queue, news_queue, selloff_queue, take_profit_queue, high_short_interest_stocks, symbols, "worker-id", port, stock_float_hashmap, low_float_stocks_dict, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, RELATIVE_VOLUME_THRESHOLD, trade_signals_track_stock_price, real_time_positions, max_loss_tolerance_per_trade, relative_volume_factor, trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap, trades_by_second_map_set, trade_signal_persist_queue, manager))        
        consumer_process_9 = multiprocessing.Process(target=consumer_process, args=("9", ib_zero, trade_queue, trade_signal_queue, news_queue, selloff_queue, take_profit_queue, high_short_interest_stocks, symbols, "worker-id", port, stock_float_hashmap, low_float_stocks_dict, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, RELATIVE_VOLUME_THRESHOLD, trade_signals_track_stock_price, real_time_positions, max_loss_tolerance_per_trade, relative_volume_factor, trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap, trades_by_second_map_set, trade_signal_persist_queue, manager))        
        consumer_process_10 = multiprocessing.Process(target=consumer_process, args=("10", ib_zero, trade_queue, trade_signal_queue, news_queue, selloff_queue, take_profit_queue, high_short_interest_stocks, symbols, "worker-id", port, stock_float_hashmap, low_float_stocks_dict, relative_volume_low_float, trade_signal_limit, stale_threshold_minutes_config, increase_open, low_float_threshold, RELATIVE_VOLUME_THRESHOLD, trade_signals_track_stock_price, real_time_positions, max_loss_tolerance_per_trade, relative_volume_factor, trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap, trades_by_second_map_set, trade_signal_persist_queue, manager))

        trade_signal_persist = multiprocessing.Process(target=trade_signal_persist_process, args=(trade_signal_persist_queue,))
        
        trade_signal_consumer1 = multiprocessing.Process(target=trade_signal_consumer, args=(ib_zero, "worker-1", trade_signal_queue, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, real_time_positions, investment_amount, trade_signals_track_stock_price))
        trade_signal_consumer2 = multiprocessing.Process(target=trade_signal_consumer, args=(ib_zero, "worker-2", trade_signal_queue, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, real_time_positions, investment_amount, trade_signals_track_stock_price))
        trade_signal_consumer3 = multiprocessing.Process(target=trade_signal_consumer, args=(ib_zero, "worker-3", trade_signal_queue, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, real_time_positions, investment_amount, trade_signals_track_stock_price))
        trade_signal_consumer4 = multiprocessing.Process(target=trade_signal_consumer, args=(ib_zero, "worker-4", trade_signal_queue, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, real_time_positions, investment_amount, trade_signals_track_stock_price))

        news_catalyts_process1 = multiprocessing.Process(target=news_catalyst_analyzer, args=("news_worker-1", port, 20, news_queue, news_time_window_minutes))
        news_catalyts_process2 = multiprocessing.Process(target=news_catalyst_analyzer, args=("news_worker-2", port, 21, news_queue, news_time_window_minutes))
        news_catalyts_process3 = multiprocessing.Process(target=news_catalyst_analyzer, args=("news_worker-3", port, 22, news_queue, news_time_window_minutes))
        news_catalyts_process4 = multiprocessing.Process(target=news_catalyst_analyzer, args=("news_worker-4", port, 23, news_queue, news_time_window_minutes))

        sellOffProcess = multiprocessing.Process(target=sell_off_process, args=(ib_zero, port, selloff_queue, real_time_positions))            
        takeProfitsProcess  = multiprocessing.Process(target=take_profits_process, args=(ib_zero, port, take_profit_queue, real_time_positions))                    

        process1.start()

        trade_signal_persist.start()

        consumer_process_1.start()
        consumer_process_2.start()
        consumer_process_3.start()
        consumer_process_4.start()
        consumer_process_5.start()
        consumer_process_6.start()
        consumer_process_7.start()
        consumer_process_8.start()
        consumer_process_9.start()
        consumer_process_10.start()

        news_catalyts_process1.start()
        news_catalyts_process2.start()
        news_catalyts_process3.start()
        news_catalyts_process4.start()

        sellOffProcess.start()    
        takeProfitsProcess.start()    

        trade_signal_consumer1.start()
        trade_signal_consumer2.start()
        trade_signal_consumer3.start()
        trade_signal_consumer4.start()

        process1.join()
        trade_signal_persist.join()

        consumer_process_1.join()
        consumer_process_2.join()
        consumer_process_3.join()
        consumer_process_4.join()
        consumer_process_5.join()
        consumer_process_6.join()
        consumer_process_7.join()
        consumer_process_8.join()
        consumer_process_9.join()
        consumer_process_10.join()        

        news_catalyts_process1.join()        
        news_catalyts_process2.join()        
        news_catalyts_process3.join()        
        news_catalyts_process4.join()        

        sellOffProcess.join()
        takeProfitsProcess.join()

        trade_signal_consumer1.join()
        trade_signal_consumer2.join()
        trade_signal_consumer3.join()
        trade_signal_consumer4.join()



def main():

    # symbols = await get_symbols()

    PAPER_PORT_IBKR_GATEWAY = 4002         # Port used to connect to the IBKR Gateway Paper account.
    PORT_IBKR_GATEWAY = 4001               # Port used for real money trading IBKR - Gateway.
    PAPER_PORT = 7497                      # Port used to connect to the Paper account - Trader Workstation.
    PORT = 7496                            # Port used for real money trading using Trader Workstation.

    RELATIVE_VOLUME_THRESHOLD = 5          # This is the threshold for relative volume to trigger a trade. Ross Cameron recommends at least 5x relative volume.    
    TRADE_CAPITAL = 180                      # This is the budget allocated for a single trade.
    
    news_time_window_minutes = 5          # This is the time window in minutes to look for news related to the stock before executing a trade.    
    TRADE_SIGNAL_LIMIT = 20                # This is the limit of trade signals per symbol to avoid overtrading.    
    STALE_THRESHOLD_MINUTES = 4            # This variable basically defines how often a Trade Signal should be generated, i.e., within what time interval. It helps prevent overloading the system with extremely liquid assets.
    STOCKS_WITH_PREV_CLOSE = 12            # Maximum allowed previous-day closing price for stock selection. Used to filter stocks in SQL queries (e.g., close <= $10).

    #Risk Management Config

    INCREASE_FROM_OPEN = 5                 # This variable indicates the minimum percentage of growth a bullish candle should have to be considered.
    MAX_LOSS_TOLERANCE_PER_TRADE = 0.95    # This is the maximum loss tolerance per trade, expressed as a percentage of the budget. For example, 0.80 means 80% of the budget.    
    PRICE_SPIKE_RISK_THRESHOLD = 20        # Defines the maximum acceptable % increase in price over a short time frame(seconds). 
                                            # If a stock's price increases more than this threshold, it is considered too volatile or risky to enter.
    FLOAT_THRESHOLD = 100000000             # Maximum float value allowed for momentum Strategy

    # Low Float Config

    MIN_PRICE_THRESHOLD = 1                  # Min price limits for trade validation. Price range used to filter valid assets after a TradeSignal(BUY). Also used to build the low_float dictionary.
    MAX_PRICE_THRESHOLD = 20                  # Max price limits for trade validation. Price range used to filter valid assets after a TradeSignal(BUY). Also used to build the low_float dictionary.
    LOW_FLOAT_THRESHOLD = 10000000           # Maximum float value allowed when building the low_float dictionary. Stocks below this threshold are more likely to experience extreme price movements.
    RELATIVE_VOLUME_THRESHOLD_LOW_FLOAT = 3  # This is the threshold for relative volume to trigger a trade. FOR Low Float Stocks.    
    RELATIVE_VOLUME_FACTOR = 1              # This is the threshold for relative volume to trigger a trade. 1x represents a complete hour of average volume.

    # High Short Interest Stocks

    SHORT_INTEREST_RATIO = 0.10

    low_float_stocks_dict = {}
    high_short_interest_stocks  = {}
    stock_float_hashmap = {}    

    db_connection = mysql.connector.connect(
        host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
        port=3306,
        user="admin", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()              

    symbols = get_stocks_in_range(mysql_cursor, FLOAT_THRESHOLD, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD)    

    low_float_stocks_dict = get_low_float_stocks(mysql_cursor, LOW_FLOAT_THRESHOLD, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD)    

    stock_float_hashmap = query_all_stock_floats(mysql_cursor) 

    high_short_interest_stocks = get_filtered_stocks_short(
        mysql_cursor,
        max_float=LOW_FLOAT_THRESHOLD,
        min_short_percent=SHORT_INTEREST_RATIO,
        min_close=MIN_PRICE_THRESHOLD,
        max_close=MAX_PRICE_THRESHOLD
    )             

    ws = WSClient()
    trade_queue = asyncio.Queue(maxsize=50000)

    mysql_cursor.close()
    db_connection.close()        

    run_processes(symbols, ws, PAPER_PORT_IBKR_GATEWAY, trade_queue, high_short_interest_stocks, low_float_stocks_dict, stock_float_hashmap, RELATIVE_VOLUME_THRESHOLD_LOW_FLOAT, trade_signal_limit=TRADE_SIGNAL_LIMIT, stale_threshold_minutes_config=STALE_THRESHOLD_MINUTES, increase_open=INCREASE_FROM_OPEN, low_float_threshold=LOW_FLOAT_THRESHOLD, min_price_threshold=MIN_PRICE_THRESHOLD, max_price_threshold=MAX_PRICE_THRESHOLD, price_spike_risk_threshold=PRICE_SPIKE_RISK_THRESHOLD, investment_amount=TRADE_CAPITAL, RELATIVE_VOLUME_THRESHOLD=RELATIVE_VOLUME_THRESHOLD, short_interest_ratio=SHORT_INTEREST_RATIO, max_loss_tolerance_per_trade=MAX_LOSS_TOLERANCE_PER_TRADE, news_time_window_minutes=news_time_window_minutes, relative_volume_factor=RELATIVE_VOLUME_FACTOR)
    

    # except KeyboardInterrupt:
    #     print("Interrupción detectada, cerrando conexión a la base de datos.")
    # finally:
    #     db_connection.close()22
    #     print("Conexión cerrada")

main()