from polygon import WebSocketClient
from typing import List
import asyncio
import time
from datetime import datetime, timedelta, date, timezone

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

def get_current_minute():
    return int(datetime.now().strftime("%M"))

async def get_stocks_from_file(file_path):
    # Lee el archivo y evalúa el contenido (si está en formato lista como mencionas)
    with open(file_path, 'r') as file:
        symbols = file.read().strip()

    # Convierte el string en una lista de símbolos
    symbols_list = eval(symbols)

    return symbols_list

def create_subscription_list(tickers):
    subscriptions = [f"T.{ticker}" for ticker in tickers]
    subscriptionQ = [f"Q.{ticker}" for ticker in tickers]
    finalList = subscriptions + subscriptionQ
    # print(finalList)
    return finalList

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

async def market_data_producer(ws: WSClient, trade_queue, quote_queue, symbols: List[str]):

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
            
    await ws.connect(handle_msg)      

async def run_trading_strategy():

    file_path = 'symbols.txt'
    symbols = await get_stocks_from_file(file_path)    

    trade_queue = asyncio.Queue(maxsize=50000)
    quote_queue = asyncio.Queue(maxsize=50000)

    ask_map = {symbol: 0 for symbol in symbols}
    ask_size_map = {symbol: 0 for symbol in symbols}
    ask_map_timestamp = {symbol: 0 for symbol in symbols}    

    print(len(symbols))

    ws = WSClient()

    print(" ")
    print(f"\033[1;33m-------------------------------------------------------------- \033[0m")          
    print(f"\033[1;33m|                        Paper Trading  2                    | \033[0m")          
    print(f"\033[1;33m|\033[0m                                                            \033[1;33m|\033[0m")     
    print(f"  Subscriptions: {len(symbols)}")    


    # await market_data_producer(ws, create_subscription_list(symbols))
    await asyncio.gather(
            market_data_producer(ws, trade_queue, quote_queue, create_subscription_list(symbols)),
            trade_execution_consumer(1, trade_queue),
            quote_update_consumer(quote_queue, ask_map, ask_map_timestamp, ask_size_map),        
    )      

asyncio.run(run_trading_strategy())