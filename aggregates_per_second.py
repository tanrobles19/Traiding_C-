from polygon import WebSocketClient
from ib_insync import *
from ib_insync import *
from polygon import RESTClient
from polygon.websocket.models import WebSocketMessage, Feed, Market
from typing import List
import threading
import time
from playsound import playsound
import random
# import sqlite3
import aiosqlite

from datetime import datetime, timedelta, date, timezone
import pytz
from dataclasses import dataclass
from typing import Optional, List
import asyncio
import csv
from ib_insync import IB, Stock
from real_time_position_manager import check_and_take_profits
from real_time_position_manager import check_and_alert_loss
import schedule
from numba import njit

import concurrent.futures

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

@dataclass
class News:
    id: int
    author: Optional[str]
    created: str  # Fecha y hora completa legible en Costa Rica
    created_hour_cr: int
    created_minute_cr: int
    title: str
    url: str

def initial_config(port, investment_amount, low_float_stocks, symbols, positions, relative_volume, relative_volume_low_float, min_price, max_price, low_float, high_short_interest_stocks, SHORT_INTEREST_RATIO):

    if port == 7497:
        print(" ")
        print(f"\033[1;33m-------------------------------------------------------------- \033[0m")          
        print(f"\033[1;33m|                        Paper Trading                       | \033[0m")          
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"\033[1;33m|\033[0m High Short-Interest Stocks: {len(high_short_interest_stocks)}                             \033[1;33m|\033[0m")     
        print(f"\033[1;33m|\033[0m Short Interest Radio      : {SHORT_INTEREST_RATIO}                           \033[1;33m|\033[0m")             
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Capital per Trade: ${investment_amount}")     
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Low Float Stocks: {low_float_stocks}")       
        print(f"  Low Float: {low_float}")
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Relative Volume          : {relative_volume}")       
        print(f"  Relative Volume Low Float: {relative_volume_low_float}")       
        print(f"  Price range: [${min_price} - ${max_price}]")               
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")             
        print(f"  Symbols: {symbols}")
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Positions:")
        print(f" {positions}")        
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Time = {print_current_time()}")
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print("  WebSocket Client started...")
        print(f"\033[1;33m|                                                            | \033[0m")                  
        print(f"\033[1;33m-------------------------------------------------------------- \033[0m")          
        print(" ")

    if port == 7496:

        print(" ")
        print(f"\033[1;31m-------------------------------------------------------------- \033[0m")          
        print(f"\033[1;31m|                        Live Trading                       | \033[0m")          
        print(f" Capital per Trade: ${investment_amount}")    
        print(" ") 
        print(f" Low Float Stocks: {low_float_stocks}")               
        print(f" Low Float: {low_float}")
        print(" ") 
        print(f" Relative Volume: {relative_volume}")       
        print(f" Relative Volume Low Float: {relative_volume_low_float}")               
        print(f" Price range: [${min_price} - ${max_price}]")               
        print(" ")
        
        print(f" Symbols: {symbols}")
        print(" ")    
        print(f" Positions: {positions}")
        print(" ")        
        print(f" Time = {print_current_time()}")
        print(" ")        
        print(" WebSocket Client started...")                
        print(f"\033[1;31m|                                                           | \033[0m")          
        print(f"\033[1;31m-------------------------------------------------------------- \033[0m")          
        print(" ")  
        play_ny_stock_exchange_opening_bell()    

@njit(fastmath=True)
def computeTest(cumulative, relative):
    return cumulative / relative

def get_am_pm():
    current_time = datetime.now()
    return "AM" if current_time.hour < 12 else "PM"

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

    

async def insert_queue_behavior(cursor, conn, queue_id, timestamp, queue_pressure, number_trades):

    # try:        
    await cursor.execute("""
        INSERT INTO QueueBehavior (queue_id, timestamp, queue_pressure, number_trades)
        VALUES (?, ?, ?, ?)
    """, (queue_id, timestamp, queue_pressure, number_trades))
    
    await conn.commit()
    
    # except sqlite3.Error as e:
        # print(f"[ERROR] No se pudo insertar el registro: {e}")
    
    # finally:
    #     if conn:
    #         conn.close()    

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

async def quote_update_consumer(quote_queue, ask_map, ask_map_timestamp, ask_size_map):

    queue_max_size = 0
    quote_count_per_minute = 0
    quote_count = 0
    current_minute = get_current_minute()

    # async with aiosqlite.connect('histFinanData.db') as conn:
    #     cursor = await conn.cursor()    

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

        if( current_minute != datetime.now().minute ):  

            current_minute = datetime.now().minute        

            # await insert_queue_behavior(cursor, conn, "quote_queue", print_current_time(), queue_max_size, quote_count_per_minute)

            queue_max_size = 0    
            quote_count_per_minute = 0
        
        quote_queue.task_done()

async def trade_execution_consumer(consumer_id, trade_queue: asyncio.Queue):    

        trade_count = 0
        queue_max_size = 0
        trade_count_total = 0

        queue_max_size = 0

        current_minute = get_current_minute()
        last_check_time = time.time()  # Guardamos el tiempo de la última verificación


        print(f"\033[1;33mStarting Consumer Loop - Consumer ID = {consumer_id}... \033[0m")   
        print("  ")

        while True:

            trade = await trade_queue.get()
            symbol = trade["symbol"]
            price  = trade["price"]
            volume = trade["volume"]
            unix_timestamp = trade["timestamp"]
            trade_conditions = trade["conditions"]

            if trade_queue.qsize() > queue_max_size:
                queue_max_size = trade_queue.qsize()
                
            trade_count += 1                  
            trade_count_total += 1

            if time.time() - last_check_time >= 10:  # 10 segundos

                last_check_time = time.time()  # Actualizamos el tiempo de la última verificación

                current_minute = datetime.now().minute     
                print(f"Current Minute = {current_minute}")    
                print(f"Trades per 10s = {trade_count}")  
                print(f"Total Trades   = {trade_count_total}")  

                trade_count = 0 
                queue_max_size = 0                
                
                local_utc_timestamp_ms = int(time.time() * 1000)

                print(f"Local UTC = {local_utc_timestamp_ms - unix_timestamp}" )
                print("   ")                          
            

            trade_queue.task_done()

async def trade_signal_consumer(ib , id, trade_signal_queue, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, ask_map, ask_map_timestamp, real_time_positions):

    print(f"Trade signal worker id = {id}")

    while True:
        signal = await trade_signal_queue.get()

        symbol = signal["symbol"]

        print(f"TIME = {print_current_time()}")       
        print("    ")


        await process_trade_signal(
            ib,
            signal["port"],
            signal["symbol"],
            signal["second"],
            signal["active_seconds_count"],                        
            signal["trade_signals_count"],            
            ask_map[symbol], 
            ask_map_timestamp[symbol],
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
            signal["investment_amount"]
        )

        trade_signal_queue.task_done()        

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

def print_current_time_microseconds():
    current_time = datetime.now()
    # %f = microsegundos (6 dígitos)
    formatted_time = current_time.strftime("%H:%M:%S.%f")
    return formatted_time    

async def query_all_stock_floats():
    stocks_dict = {}

    async with aiosqlite.connect('histFinanData.db') as conn:
        cursor = await conn.cursor()

        query = """
        SELECT ticker, float
        FROM Stocks
        """

        await cursor.execute(query)
        rows = await cursor.fetchall()

        stocks_dict = {row[0]: row[1] for row in rows if row[1] is not None}

    return stocks_dict

async def query_stock_float_short_interest(symbol):

    async with aiosqlite.connect('histFinanData.db') as conn:
        cursor = await conn.cursor()    

        query = """
        SELECT float, short_percent_float
        FROM Stocks
        WHERE ticker = ?
        """    

        await cursor.execute(query, (symbol, ))

        result = await cursor.fetchone()

        if result:
            return {'float': result[0], 'short_percent_float': result[1]}
        else:
            return None    

async def order_exists(cursor, symbol: str, status: str, order_type: str) -> bool:
    # conn = sqlite3.connect('histFinanData.db')
    # cursor = conn.cursor()    
    query = """
        SELECT 1
        FROM Orders
        WHERE symbol = ? AND status = ? AND orderType = ?
        LIMIT 1
    """
    await cursor.execute(query, (symbol, status, order_type))
    return await cursor.fetchone() is not None

async def get_record_count_for_symbol(conn, cursor, symbol):
    await cursor.execute('''
        SELECT COUNT(*) FROM "TradeSignalsBuyPerSecond" WHERE symbol = ?
    ''', (symbol,))

    row = await cursor.fetchone()
    record_count = row[0] if row else 0

    return record_count    

def human_format(num):
    if num is None:
        return "N/A"
    elif num >= 1_000_000_000:
        return f"{num/1_000_000_000:.1f}B"
    elif num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    else:
        return str(num)

async def get_filtered_stocks_short(cursor, max_float, min_short_percent, min_close, max_close):
    
    query = """
        SELECT ticker, close
        FROM Stocks
        WHERE "float" < ?
          AND short_percent_float > ?
          AND "close" BETWEEN ? AND ?;
    """
    
    await cursor.execute(query, (max_float, min_short_percent, min_close, max_close))
    results = await cursor.fetchall()
    
    stocks_dict = {row[0]: row[1] for row in results}
        
    return stocks_dict

async def get_low_float_stocks(cursor, max_float, min_close, max_close):

    query = """
        SELECT * FROM Stocks
        WHERE float < ?
          AND close >= ?
          AND close <= ?
        ORDER BY close ASC
    """
    await cursor.execute(query, (max_float, min_close, max_close))
    rows = await cursor.fetchall()

    columns = ["ticker", "close", "stock_index", "avg_month_volume", "shares_outstanding", "float"]

    result = {row[0]: row[5] for row in rows}
    return result

#close = The close parameter represents the price sent by the WebSocket (m.close) at this specific second. It is not the most up-to-date price (get_last_trade).

async def persist_trade_signal(cursor, conn, symbol, consumer_id, trade_activity_seconds, trade_signals_count, end_timestamp, open_price, open_map_timestamp, close, accumulated_volume, vwap, low_float, cumulative_volume, relative_volume_factor, aggregates_per_second, open_map, relative_volume_list_hashmap_hour, INCREASE_FROM_OPEN, ask_price, ask_price_timestamp):

    purchasePrediction = "NO"
    purchasePredictionTEST = "NO"

    if close > open_map[symbol]: # Check if the last trade price is greater than the open price

        price_increase_percentage = (close - open_map[symbol]) / open_map[symbol] * 100

        if price_increase_percentage >= INCREASE_FROM_OPEN: # 4% increase from the open price

            purchasePrediction = "BUY"
 
        else:
            # purchasePrediction = "Price increase less than"
            purchasePrediction = "Price increase less than " + str(INCREASE_FROM_OPEN) + "%"            
    else:
        if close == open_map[symbol]:         
            purchasePrediction = "Doji Candle"
        else:    
            purchasePrediction = "Bearish Candle"
            # print(f"symbol {symbol}  state -> {purchasePrediction} ")

    if purchasePrediction == "BUY":

        # This is a low-activity candle with very few trades during the 1-minute aggregation - VALIDATION.

        # timestamp_stored = print_current_time()
        # time_stored = datetime.strptime(timestamp_stored, "%H:%M:%S:%f")

        second = datetime.now().second
        print("Low trades track....")
        print(second)        

        # if time_stored.second < 15 and time_stored.second >= 10 and aggregates_per_second[symbol] < 3: #30%            
        #     purchasePredictionTEST = "LOW_CANDLE_1"
        #     purchasePrediction = "LOW_CANDLE_1"

        # if second >= 15 and second <= 30 and trade_signals_count < 10: #30%            
        # #     purchasePredictionTEST = "LOW_CANDLE_2"            
        #     purchasePrediction = "LOW_CANDLE_2"

        # if second > 30 and second < 45 and trade_signals_count < 30: #30%
        # #     purchasePredictionTEST = "LOW_CANDLE_3"
        #     purchasePrediction = "LOW_CANDLE_3"

        # if second > 45 and trade_signals_count < 45: #40%
        #     purchasePrediction = "LOW_CANDLE_4"

        # purchasePredictionTEST = str(time_stored.second)

    low_float_value = "high"

    if low_float is not None and low_float < 5000000:        
        low_float_value = "low"

    # The Orders table contains a column named timestamp_unix, which stores the UTC timestamp 
    # representing the exact moment when a trade occurred on an exchange.

    # Another column, local_tc_timestamp, is calculated by subtracting the local system 
    # timestamp from timestamp_unix.
    # This value represents the latency (in milliseconds) between the moment the trade was 
    # executed on the exchange and when it was received or processed locally.

    ask_price_value = 0
    local_utc_timestamp_ms = int(time.time() * 1000)

    if ask_price_timestamp > 0:
        ask_price_value = end_timestamp - ask_price_timestamp

    if ask_price == 0:
        ask_price_value = "---"

    await cursor.execute('''
        INSERT INTO TradeSignalsBuyPerSecond (
            symbol, consumer_id, trade_activity_seconds, tradeSignalsCount, open, open_timestamp, close, last_trade_price, ask_price, ask_timestamp, accumulated_volume, low_float, vwap, volume,
            relative_volume, timestamp, averageDayVolume, purchasePrediction, aggregatesPerSecond, news_metadata, relative_volume_hour, timestamp_unix, local_utc_timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        symbol,
        consumer_id,
        trade_activity_seconds,
        trade_signals_count,
        open_price,  
        open_map_timestamp,
        close, 
        close,
        ask_price,
        ask_price_value,
        accumulated_volume,
        low_float_value,
        vwap,
        cumulative_volume, 
        relative_volume_factor,
        print_current_time(),
        await get_average_volume(cursor, symbol),
        purchasePrediction,
        0, #aggregates_per_second[symbol], ahora usamos trades
        "----",
        0, #relative_volume_list_hashmap_hour[symbol],
        format_unix_timestamp(end_timestamp),
        local_utc_timestamp_ms - end_timestamp
    ))

    tradeSignalId = cursor.lastrowid
    await conn.commit()
    
    return tradeSignalId, purchasePrediction

async def persist_trade_signal_raw(cursor, conn, symbol, consumer_id, hour, minute, close, cumulative_volume, relative_volume_factor, relative_volume_list_hashmap_hour, open_price, record_number, exists_register, trade_signal_buffer):

    trade_signal_buffer.append((
        symbol,
        consumer_id,
        hour, 
        minute,
        close, 
        cumulative_volume, 
        relative_volume_factor,
        print_current_time(),
        "RAW_SIGNAL",     # purchasePrediction
        1000,             # relative_volume_hour
        open_price,
        record_number, 
        exists_register
    ))    

    # purchasePrediction = "RAW_SIGNAL"

    # # print(f"Trade Signals = {consumer_id} - {symbol}")

    # await cursor.execute('''
    #     INSERT INTO TradeSignalsRaw (
    #         symbol, consumer_id, hour, minute, close, volume, relative_volume, timestamp, purchasePrediction, relative_volume_hour, open, record_number, exists_register
    #     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    # ''', (
    #     symbol,
    #     consumer_id,
    #     hour, 
    #     minute,
    #     close, 
    #     cumulative_volume, 
    #     relative_volume_factor,
    #     print_current_time(),
    #     purchasePrediction,
    #     1000,
    #     open_price,
    #     record_number, 
    #     exists_register
    # ))

    # await conn.commit()

async def persist_trade_signal_live(cursor, conn, symbol, hour, minute, close, accumulated_volume, attempts_counts):

    print(f"{symbol} -> trade Signal Init = {datetime.now().second}")

    await cursor.execute('''
        INSERT INTO TradeSignalsLive(
            symbol, hour, minute, second, close, volume, timestamp, attempts_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        symbol,
        hour, 
        minute,
        datetime.now().second,        
        close, 
        accumulated_volume,
        print_current_time(),
        attempts_counts
    ))

    await conn.commit()

async def persist_trade_monitor_growth(cursor, conn, symbol, hour, minute, close, accumulated_volume, attempts_counts):

    # print(f"{symbol} -> Monitor Growth Init = {datetime.now().second}")

    await cursor.execute('''
        INSERT INTO TradeSignalsMonitorGrowth(
            symbol, hour, minute, second, close, volume, timestamp, attempts_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        symbol,
        hour, 
        minute,
        datetime.now().second,        
        close, 
        accumulated_volume,
        print_current_time(),
        attempts_counts
    ))

    await conn.commit()    

async def insert_resistance_signal(conn, cursor, symbol, kickOffTracking, resistance_price, volume, timestamp):
    sql = '''INSERT INTO "ResistanceSignals" 
                ("symbol", "kickOffTracking", "resistance_price", "volume", "timestamp")
                VALUES (?, ?, ?, ?, ?)'''
    
    await cursor.execute(sql, (symbol, kickOffTracking, resistance_price, volume, timestamp))
    
    await conn.commit()        
    print("Registro insertado correctamente.")

def determine_purchase_quantity(investment_amount: float, price_per_share: float) -> int:

    #Determines the number of shares that can be purchased given a certain capital and the current price per share.
    #Returns the maximum whole number of shares that can be bought. If the price per share is zero or negative, returns 0.

    if price_per_share <= 0:
        return 0  
    shares = int(investment_amount // price_per_share)
    return shares

async def has_no_recent_trade_signal(cursor, symbol, close, relative_volume, stale_threshold_minutes):

    query = """
    SELECT "timestamp", "close", "relative_volume"
    FROM "TradeSignalsBuyPerSecond"
    WHERE "symbol" = ?
    ORDER BY "timestamp" DESC
    LIMIT 1
    """
    await cursor.execute(query, (symbol,))
    
    result = await cursor.fetchone()
    
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

async def has_existing_trade_signal_with_News(cursor, symbol):
    await cursor.execute('''
        SELECT COUNT(*) FROM TradeSignalsBuyPerSecond
        WHERE symbol = ? AND newsCount > 0
    ''', (symbol,))
    
    result = await cursor.fetchone()

    if result[0] == 0:
        return False 
    return True

async def get_average_volume(cursor, stock_id) -> int:
    
    await cursor.execute('''
        SELECT volume
        FROM AggregatesByMin
        WHERE stockID = ?
    ''', (stock_id,))
    
    rows = await cursor.fetchall()
    
    if rows:
        total_volume = sum(row[0] for row in rows)
        average_volume = total_volume // len(rows)
    else:
        average_volume = 0
        
    return average_volume

async def has_news_for_symbol(cursor, symbol):
    
    await cursor.execute("""
        SELECT newsCount FROM TradeSignalsBuyPerSecond
        WHERE symbol = ?
    """, (symbol,))
    
    rows = await cursor.fetchall()

    if not rows:
        return False

    for row in rows:
        if row[0] is not None:
            return True

    return False        

async def save_order_to_db(symbol, start_timestamp, avgFillPrice, status, tradeLog, orderType, totalQuantity, trade_signals_count, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_map_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close):    

    async with aiosqlite.connect('histFinanData.db') as conn:
        cursor = await conn.cursor()

        await cursor.execute('''
            INSERT INTO Orders (symbol, end_timestamp, start_timestamp, filledPrice, status, log, orderType, totalQuantity, tradeSignalsCount, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, print_current_time(), start_timestamp, avgFillPrice, status,  str(tradeLog), orderType, totalQuantity, trade_signals_count, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_map_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close))

        await conn.commit()

async def update_newsCount(conn, cursor, tradeSignalID, symbol, newsCount, first_title, attempts_count):

    await cursor.execute("""
        SELECT newsCount FROM TradeSignalsBuyPerSecond
        WHERE symbol = ?
    """, (symbol,))

    rows = await cursor.fetchall()

    if not rows:
        raise ValueError(f"No se encontraron registros con el símbolo '{symbol}'.")

    for row in rows:
        if row[0] is not None:
            return True

    await cursor.execute("""
        UPDATE TradeSignalsBuyPerSecond
        SET newsCount = ?, 
            attempts_count = ?,
            news_metadata = ?,
            timestamp_news = ?
        WHERE id = ? AND symbol = ?
    """, (newsCount, attempts_count, first_title, print_current_time(), tradeSignalID, symbol))

    await conn.commit()
    return False 

def play_ny_stock_exchange_opening_bell():
    playsound('ny_stock_exchange_opening_bell.mp3')                        

async def play_bell():
    loop = asyncio.get_running_loop()
    # playsound('piece-of-cake.mp3')        
    await loop.run_in_executor(_executor, playsound, 'piece-of-cake.mp3')

def play_bell_news():    

    playsound('news_clip.mp3')                             

async def get_all_close_prices(cursor) -> dict:
    
    await cursor.execute("SELECT ticker, close FROM Stocks")
    
    rows = await cursor.fetchall()

    close_prices = {row[0]: row[1] for row in rows}

    return close_prices

def get_current_minute():
    return int(datetime.now().strftime("%M"))

def get_current_hour():
    return int(datetime.now().strftime("%I"))

async def get_relative_volume(hour, minute, am_pm, cursor):

    await cursor.execute('''
        SELECT symbol, relative_volume
            FROM RelativeVolumeRatio
                WHERE hour = ? 
                AND minute = ?
                AND amPm = ?
    ''', (hour, minute, am_pm))

    rows = await cursor.fetchall()
    relative_volume_list_hashmap = {row[0]: row[1] for row in rows}
    return relative_volume_list_hashmap

async def get_relative_volume_hour(hour, am_pm, cursor):

    await cursor.execute('''
        SELECT symbol, relative_volume
            FROM RelativeVolumeRatioHour
                WHERE hour = ? 
                AND amPm = ?
    ''', (hour, am_pm))

    rows = await cursor.fetchall()
    relative_volume_list_hashmap = {row[0]: row[1] for row in rows}
    return relative_volume_list_hashmap    

async def get_stock_data_at_specific_time(cursor, stockID, hour=7, minute=30, am_pm='AM'):

    query = """
    SELECT *
    FROM HistoryByMinToday
    WHERE StockID = ? AND 
      hour = ?
      AND minute = ?
      AND amPm = ?
    """
    
    await cursor.execute(query, (stockID, hour, minute, am_pm))
    results = await cursor.fetchall()

    return results

def create_subscription_list(tickers):
    subscriptions = [f"T.{ticker}" for ticker in tickers]
    subscriptionQ = [f"Q.{ticker}" for ticker in tickers]
    finalList = subscriptions + subscriptionQ
    # print(finalList)
    return finalList    

async def get_stocks_from_file(file_path):
    # Lee el archivo y evalúa el contenido (si está en formato lista como mencionas)
    with open(file_path, 'r') as file:
        symbols = file.read().strip()

    # Convierte el string en una lista de símbolos
    symbols_list = eval(symbols)

    return symbols_list

async def get_stocks_in_range(cursor, float_limit, min_price, max_price):
    await cursor.execute('''
        SELECT ticker, close, stock_index
        FROM Stocks
        WHERE float < ?
        AND close > ? 
        AND close < ?
    ''', (float_limit, min_price, max_price))

    rows = await cursor.fetchall()

    tickers = [row[0] for row in rows]
    return tickers

def print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]

def format_unix_timestamp(timestamp_ms):

    timestamp_s = timestamp_ms / 1000.0
    
    current_time = datetime.utcfromtimestamp(timestamp_s)
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")
    
    return formatted_time[:-3]  

def get_current_hour_24():
    current_time_utc = datetime.utcnow()

    cr_tz = pytz.timezone("America/Costa_Rica")

    current_time_cr = current_time_utc.replace(tzinfo=pytz.utc).astimezone(cr_tz)

    return int(current_time_cr.strftime("%H"))

def get_hour_from_timestamp(start_timestamp):
    start_timestamp_seconds = start_timestamp / 1000
    
    start_time_utc = datetime.utcfromtimestamp(start_timestamp_seconds)
    
    cr_tz = pytz.timezone("America/Costa_Rica")
    start_time_cr = start_time_utc.replace(tzinfo=pytz.utc).astimezone(cr_tz)
    
    return int(start_time_cr.strftime("%I"))    

def get_minute_from_timestamp(start_timestamp):
    start_timestamp_seconds = start_timestamp / 1000
    
    start_time_utc = datetime.utcfromtimestamp(start_timestamp_seconds)
    
    cr_tz = pytz.timezone("America/Costa_Rica")
    start_time_cr = start_time_utc.replace(tzinfo=pytz.utc).astimezone(cr_tz)
    
    return int(start_time_cr.strftime("%M"))

async def check_symbol_exists(symbol, cursor):

    cursor.execute("SELECT COUNT(1) FROM TradeSignalsBuyPerSecond WHERE symbol = ?", (symbol,))
    exists = await cursor.fetchone()[0] > 0

    return exists

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

async def get_news(conn, cursor, ib, newsProviders, symbol, tradeSignalId, news_time_window_minutes):

    codes = '+'.join(np.code for np in newsProviders)

    amd = Stock(symbol, 'SMART', 'USD')
    await ib.qualifyContractsAsync(amd)

    headlines = await ib.reqHistoricalNewsAsync(amd.conId, codes, '', '', 10)

    if not headlines:
        return 0, None

    newsCount = 0
    first_title = None

    today = datetime.now().date()

    for headline in headlines:
        
        headline_date = headline.time.date()
        
        if headline_date == today:

            now_utc = datetime.now(timezone.utc)
            headline_time_utc = headline.time.replace(tzinfo=timezone.utc)

            delta = now_utc - headline_time_utc

            if delta <= timedelta(minutes=news_time_window_minutes):                

                formatted_time = headline_time_utc.strftime('%Y-%m-%d %H:%M:%S')
                print("")
                print(f"\n[NOTICIA RECIENTE] Fecha (UTC): {formatted_time}")
                print(f"Proveedor: {headline.providerCode}")
                print(f"Titular {symbol}: {headline.headline}")
                print("")

                if first_title is None:
                    first_title = headline.headline                

                newsCount += 1

    return newsCount, first_title

async def buyStock(ib, PORT, symbol, second, active_seconds_count, trade_signals_count, polygon_second_close, real_time_positions, investment_amount, open_map, open_map_timestamp, INCREASE_FROM_OPEN, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD, LOW_FLOAT_THRESHOLD, PRICE_SPIKE_RISK_THRESHOLD, ask_price, ask_timestamp, last_trade_price):

    print("BUY STOCK")
    print(f"Symbol = {symbol}")
    print(f"active_seconds_count = {active_seconds_count}")    
    print(f"second = {second}")
    print(f"open_map_timestamp = {open_map_timestamp}")

    percentage = 0.33
    elapsed_seconds = second - open_map_timestamp
    elapsed_seconds_33_percent = elapsed_seconds * percentage

    stock = Stock(symbol, 'SMART', 'USD')

    totalQuantity = determine_purchase_quantity(investment_amount, ask_price)    

    ask_size = 1

    bid_price = 1
    bid_size = 1

    if active_seconds_count < elapsed_seconds_33_percent:

        log_text = f"LOW Activity - second = {second} - Active Seconds Count = {active_seconds_count}  <  {elapsed_seconds_33_percent} "
        print(" ")          
        print(f"\033[1;31m ******** LOW ACTIVITY {symbol}******** \033[0m")            
        print(" ")          

        await save_order_to_db(
            symbol, 
            print_current_time(), 
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
            polygon_second_close=polygon_second_close)

        return    

    stock_info = await query_stock_float_short_interest(symbol)

    if stock_info.get('float') is not None and stock_info['float'] > LOW_FLOAT_THRESHOLD and PORT == 7496:        

        print("Float menor a 5M")

        await save_order_to_db(
            symbol, 
            print_current_time(), 
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
            polygon_second_close=polygon_second_close)

        return

    if ask_price == 0:

        log_text = "Ask price == 0"

        print("Ask price == 0")        

        await save_order_to_db(
            symbol, 
            print_current_time(), 
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
            polygon_second_close=polygon_second_close)

        return

    if ask_price < MIN_PRICE_THRESHOLD or ask_price > MAX_PRICE_THRESHOLD:

        log_text = f"Ask price exceeded configured thresholds [${MIN_PRICE_THRESHOLD} to ${MAX_PRICE_THRESHOLD}]"

        print("Precio fuera de Rango")        

        await save_order_to_db(
            symbol, 
            print_current_time(), 
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
            polygon_second_close=polygon_second_close)

        return

    if last_trade_price > open_map[symbol]: # Check if the last trade price is greater than the open price

        price_increase_percentage = (last_trade_price - open_map[symbol]) / open_map[symbol] * 100

        # Calculates the percentage increase from the market open (open_map[symbol]) 
        # to the most recent trade price (last_trade_price). INCREASE_FROM_OPEN = 3% e.g.

        print(f"price_increase_percentage {price_increase_percentage}")

        if price_increase_percentage >= INCREASE_FROM_OPEN:

            open_price = open_map[symbol]
            percentage_increase = ((ask_price - open_price) / open_price) * 100

                # Verifies that the increase from open does not exceed the maximum acceptable threshold 
                # (PRICE_SPIKE_RISK_THRESHOLD, e.g., 35%).

                # 🔸 This prevents entering trades where the price has surged too quickly, 
                # which may indicate an artificial or unsustainable spike, reducing the risk 
                # of buying at the top before a potential reversal.

            if percentage_increase < PRICE_SPIKE_RISK_THRESHOLD:

                order = LimitOrder('BUY', totalQuantity, ask_price + 0.02, outsideRth=True)

                start_timestamp = print_current_time()
                print("ib.connectAsync........... STEP 3")
                print(start_timestamp)
                print(" ")

                await save_order_to_db(
                    symbol, 
                    start_timestamp, 
                    0, 
                    "", 
                    "Processing", 
                    "placeOrderBUY", 
                    totalQuantity, 
                    trade_signals_count,
                    ask_price= ask_price + 0.02, 
                    ask_timestamp=ask_timestamp,
                    ask_size=ask_size, 
                    bid_price=bid_price, 
                    bid_size=bid_size, 
                    open_price=open_price, 
                    open_map_timestamp=open_map_timestamp,
                    last_trade_price=last_trade_price, 
                    last_trade_timestamp="  ",
                    polygon_second_close=polygon_second_close)    

                trade = ib.placeOrder(stock, order)

                while not trade.isDone():
                    await asyncio.sleep(0.5)

                print(f"Order Status: {symbol}")

                await save_order_to_db(
                    symbol, 
                    start_timestamp, 
                    trade.orderStatus.avgFillPrice, 
                    trade.orderStatus.status, 
                    trade, 
                    "BUY", 
                    totalQuantity, 
                    trade_signals_count,
                    ask_price= ask_price + 0.02, 
                    ask_timestamp=ask_timestamp,
                    ask_size=ask_size, 
                    bid_price=bid_price, 
                    bid_size=bid_size, 
                    open_price=open_price, 
                    open_map_timestamp=open_map_timestamp,
                    last_trade_price=last_trade_price, 
                    last_trade_timestamp=" ",
                    polygon_second_close=polygon_second_close)

                if trade.orderStatus.status == "Filled":
                    real_time_positions[symbol] = trade.orderStatus.avgFillPrice
                    print(f"Real Time Positions: {real_time_positions}")     
            else:
                
                log_text = f"Too risky: price increased more than {PRICE_SPIKE_RISK_THRESHOLD}% -> percentage_increase: {percentage_increase}"

                print(log_text)

                await save_order_to_db(symbol, print_current_time(), 0, "Not executed", log_text, "BUY", 
                totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, open_price=open_price, open_map_timestamp=open_map_timestamp, 
                last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close)                

        else:

            log_text = f"Price increase less than %{INCREASE_FROM_OPEN}"

            print(log_text)

            await save_order_to_db(symbol, print_current_time(), 0, "Not executed", log_text, "BUY", 
            totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, open_price=open_map[symbol], open_map_timestamp=open_map_timestamp, 
            last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close)

    else:
        
        if last_trade_price == open_map[symbol]:         
            print("buyStock(...) -> Doji Candle")
            
            await save_order_to_db(symbol, print_current_time(), 0, "Not executed", "Doji Candle", "BUY", 
            totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, open_price=open_map[symbol], open_map_timestamp=open_map_timestamp,
            last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close)            
        else:    
            print("buyStock(...) -> Bearish Candle")
            await save_order_to_db(symbol, print_current_time(), 0, "Not executed", "Bearish Candle", "BUY", 
            totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, 
            open_price=open_map[symbol], open_map_timestamp=open_map_timestamp, last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close)

async def  checkResistanceSignals(conn, cursor, priceHashMap):

    sql_select = '''SELECT id, symbol, kickOffTracking, resistance_price FROM "ResistanceSignals"'''
    cursor.execute(sql_select)
    
    records = cursor.fetchall()
    
    if records:
        for record in records:
            record_id = record[0]
            symbol = record[1]
            kickOffTracking = record[2]
            resistance_price = record[3]

            # Si kickOffTracking >= 10 lo imprimimos
            # if kickOffTracking >= 10:
            #     print(f"ID: {record_id} - kickOffTracking: {kickOffTracking}")
            
            # Si kickOffTracking < 10 lo incrementamos
            if kickOffTracking < 10:
                new_kickOffTracking = kickOffTracking + 1
                sql_update_kickoff = '''UPDATE "ResistanceSignals" SET kickOffTracking = ? WHERE id = ?'''
                cursor.execute(sql_update_kickoff, (new_kickOffTracking, record_id))

            # Verificamos si el símbolo está en el priceHashMap
            if symbol in priceHashMap:
                current_price = priceHashMap[symbol]
                if current_price > resistance_price:
                    sql_update_resistance = '''UPDATE "ResistanceSignals" SET resistance_price = ? WHERE id = ?'''
                    cursor.execute(sql_update_resistance, (current_price, record_id))
                    print(f"Nueva resistencia para {symbol}: {current_price} (antes era {resistance_price})")
        
        conn.commit()    

# async def track_buy_signal_status(PORT, symbol, close, hour, current_minute, investment_amount, open_map, real_time_positions, trade_signal_live, INCREASE_FROM_OPEN, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD, LOW_FLOAT_THRESHOLD, PRICE_SPIKE_RISK_THRESHOLD, low_float_stocks_dict):

#     conn = sqlite3.connect('histFinanData.db')
#     cursor = conn.cursor()   
                            
#     await cursor.execute('''
#         SELECT second FROM TradeSignalsLive 
#         WHERE symbol = ? AND hour = ? AND minute = ?
#         LIMIT 1
#     ''', (symbol, hour, current_minute))

#     result = await cursor.fetchone()

#     if result:
#         trade_signal_live_init_second = result[0]
#         current_second = datetime.now().second

#         percentage = 0.33
#         elapsed_seconds = current_second - trade_signal_live_init_second
#         elapsed_seconds_33_percent = elapsed_seconds * percentage

#         if trade_signal_live[symbol] > elapsed_seconds_33_percent:

#             attempts_count = trade_signal_live[symbol]
#             del trade_signal_live[symbol]

#             end = print_current_time()

#             print(" ")
#             print(f"symbol = {symbol}")
#             print(f"current_second = {current_second}")
#             print(f"trade_signal_live_init_second = {trade_signal_live_init_second}")
#             print(" ")

#             await buyStock(PORT, symbol, close, real_time_positions, investment_amount, open_map, INCREASE_FROM_OPEN, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD, LOW_FLOAT_THRESHOLD, PRICE_SPIKE_RISK_THRESHOLD)
#             insert_resistance_signal(conn, cursor, symbol, 0, close, 0, print_current_time())            

#             cursor.execute('''
#                 INSERT INTO TradeSignalsLive(
#                     symbol, hour, minute, second, close, volume, timestamp, attempts_count, data, current_second, elapsed_seconds, elapsed_seconds_33_percent
#                 ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
#             ''', (
#                 symbol,
#                 hour, 
#                 current_minute,
#                 datetime.now().second,        
#                 close, 
#                 0,
#                 end,
#                 attempts_count,
#                 "LIVE",
#                 current_second,
#                 elapsed_seconds,
#                 elapsed_seconds_33_percent
#             ))

#             conn.commit()
#         else:
#             cursor.execute('''
#                 INSERT INTO TradeSignalsLive(
#                     symbol, hour, minute, second, close, volume, timestamp, attempts_count, data, current_second, elapsed_seconds, elapsed_seconds_33_percent
#                 ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
#             ''', (
#                 symbol,
#                 hour, 
#                 current_minute,
#                 datetime.now().second,        
#                 close, 
#                 0,
#                 print_current_time(),
#                 trade_signal_live[symbol],
#                 "LOW_TRANSACTIONS",
#                 current_second,
#                 elapsed_seconds,
#                 elapsed_seconds_33_percent                
#             ))

#             conn.commit() 
#     conn.close()                            

async def monitor_growth_trade_signal(conn, cursor, PORT, symbol, close, hour, current_minute, investment_amount, open_map, real_time_positions, trade_signal_live, INCREASE_FROM_OPEN):
                            
    await cursor.execute('''
        SELECT second FROM TradeSignalsMonitorGrowth 
        WHERE symbol = ? AND hour = ? AND minute = ?
        LIMIT 1
    ''', (symbol, hour, current_minute))

    result = await cursor.fetchone()

    # print(f"{symbol} = monitor_growth_trade_signal ***********")

    if result:
        trade_signal_live_init_second = result[0]
        current_second = datetime.now().second

        percentage = 0.33
        elapsed_seconds = current_second - trade_signal_live_init_second
        elapsed_seconds_33_percent = elapsed_seconds * percentage

        if trade_signal_live[symbol] > elapsed_seconds_33_percent:

            attempts_count = trade_signal_live[symbol]
            del trade_signal_live[symbol]

            end = print_current_time()

            print(" ")
            print(f"symbol = {symbol}")
            print(f"current_second = {current_second}")
            print(f"trade_signal_live_init_second = {trade_signal_live_init_second}")
            print(" ")

            # await buyStock(PORT, symbol, close, real_time_positions, investment_amount, open_map, INCREASE_FROM_OPEN)
            # play_bell()     

            insert_resistance_signal(conn, cursor, symbol, 0, close, 0, print_current_time())            

            cursor.execute('''
                INSERT INTO TradeSignalsMonitorGrowth(
                    symbol, hour, minute, second, close, volume, timestamp, attempts_count, data, current_second, elapsed_seconds, elapsed_seconds_33_percent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                symbol,
                hour, 
                current_minute,
                datetime.now().second,        
                close, 
                0,
                end,
                attempts_count,
                "LIVE",
                current_second,
                elapsed_seconds,
                elapsed_seconds_33_percent
            ))

            conn.commit()
        else:
            cursor.execute('''
                INSERT INTO TradeSignalsMonitorGrowth(
                    symbol, hour, minute, second, close, volume, timestamp, attempts_count, data, current_second, elapsed_seconds, elapsed_seconds_33_percent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                symbol,
                hour, 
                current_minute,
                datetime.now().second,        
                close, 
                0,
                print_current_time(),
                trade_signal_live[symbol],
                "LOW_TRANSACTIONS",
                current_second,
                elapsed_seconds,
                elapsed_seconds_33_percent                
            ))

            conn.commit()                                    

#open_price = The parameter open_price contains the Open value of the candlestick that is being built during the current minute.

async def process_trade_signal(ib ,PORT, symbol, second, active_seconds_count, trade_signals_count, ask, ask_timestamp, end_timestamp, minute, close, accumulated_volume, cumulative_volume, aggregates_per_second, 
    relative_volume_factor, news_time_window_minutes, TRADE_SIGNAL_LIMIT, open_map, open_map_timestamp, relative_volume_list_hashmap_hour, INCREASE_FROM_OPEN, stale_threshold_minutes, real_time_positions, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, investment_amount): 
    
    print("process_trade_signal -> BUY")
    print(f"time = {print_current_time()}")               
    await buyStock(ib, PORT, symbol, second, active_seconds_count, trade_signals_count, close, real_time_positions, investment_amount, open_map, open_map_timestamp, INCREASE_FROM_OPEN, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, ask, ask_timestamp, close)                                         

    # try:
        # conn = sqlite3.connect('histFinanData.db')
        # cursor = conn.cursor()   
        # conn.close()
                                                      

        #                     buyStock(PORT, symbol, close, real_time_positions, investment_amount, open_map, INCREASE_FROM_OPEN, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold)

        #             if stock_info.get('float') is not None and stock_info['float'] > low_float_threshold:
        #                 print(f"Float -> {human_format(stock_info.get('float'))}")                                                   

        #             if stock_info.get('short_percent_float') is not None and stock_info['short_percent_float'] > 0.10:
        #                 print(f"\033[1;31mShort % Float > 10%\033[0m")                    

        #             print("   ")
        #             play_bell()     

        #             newsCount = 0
        #             retries = 0
        #             max_retries = 2
        #             delay = 20        
        #             total_retries = 0    

        #             # ib = IB()
        #             # client_id = random.randint(1, 1000)
        #             # ib = await ib.connectAsync('127.0.0.1', PORT, clientId=client_id)                    

        #             # while retries < max_retries:

        #             #     newsCount, first_title = await get_news(conn, cursor, ib, newsProviders, symbol, tradeSignalId, news_time_window_minutes)   
                        
        #             #     if newsCount is not None and newsCount > 0:
        #             #         print(f"Found {newsCount} news for {symbol}")
        #             #         break 

        #             #     if newsCount is not None:
        #             #         retries += 1
                        
        #             #     total_retries += 1

        #             #     if retries < max_retries:
        #             #         await asyncio.sleep(delay)

        #             # if newsCount is not None and newsCount > 0:
        #             #     hasNews =  update_newsCount(conn, cursor, tradeSignalId, symbol, newsCount, first_title, total_retries)
        #             #     if hasNews == False:
        #             #         print(" ")
        #             #         print(f"\033[1;31mNEWS ALERT -> {symbol} \033[0m")                             
        #             #         print(" ")
        #             #         play_bell_news()                            

        #             # ib.disconnect()         
        # conn.close()

    # except sqlite3.Error as e:
    #     print(f"SQLite error: {e}")    

# async def persist_aggregates_by_minute(conn, cursor, symbol, volume, has_symbols, close_map, volume_map, amPm, current_minute, real_time_positions, trade_signals_memory_hashmap):

#     # cursor.execute('BEGIN TRANSACTION')

#     # for symbol, volume in volume_map.items():
#     #     cursor.execute('''
#     #         INSERT INTO "AggregatesByMin" (stockID, volume, hour, minute, close, vwap)
#     #         VALUES (?, ?, ?, ?, ?, ?)
#     #     ''', (symbol, volume, time.localtime().tm_hour, time.localtime().tm_min -1, 0, 0))

#     # cursor.execute('COMMIT')                

#     volume_map = {symbol: 0 for symbol in has_symbols}

#     relative_volume_list_hashmap = get_relative_volume(get_hour_from_timestamp(current_minute), current_minute, amPm, cursor)
    
#     trade_signals_memory_hashmap.clear()
    
#     conn.close()

    # asyncio.create_task(checkResistanceSignals(conn, cursor, priceHashMap=close_map))

def get_current_positions(ib, real_time_positions):
    positions = ib.positions()
    
    for pos in positions:

        symbol = pos.contract.symbol
        avg_cost = pos.avgCost
        
        real_time_positions[symbol] = avg_cost        

# async def test(msgs: List[WebSocketMessage], PORT, STALE_THRESHOLD_MINUTES, trade_signal_live, trade_signal_monitor_growth,  relative_volume_list_hashmap, relative_volume_list_hashmap_hour, yesterday_close_list_hashmap, trade_signals_memory_hashmap, current_minute, volume_map, aggregates_per_second, close_map, open_map, ib, newsProviders, real_time_positions, investment_amount, port, MAX_LOSS_TOLERANCE_PER_TRADE, RELATIVE_VOLUME_THRESHOLD, news_time_window_minutes, trade_signal_limit, INCREASE_FROM_OPEN, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, low_float_stocks_dict, has_symbols):    

#     # print(f"Second: {datetime.now().second}")
#     for m in msgs:

#         volume_map[m.symbol] += m.volume
#         # print( format_unix_timestamp(m.end_timestamp) )            

#         # SELL POSTIONS
#         check_and_alert_loss(m, real_time_positions, MAX_LOSS_TOLERANCE_PER_TRADE, port, ib)
#         check_and_take_profits(m, real_time_positions, MAX_LOSS_TOLERANCE_PER_TRADE, port, ib)

#         if m.symbol in trade_signal_live:                    

#             trade_signal_live[m.symbol] = trade_signal_live[m.symbol] + 1

#             if trade_signal_live[m.symbol] >= 3:
                
#                 asyncio.create_task( 
#                     track_buy_signal_status(
#                         PORT, 
#                         m.symbol, 
#                         m.close, 
#                         time.localtime().tm_hour, 
#                         current_minute, 
#                         investment_amount, 
#                         open_map, 
#                         real_time_positions, 
#                         trade_signal_live, 
#                         INCREASE_FROM_OPEN, 
#                         min_price_threshold, 
#                         max_price_threshold, 
#                         low_float_threshold,
#                         price_spike_risk_threshold,
#                         low_float_stocks_dict)
#                 )

#         # if m.symbol in trade_signal_monitor_growth:                    

#         #     trade_signal_monitor_growth[m.symbol] = trade_signal_monitor_growth[m.symbol] + 1

#         #     if trade_signal_monitor_growth[m.symbol] >= 4:
                
#         #         asyncio.create_task( 
#         #             monitor_growth_trade_signal(conn, cursor, PORT, m.symbol, m.close, time.localtime().tm_hour, current_minute, investment_amount, open_map, real_time_positions, trade_signal_monitor_growth, INCREASE_FROM_OPEN, min_price_threshold, max_price_threshold)
#         #         )                        
                

#         if m.symbol in open_map:
#             if open_map[m.symbol] == 0:
#                 open_map[m.symbol] = m.open                

#         volume_map[m.symbol] += m.volume
#         aggregates_per_second[m.symbol] = aggregates_per_second[m.symbol] + 1
#         close_map[m.symbol] = m.close

#         if m.symbol in low_float_stocks_dict:
#             #Low Float Relative Volume
            
#             cumulative_volume = volume_map[m.symbol]            
#             relative_volume = relative_volume_list_hashmap[m.symbol]

#             # TO DO
#             # SI el relative Volume NO existe vamos a consultar el Hour Relative Volume...
#             # Ejemplo -> muchas veces se detecta un Trade Signal... al no haber relative volume  podriamos consultar el por hora.
#             # Si el cumulative_volume es un 30% del R.V podria ser una segal de compra.

#             if relative_volume == 0:
#                 # esto como valor defaul no esta bien... no es relativo a la accion... debemos probar con el por hora. 
#                 relative_volume = 300                 

#             relative_volume_factor = round(cumulative_volume / relative_volume , 2)
            
#             if relative_volume_factor >= 2 and m.close >= ( yesterday_close_list_hashmap[m.symbol]):
#                 if m.symbol not in trade_signals_memory_hashmap:
                    
#                     trade_signals_memƒory_hashmap[m.symbol] = cumulative_volume

#                     asyncio.create_task(
#                         process_trade_signal(
#                             PORT, 
#                             trade_signal_live, 
#                             trade_signal_monitor_growth, 
#                             newsProviders, 
#                             m.symbol, 
#                             m.end_timestamp,
#                             time.localtime().tm_hour, 
#                             current_minute, 
#                             open_map[m.symbol], 
#                             m.close, 
#                             m.accumulated_volume, 
#                             m.vwap,                                                           
#                             cumulative_volume, 
#                             aggregates_per_second, 
#                             relative_volume_factor, 
#                             news_time_window_minutes, 
#                             trade_signal_limit, 
#                             open_map, 
#                             relative_volume_list_hashmap_hour, 
#                             INCREASE_FROM_OPEN, 
#                             STALE_THRESHOLD_MINUTES,
#                             real_time_positions,
#                             min_price_threshold, 
#                             max_price_threshold,
#                             low_float_threshold,
#                             price_spike_risk_threshold,
#                             investment_amount)
#                     )                                    
#         else:            
#             #Standard Relative Volume

#             cumulative_volume = volume_map[m.symbol]            
#             relative_volume = relative_volume_list_hashmap[m.symbol]

#             # TODO -> Sino tenemos un Relative Volume... estamos usando un valor por defecto(1000) esto no es preciso ni relativo al activo.... podriamos 
#             # Anlizar el R.V hour... es un dato secuendario pero es mejor que un dato completamente desconectado del sock en cuestion.... 
#             # Si el cumulative_volume es una tercera parte del R.V hour podriamos romarlo en cuenta.                 

#             if relative_volume == 0:
#                 relative_volume = 1000                 

#             relative_volume_factor = round(cumulative_volume / relative_volume , 2)
            
#             if relative_volume_factor >= RELATIVE_VOLUME_THRESHOLD and m.close >= ( yesterday_close_list_hashmap[m.symbol]):
#                 if m.symbol not in trade_signals_memory_hashmap:
                    
#                     trade_signals_memory_hashmap[m.symbol] = cumulative_volume

#                     #TODO -> Vamos a guardar a enviar el m.timeStamp del momento cuando se registro este grupo de agregaciones, la marca de tiempo.... 
#                     # Para poder comparar con la marca de tiempo que se guarda a nivel de TradeSignal... asi podremos entender cualquier desfase en el tiempo. 

#                     asyncio.create_task(
#                         process_trade_signal(
#                             PORT, 
#                             trade_signal_live, 
#                             trade_signal_monitor_growth, 
#                             newsProviders, 
#                             m.symbol, 
#                             m.end_timestamp,
#                             time.localtime().tm_hour, 
#                             current_minute, 
#                             open_map[m.symbol], 
#                             m.close, 
#                             m.accumulated_volume, 
#                             m.vwap,                                                           
#                             cumulative_volume, 
#                             aggregates_per_second, 
#                             relative_volume_factor, 
#                             news_time_window_minutes, 
#                             trade_signal_limit, 
#                             open_map, 
#                             relative_volume_list_hashmap_hour, 
#                             INCREASE_FROM_OPEN, 
#                             STALE_THRESHOLD_MINUTES,
#                             real_time_positions,
#                             min_price_threshold, 
#                             max_price_threshold,
#                             low_float_threshold,
#                             price_spike_risk_threshold,
#                             investment_amount)
#                     )                   

async def market_data_producer_offline(trade_queue: asyncio.Queue):

    total = 0

    for i in range(1, 3):
        # total += i
        # print(i)
        await trade_queue.put({
            "symbol": "CWH",
            "price": 20,
            "volume": 1000,
            "timestamp": 1728073164523,
            "conditions": [12,36, 41]
        })

async def market_data_producer(ws: WSClient, trade_queue: asyncio.Queue, quote_queue: asyncio.Queue, symbols: List[str]):

    print(f"\033[1;33mStarting Market Data Producer... \033[0m")              

    ws = WebSocketClient(api_key='hzZItvRA2Rfrri2XEjt2VSyMek9PC1Yu', subscriptions=symbols) 

    async def handle_msg(msgs: List[WebSocketMessage]):
        nonlocal trade_queue, quote_queue
        
        for m in msgs:

            if m.event_type == 'T':     

                await trade_queue.put({
                    "symbol": m.symbol,
                    "price": m.price,
                    "volume": m.size,
                    "timestamp": m.timestamp,
                    "conditions": m.conditions
                })   
            else: 
                await quote_queue.put({
                    "symbol": m.symbol,
                    "timestamp": m.timestamp,
                    "ask_price": m.ask_price,
                    "ask_size": m.ask_size
                })                

            # trade_count += 1                  
            # trade_count_total += 1

            # if time.time() - last_check_time >= 10:  # 10 segundos

            #     last_check_time = time.time()  # Actualizamos el tiempo de la última verificación

            #     current_minute = datetime.now().minute     
            #     print(f"Current Minute       = {current_minute}")    
            #     print(f"Trades per minute = {trade_count}")  
            #     print(f"Trades per minute = {trade_count_total}")  

            #     # print(f"Unix TimeStamp       = {unix_timestamp}")
            #     # print(format_unix_timestamp(unix_timestamp))
            #     # print(print_current_time())

            #     trade_count = 0 
                
            #     local_utc_timestamp_ms = int(time.time() * 1000)

            #     print(f"Local UTC = {local_utc_timestamp_ms - m.timestamp}" )
            #     print("   ")
            



    await ws.connect(handle_msg)    
    
# async def raw_trade_signal():
#     print(f"{print_current_time()} = 1")
#     conn = sqlite3.connect('histFinanData.db')
#     print(f"{print_current_time()} = 2")
#     cursor = conn.cursor()   

#     # await persist_trade_signal_raw(cursor, conn, "TSLA", 6, 0, 400, 5000, 500, 12) 
#     last_trade_price = client.get_last_trade("CWH").price
#     ask_price = client.get_last_quote("CWH").ask_price
#     conn.close()    
#     print(f"{print_current_time()} = END")    

async def put_order_interactive_brokers(client, ib, port, symbol, number):    

    print(f"{print_current_time()} = 1")
    PRE_ask_price = client.get_last_quote("CWH").ask_price

    ask_size = client.get_last_quote("CWH").ask_size

    bid_price = client.get_last_quote("CWH").bid_price
    bid_size = client.get_last_quote("CWH").bid_size  

    last_trade_data = client.get_last_trade("CWH")

    print(f"{print_current_time()} = END")

async def test(ib):
    print(f"{print_current_time()} = Test")

    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)

    await put_order_interactive_brokers(client, ib, 7497, "TSLA", 1)

    # await raw_trade_signal()

def process_trades_per_second(has_symbols):

    trades_by_second_map = {symbol: set() for symbol in has_symbols}

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    cursor.execute("SELECT second FROM RawTrades order BY second ASC")
    count = 0 
    init = datetime.now()

    # active_seconds = set()

    for row in cursor.fetchall():
        count += 1
        current_second = row[0]  # El segundo actual

        trades_by_second_map["STTK"].add(current_second)

    active_seconds_count = len(trades_by_second_map["STTK"])
    print(f"Total de segundos con actividad: {active_seconds_count} de 60")

    print(f"Tiempo de inicio: {init}")
    print(f"Tiempo actual   : {datetime.now()}")


    init = datetime.now()
    # for symbol in trades_by_second_map:
    #     trades_by_second_map[symbol] = set()
    
    timestamp_in_seconds = 1760378526193 // 1000

    second = timestamp_in_seconds % 60 

    print(init)         
    print(datetime.now()) 

    print(second)
    conn.close()
    
async def run_trading_strategy():

    ib = IB()

    PAPER_PORT_IBKR_GATEWAY = 4002         # Port used to connect to the IBKR Gateway Paper account.
    PORT_IBKR_GATEWAY = 4001               # Port used for real money trading IBKR - Gateway.
    PAPER_PORT = 7497                      # Port used to connect to the Paper account - Trader Workstation.
    PORT = 7496                            # Port used for real money trading using Trader Workstation.

    RELATIVE_VOLUME_THRESHOLD = 5          # This is the threshold for relative volume to trigger a trade. Ross Cameron recommends at least 5x relative volume.    
    TRADE_CAPITAL = 280                     # This is the budget allocated for a single trade.
    
    news_time_window_minutes = 2           # This is the time window in minutes to look for news related to the stock before executing a trade.    
    TRADE_SIGNAL_LIMIT = 20                # This is the limit of trade signals per symbol to avoid overtrading.    
    STALE_THRESHOLD_MINUTES = 4            # This variable basically defines how often a Trade Signal should be generated, i.e., within what time interval. It helps prevent overloading the system with extremely liquid assets.
    STOCKS_WITH_PREV_CLOSE = 10            # Maximum allowed previous-day closing price for stock selection. Used to filter stocks in SQL queries (e.g., close <= $10).

    #Risk Management Config

    INCREASE_FROM_OPEN = 5                 # This variable indicates the minimum percentage of growth a bullish candle should have to be considered.
    MAX_LOSS_TOLERANCE_PER_TRADE = 0.92    # This is the maximum loss tolerance per trade, expressed as a percentage of the budget. For example, 0.80 means 80% of the budget.    
    PRICE_SPIKE_RISK_THRESHOLD = 20        # Defines the maximum acceptable % increase in price over a short time frame(seconds). 
                                           # If a stock's price increases more than this threshold, it is considered too volatile or risky to enter.
    FLOAT_THRESHOLD = 50000000             # Maximum float value allowed for momentum Strategy

    # Low Float Config

    MIN_PRICE_THRESHOLD = 1               # Min price limits for trade validation. Price range used to filter valid assets after a TradeSignal(BUY). Also used to build the low_float dictionary.
    MAX_PRICE_THRESHOLD = 7                  # Max price limits for trade validation. Price range used to filter valid assets after a TradeSignal(BUY). Also used to build the low_float dictionary.
    LOW_FLOAT_THRESHOLD = 10000000            # Maximum float value allowed when building the low_float dictionary. Stocks below this threshold are more likely to experience extreme price movements.
    RELATIVE_VOLUME_THRESHOLD_LOW_FLOAT = 3  # This is the threshold for relative volume to trigger a trade. FOR Low Float Stocks.

    # High Short Interest Stocks

    SHORT_INTEREST_RATIO = 0.12

    # conn = sqlite3.connect('histFinanData.db')

    low_float_stocks_dict = {}
    high_short_interest_stocks  = {}
    stock_float_hashmap = {}

    # file_path = 'symbols.txt'
    # symbols = await get_stocks_from_file(file_path)

    # print(symbols)

    async with aiosqlite.connect('histFinanData.db') as conn:

    # cursor = conn.cursor()
        cursor = await conn.cursor()

        symbols = await get_stocks_in_range(cursor, FLOAT_THRESHOLD, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD)    
        # print(symbols)
        low_float_stocks_dict = await get_low_float_stocks(cursor, LOW_FLOAT_THRESHOLD, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD)   
        stock_float_hashmap = await query_all_stock_floats() 
        # print(stock_float_hashmap)

        high_short_interest_stocks = await get_filtered_stocks_short(
            cursor,
            max_float=LOW_FLOAT_THRESHOLD,
            min_short_percent=SHORT_INTEREST_RATIO,
            min_close=MIN_PRICE_THRESHOLD,
            max_close=LOW_FLOAT_THRESHOLD
        )            

    await ib.connectAsync('127.0.0.1', PAPER_PORT, clientId=0)

    trade_signal_queue = asyncio.Queue(maxsize=50000)

    trade_queue = asyncio.Queue(maxsize=50000)
    quote_queue = asyncio.Queue(maxsize=50000)

    ws = WSClient()

    # low_float_stocks_dict = get_low_float_stocks(LOW_FLOAT_THRESHOLD, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD)

    real_time_positions = {}
    get_current_positions(ib, real_time_positions)    


    initial_config(PAPER_PORT, TRADE_CAPITAL, len(low_float_stocks_dict), len(symbols), real_time_positions, RELATIVE_VOLUME_THRESHOLD, RELATIVE_VOLUME_THRESHOLD_LOW_FLOAT, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD, LOW_FLOAT_THRESHOLD, high_short_interest_stocks, SHORT_INTEREST_RATIO)   

    ask_map = {symbol: 0 for symbol in symbols}
    ask_size_map = {symbol: 0 for symbol in symbols}
    ask_map_timestamp = {symbol: 0 for symbol in symbols}

    trade_consumer_close_map = {symbol: 0 for symbol in symbols}
    trade_consumer_volume_map = {symbol: 0 for symbol in symbols}
    trade_consumer_open_map = {symbol: 0 for symbol in symbols}
    trade_consumer_open_map_timestamp = {symbol: 0 for symbol in symbols}    
    trade_per_minute_map = {symbol: 0 for symbol in symbols}
    trade_signals_memory_hashmap = {}

    # trade_consumer_close_map, trade_consumer_volume_map, trade_consumer_open_map, trade_consumer_open_map_timestamp, trade_per_minute_map, trade_signals_memory_hashmap

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
    # process_trades_per_second(symbols)

    # await market_data_producer(ws, trade_queue, create_subscription_list(symbols))

    await asyncio.gather(
            market_data_producer(ws, trade_queue, quote_queue, create_subscription_list(symbols)),
            trade_execution_consumer(1, trade_queue),
            quote_update_consumer(quote_queue, ask_map, ask_map_timestamp, ask_size_map),        
    )             
    # finally:
    #     print("Disconnecting from IB...")
    #     print(print_current_time())
    #     ib.disconnect()            

asyncio.run(run_trading_strategy())