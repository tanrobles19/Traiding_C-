from polygon import WebSocketClient
from polygon import RESTClient
from ib_insync import IB, Stock
from ib_insync.order import LimitOrder
from typing import List
import asyncio
import time
import csv
import aiosqlite
from datetime import datetime, timedelta, date, timezone
import pytz

from real_time_position_manager import check_and_alert_loss

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

def format_number(number):
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    elif number >= 1_000:
        return f"{number / 1_000:.1f}K"
    else:
        return str(number)    

def get_current_positions(ib, real_time_positions):
    positions = ib.positions()
    
    for pos in positions:

        symbol = pos.contract.symbol
        avg_cost = pos.avgCost
        
        real_time_positions[symbol] = avg_cost  

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

async def save_order_to_db(symbol, start_timestamp, avgFillPrice, status, tradeLog, orderType, totalQuantity, trade_signals_count, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_map_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close):    

    async with aiosqlite.connect('histFinanData.db') as conn:
        cursor = await conn.cursor()

        await cursor.execute('''
            INSERT INTO Orders (symbol, end_timestamp, start_timestamp, filledPrice, status, log, orderType, totalQuantity, tradeSignalsCount, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, print_current_time(), start_timestamp, avgFillPrice, status,  str(tradeLog), orderType, totalQuantity, trade_signals_count, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_map_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close))

        await conn.commit()    

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

async def has_existing_trade_signal_with_News(cursor, symbol):
    await cursor.execute('''
        SELECT COUNT(*) FROM TradeSignalsBuyPerSecond
        WHERE symbol = ? AND newsCount > 0
    ''', (symbol,))
    
    result = await cursor.fetchone()

    if result[0] == 0:
        return False 
    return True    

async def order_exists(cursor, symbol: str, status: str, order_type: str) -> bool:
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

def initial_config(version_code, port, investment_amount, low_float_stocks, symbols, positions, relative_volume, relative_volume_low_float, min_price, max_price, low_float, high_short_interest_stocks, SHORT_INTEREST_RATIO, INCREASE_FROM_OPEN, MAX_LOSS_TOLERANCE_PER_TRADE, PRICE_SPIKE_RISK_THRESHOLD):

    if port == 7497:
        print(" ")
        print(f"\033[1;33m-------------------------------------------------------------- \033[0m")          
        print(f"\033[1;33m|                        Paper Trading {version_code}                | \033[0m")          
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"\033[1;33m|\033[0m High Short-Interest Stocks: {len(high_short_interest_stocks)}                             \033[1;33m|\033[0m")     
        print(f"\033[1;33m|\033[0m Short Interest Radio      : {SHORT_INTEREST_RATIO}                           \033[1;33m|\033[0m")             
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Low Float Stocks: {low_float_stocks}")       
        print(f"  Low Float: {low_float}")
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Relative Volume           : {relative_volume}")       
        print(f"  Relative Volume Low Float : {relative_volume_low_float}")       
        print(f"  Price range               : [${min_price} - ${max_price}]")         
        print(f"  Capital per Trade         : ${investment_amount}")             
        print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
        print(f"  Risk Management Config:")                             
        print(f"  Minimum from Open      : {INCREASE_FROM_OPEN}")                             
        print(f"  Maximum Price Spike    : {PRICE_SPIKE_RISK_THRESHOLD}")                                             
        print(f"  Maximum Loss tolerance : {MAX_LOSS_TOLERANCE_PER_TRADE}")                                             
                
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

def print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]

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

async def insert_queue_behavior(cursor, conn, queue_id, timestamp, queue_pressure, number_trades):

    await cursor.execute("""
        INSERT INTO QueueBehavior (queue_id, timestamp, queue_pressure, number_trades)
        VALUES (?, ?, ?, ?)
    """, (queue_id, timestamp, queue_pressure, number_trades))
    
    await conn.commit()    

async def persist_trade_signal(cursor, conn, symbol, consumer_id, trade_activity_seconds, trade_signals_count, end_timestamp, open_price, open_map_timestamp, close, accumulated_volume, vwap, low_float, cumulative_volume, relative_volume_factor, aggregates_per_second, relative_volume_list_hashmap_hour, INCREASE_FROM_OPEN, isShortSqueeze, trade_id, trade_exchange, trade_trf_id):

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

    await cursor.execute('''
        INSERT INTO TradeSignalsBuyPerSecond (
            symbol, consumer_id, trade_activity_seconds, tradeSignalsCount, open, open_timestamp, close, last_trade_price, ask_price, ask_timestamp, accumulated_volume, low_float, vwap, volume,
            relative_volume, timestamp, averageDayVolume, purchasePrediction, aggregatesPerSecond, news_metadata, relative_volume_hour, timestamp_unix, local_utc_timestamp, trade_id, exchange, trf_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        symbol,
        consumer_id,
        trade_activity_seconds,
        trade_signals_count,
        open_price,  
        open_map_timestamp,
        close, 
        close,
        0,
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
        # format_unix_timestamp(end_timestamp),
        end_timestamp,        
        local_utc_timestamp_ms - end_timestamp,
        trade_id, 
        trade_exchange, 
        trade_trf_id
    ))

    tradeSignalId = cursor.lastrowid
    await conn.commit()
    
    return tradeSignalId, purchasePrediction    

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
        print("Volume")
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
            # timestamp_in_seconds = unix_timestamp // 1000
            # # Extracts the second within the current minute by calculating the 
            # # remainder when dividing the timestamp in seconds by 60 [timestamp_in_seconds % 60].         
            # trades_by_second_map_set[symbol].add(timestamp_in_seconds % 60 )  

            # if trade_queue.qsize() > queue_max_size:
            #     queue_max_size = trade_queue.qsize()
                
            # trade_count += 1                  
            # trade_count_total += 1

            # if trade_consumer_open_map[symbol] == 0:
            #     if condition_affects_ohlcv_component(trade_conditions, conditions, 0):
            #         trade_consumer_open_map_timestamp[symbol] = unix_timestamp
            #         trade_consumer_open_map[symbol] = trade_price        

            #         trade_consumer_close_map[symbol] = trade_price                  
            #         # Cuando se establece un Open se convierte en su close tambien. 

            # if condition_affects_ohlcv_v_p(trade_conditions, conditions, 1):
            #     trade_consumer_close_map[symbol] = trade_price                  

            # if condition_affects_ohlcv_v_p(trade_conditions, conditions, 2):
            #     trade_consumer_volume_map[symbol] += trade_volume
                
            # cumulative_volume = trade_consumer_volume_map[symbol]            
            # relative_volume = relative_volume_list_hashmap[symbol]         

            # if relative_volume == 0:
            #     relative_volume = 1000                  

            # relative_volume_factor = round(cumulative_volume / relative_volume , 2)

            # if symbol in low_float_stocks_dict:

            #     if relative_volume_factor >= relative_volume_low_float:       
                    
            #         if symbol not in trade_signals_memory_hashmap:    
            #             # print(f"LOW Symbol ={symbol} -> relative_volume_factor = {relative_volume_factor} trade_signals_memory_hashmap = {len(trade_signals_memory_hashmap)}")         
            #             trade_signals_memory_hashmap[symbol] = cumulative_volume

            #             record_number = await get_record_count_for_symbol(conn, cursor, symbol)
            #             exists = await order_exists(cursor, symbol, "Filled", "BUY")                

            #             if trade_consumer_open_map[symbol] == 0:                    
            #                 continue

            #             if record_number > trade_signal_limit:
            #                 continue

            #             if exists:                    
            #                 continue         

            #             if await has_existing_trade_signal_with_News(cursor, symbol) == False:
                                    
            #                 if await has_no_recent_trade_signal(cursor, symbol, trade_consumer_close_map[symbol], relative_volume_factor, stale_threshold_minutes_config):
                                    
            #                     active_seconds_count = len(trades_by_second_map_set[symbol]) 

            #                     tradeSignalId, purchasePrediction =  await persist_trade_signal(cursor, conn, symbol, consumer_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], trade_consumer_close_map[symbol], cumulative_volume, 10, stock_float_hashmap[symbol],
            #                     cumulative_volume, relative_volume_factor, {}, {}, increase_open, 0, trade_id, trade_exchange, trade_trf_id )                                

            #                     if purchasePrediction == "BUY":

            #                         print(f"symbol {symbol}  state -> {purchasePrediction} - LOW FLOAT")      
            #                         print(f"time = {print_current_time()}")               
            #                         print("   ")                    
            #                         print(f"\033[1;33mTRADE SIGNAL -> {symbol} \033[0m")       

            #                         if stock_float_hashmap[symbol] is not None and stock_float_hashmap[symbol] < low_float_threshold:
            #                             print(f"\033[1;31m     Low Float = {format_number(stock_float_hashmap[symbol])}\033[0m")  
            #                             print(f"     Time = {print_current_time()}")   

            #                         await trade_signal_queue.put({
            #                             "port": port,
            #                             "symbol": symbol,
            #                             "second": timestamp_in_seconds % 60,
            #                             "active_seconds_count": active_seconds_count,                                    
            #                             "trade_signals_count": trade_per_minute_map[symbol],
            #                             "timestamp": unix_timestamp,
            #                             "minute": current_minute,
            #                             "price": trade_consumer_close_map[symbol],
            #                             "hardcoded": 111,   # tu valor fijo
            #                             "cumulative_volume": cumulative_volume,
            #                             "extra": {},  # placeholder
            #                             "relative_volume_factor": relative_volume_factor,
            #                             "news_time_window_minutes": news_time_window_minutes,
            #                             "trade_signal_limit": trade_signal_limit,
            #                             "open_map": trade_consumer_open_map,
            #                             "open_map_timestamp": trade_consumer_open_map_timestamp[symbol],
            #                             "extra2": {},  # placeholder
            #                             "increase_open": increase_open,
            #                             "stale_threshold_minutes_config": stale_threshold_minutes_config,
            #                             "extra3": {},  # placeholder
            #                             "investment_amount": investment_amount,
            #                         })                                            
            # else:

            #     if relative_volume_factor >= RELATIVE_VOLUME_THRESHOLD:

            #         if symbol not in trade_signals_memory_hashmap:    
            #             trade_signals_memory_hashmap[symbol] = cumulative_volume

            #             record_number = await get_record_count_for_symbol(conn, cursor, symbol)
            #             exists = await order_exists( cursor, symbol, "Filled", "BUY")

            #             # await persist_trade_signal_raw(cursor, conn, symbol, consumer_id, time.localtime().tm_hour, current_minute, price, cumulative_volume, relative_volume_factor, {}, trade_consumer_open_map[symbol], record_number, exists, trade_signal_buffer)                 
                        
            #             if trade_consumer_open_map[symbol] == 0:                    
            #                 continue

            #             if record_number > trade_signal_limit:
            #                 continue

            #             if exists:                    
            #                 continue

            #             if await has_existing_trade_signal_with_News(cursor, symbol) == False:
                                    
            #                 if await has_no_recent_trade_signal(cursor, symbol, trade_consumer_close_map[symbol], relative_volume_factor, stale_threshold_minutes_config):

            #                     # stock_info = await query_stock_float_short_interest(symbol)   

            #                     active_seconds_count = len(trades_by_second_map_set[symbol])                                                                         

            #                     tradeSignalId, purchasePrediction =  await persist_trade_signal(cursor, conn, symbol, consumer_id, active_seconds_count, trade_per_minute_map[symbol], unix_timestamp, trade_consumer_open_map[symbol], trade_consumer_open_map_timestamp[symbol], trade_consumer_close_map[symbol], cumulative_volume, 10, stock_float_hashmap[symbol],
            #                     cumulative_volume, relative_volume_factor, {}, {}, increase_open, 0, trade_id, trade_exchange, trade_trf_id)                               
                                
            #                     if purchasePrediction == "BUY":

            #                         print(f"symbol {symbol}  state -> {purchasePrediction} ")      
            #                         print(f"time = {print_current_time()}")               
            #                         print("   ")                    
            #                         print(f"\033[1;33mTRADE SIGNAL -> {symbol} \033[0m")       
                                    
            #                         if stock_float_hashmap[symbol] is not None and stock_float_hashmap[symbol] < low_float_threshold:
            #                             print(f"\033[1;31m     Low Float = {format_number(stock_float_hashmap[symbol])}\033[0m")                                                        
            #                             print(f"     Time = {print_current_time()}")   

            #                         await trade_signal_queue.put({
            #                             "port": port,
            #                             "symbol": symbol,
            #                             "second": timestamp_in_seconds % 60,
            #                             "active_seconds_count": active_seconds_count,
            #                             "trade_signals_count": trade_per_minute_map[symbol],
            #                             "timestamp": unix_timestamp,
            #                             "minute": current_minute,
            #                             "price": trade_consumer_close_map[symbol],
            #                             "hardcoded": 111,   # tu valor fijo
            #                             "cumulative_volume": cumulative_volume,
            #                             "extra": {},  # placeholder
            #                             "relative_volume_factor": relative_volume_factor,
            #                             "news_time_window_minutes": news_time_window_minutes,
            #                             "trade_signal_limit": trade_signal_limit,
            #                             "open_map": trade_consumer_open_map,
            #                             "open_map_timestamp": trade_consumer_open_map_timestamp[symbol],
            #                             "extra2": {},  # placeholder
            #                             "increase_open": increase_open,
            #                             "stale_threshold_minutes_config": stale_threshold_minutes_config,
            #                             "extra3": {},  # placeholder
            #                             "investment_amount": investment_amount,
            #                         })
            #                         # await play_bell()                                              

            # if( consumer_id == 1 and current_minute != datetime.now().minute ):                  

            #     current_minute = datetime.now().minute     
            #     print(f"Current Minute    = {current_minute}")    
            #     print(f"Trades per MINUTE = {trade_count}")  
            #     print(f"Total Trades      = {trade_count_total}")  

            #     await insert_queue_behavior(cursor, conn, "trade_queue", print_current_time(), queue_max_size, trade_count)                

            #     trade_count = 0 
            #     queue_max_size = 0      

            #     trade_consumer_close_map.clear()
            #     trade_consumer_volume_map.clear()
            #     trade_consumer_open_map.clear()
            #     trade_consumer_open_map_timestamp.clear()
            #     trade_per_minute_map.clear()
            #     trade_signals_memory_hashmap.clear()

            #     trades_by_second_map_set.clear()

            #     trade_consumer_close_map = {symbol: 0 for symbol in symbols}
            #     trade_consumer_volume_map = {symbol: 0 for symbol in symbols}
            #     trade_consumer_open_map = {symbol: 0 for symbol in symbols}
            #     trade_consumer_open_map_timestamp = {symbol: 0 for symbol in symbols}    
            #     trade_per_minute_map = {symbol: 0 for symbol in symbols}
            #     trade_signals_memory_hashmap = {}    

            #     trades_by_second_map_set = {symbol: set() for symbol in symbols}  

            #     relative_volume_list_hashmap = await get_relative_volume(get_current_hour(), get_current_minute(), get_am_pm(), cursor)                    

                
            #     local_utc_timestamp_ms = int(time.time() * 1000)

            #     print(f"Local UTC = {local_utc_timestamp_ms - unix_timestamp}" )
            #     print("   ")      

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

async def trade_signal_consumer(ib, id, trade_signal_queue, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, real_time_positions):

    print(f"Trade signal worker id = {id}")

    while True:
        signal = await trade_signal_queue.get()

        symbol = signal["symbol"]

        await process_trade_signal(
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
            signal["investment_amount"]
        )

        trade_signal_queue.task_done()        

async def process_trade_signal(ib, PORT, symbol, second, active_seconds_count, trade_signals_count, end_timestamp, minute, close, accumulated_volume, cumulative_volume, aggregates_per_second, 
    relative_volume_factor, news_time_window_minutes, TRADE_SIGNAL_LIMIT, open_map, open_map_timestamp, relative_volume_list_hashmap_hour, INCREASE_FROM_OPEN, stale_threshold_minutes, real_time_positions, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, investment_amount):                  

    await buyStock(ib, PORT, symbol, second, active_seconds_count, trade_signals_count, close, real_time_positions, investment_amount, open_map, open_map_timestamp, INCREASE_FROM_OPEN, min_price_threshold, max_price_threshold, low_float_threshold, price_spike_risk_threshold, close)                                           

async def buyStock(ib, PORT, symbol, second, active_seconds_count, trade_signals_count, polygon_second_close, real_time_positions, investment_amount, open_map, open_map_timestamp, INCREASE_FROM_OPEN, MIN_PRICE_THRESHOLD, MAX_PRICE_THRESHOLD, LOW_FLOAT_THRESHOLD, PRICE_SPIKE_RISK_THRESHOLD, last_trade_price):

    print("     Last trade price:", last_trade_price)

    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)
        
    quote = client.get_last_quote(symbol)

    ask_timestamp = "1761235865389"
    ask_price = quote.ask_price

    percentage = 0.33
    elapsed_seconds = second - open_map_timestamp
    elapsed_seconds_33_percent = elapsed_seconds * percentage

    stock = Stock(symbol, 'SMART', 'USD')

    totalQuantity = determine_purchase_quantity(investment_amount, ask_price)    

    print(f"     Ask: {ask_price}")    
    print(f"     Total Quantity: {totalQuantity}")    

    ask_size = 1

    bid_price = 1
    bid_size = 1

    if active_seconds_count < elapsed_seconds_33_percent:

        log_text = f"LOW Activity - second = {second} - Active Seconds Count = {active_seconds_count}  <  {elapsed_seconds_33_percent} "
        print(" ")          
        print(f"\033[1;31m 🔻 LOW ACTIVITY 🔻 -> {symbol} \033[0m")                    
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
        print(" ")
        print(f"\033[1;31m 🔻 Float menor a 5M 🔻 -> {symbol} \033[0m")    
        print(" ")        

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
        print(" ")
        print(f"\033[1;31m 🔻 Ask price == 0 🔻 -> {symbol} \033[0m")    
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

    if ask_price < MIN_PRICE_THRESHOLD or ask_price > MAX_PRICE_THRESHOLD:

        log_text = f"Ask price exceeded configured thresholds [${MIN_PRICE_THRESHOLD} to ${MAX_PRICE_THRESHOLD}]"
        print(" ")
        print(f"\033[1;31m 🔻 Ask price exceeded configured thresholds 🔻 -> {symbol} \033[0m")     
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
                print("Put Limit Order BUY")
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
                    open_price=open_map[symbol], 
                    open_map_timestamp=open_map_timestamp,
                    last_trade_price=last_trade_price, 
                    last_trade_timestamp="  ",
                    polygon_second_close=polygon_second_close)    

                trade = ib.placeOrder(stock, order)

                while not trade.isDone():
                    await asyncio.sleep(0.1)
                
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
                    open_price=open_map[symbol], 
                    open_map_timestamp=open_map_timestamp,
                    last_trade_price=last_trade_price, 
                    last_trade_timestamp=" ",
                    polygon_second_close=polygon_second_close)

                if trade.orderStatus.status == "Filled":
                    real_time_positions[symbol] = trade.orderStatus.avgFillPrice
                    print(" ")
                    print(" 💹 UPDATED Real Time Positions after BUY 💹")     
                    print(f"Real Time Positions: {real_time_positions}")     
                    print(" ")
            else:
                
                log_text = f"Too risky: price increased more than {PRICE_SPIKE_RISK_THRESHOLD}% -> percentage_increase: {percentage_increase}"
                print(" ")
                print(f"\033[1;31m 🔻 Too risky: price increased more than 🔻 -> {symbol} \033[0m")                     
                print(" ")

                await save_order_to_db(symbol, print_current_time(), 0, "Not executed", log_text, "BUY", 
                totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, open_price=open_price, open_map_timestamp=open_map_timestamp, 
                last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close)                

        else:

            log_text = f"Price increase less than %{INCREASE_FROM_OPEN}"
            print(" ")            
            print(f"\033[1;31m 🔻 Price increase less than 🔻 -> {symbol} \033[0m")     
            print(" ")
            await save_order_to_db(symbol, print_current_time(), 0, "Not executed", log_text, "BUY", 
            totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, open_price=open_map[symbol], open_map_timestamp=open_map_timestamp, 
            last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close)

    else:
        
        if last_trade_price == open_map[symbol]:       
            print(" ")  
            print(f"\033[1;31m 🔻 Doji Candle 🔻 -> {symbol} \033[0m")     
            print(" ")
            await save_order_to_db(symbol, print_current_time(), 0, "Not executed", "Doji Candle", "BUY", 
            totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, open_price=open_map[symbol], open_map_timestamp=open_map_timestamp,
            last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close)            
        else:    
            print(" ")            
            print(f"\033[1;31m 🔻 Bearish Candle 🔻 ->{symbol} \033[0m")     
            print(" ")
            await save_order_to_db(symbol, print_current_time(), 0, "Not executed", "Bearish Candle", "BUY", 
            totalQuantity, trade_signals_count, ask_price=ask_price, ask_timestamp=ask_timestamp, ask_size=ask_size, bid_price=bid_price, bid_size=bid_size, 
            open_price=open_map[symbol], open_map_timestamp=open_map_timestamp, last_trade_price=last_trade_price, last_trade_timestamp=" ", polygon_second_close=polygon_second_close)    

async def market_data_producer(ws: WSClient, trade_queue, symbols: List[str]):

    print(f"\033[1;33mStarting Market Data Producer... \033[0m")              

    ws = WebSocketClient(api_key='hzZItvRA2Rfrri2XEjt2VSyMek9PC1Yu', subscriptions=symbols) 

    trade_count =  0
    trade_count_total = 0
    last_check_time = time.time()  # Actualizamos el tiempo de la última verificación

    async def handle_msg(msgs: List[WebSocketMessage]):
        nonlocal trade_queue, trade_count, trade_count_total, last_check_time
        
        for m in msgs:

            if m.event_type == 'T':   

                await trade_queue.put({
                    "symbol": m.symbol,
                    "price": m.price,
                    "volume": m.size,
                    "timestamp": m.timestamp,
                    "conditions": m.conditions,
                    "id": m.id,
                    "exchange": m.exchange,
                    "trf_id": m.trf_id                                                            
                })   

            trade_count += 1                  
            trade_count_total += 1

            if time.time() - last_check_time >= 10:  # 10 segundos

                last_check_time = time.time()  # Actualizamos el tiempo de la última verificación

                current_minute = datetime.now().minute     
                # print(f"Current Minute       = {current_minute}")    
                print(f"Trades per minute = {trade_count}")  
                print(f"Trades per minute = {trade_count_total}")  

                # print(f"Unix TimeStamp       = {unix_timestamp}")
                # print(format_unix_timestamp(unix_timestamp))
                # print(print_current_time())

                trade_count = 0 
                
                local_utc_timestamp_ms = int(time.time() * 1000)

                print(f"Local UTC = {local_utc_timestamp_ms - m.timestamp}" )
                print("   ")

            
    await ws.connect(handle_msg)      

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

            # trade_signal_consumer(ib, "worker-1", trade_signal_queue, min_price_threshold = MIN_PRICE_THRESHOLD, max_price_threshold = MAX_PRICE_THRESHOLD, low_float_threshold = LOW_FLOAT_THRESHOLD, price_spike_risk_threshold = PRICE_SPIKE_RISK_THRESHOLD, real_time_positions=real_time_positions)
            )      

asyncio.run(run_trading_strategy())