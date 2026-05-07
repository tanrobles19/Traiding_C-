from datetime import datetime, timedelta, date, timezone
from colorama import Fore, Style, init
from prettytable import PrettyTable
import asyncio
from ib_insync import *
from ib_insync import IB, Stock
from polygon import RESTClient
import sqlite3
import mysql.connector
import os
from get_float import get_float
from get_previous_close import getPreviousClose
from relative_volume_ratio import getRelativeVolumeFactor
from fetch_historycal_data_to_db import getHistoricalData
from clean_db import clear_all_tables
from clean_db import clear_day_work_tables
from clean_db import clear_intradia_tables
from trade_signals_query import show_trade_signals
from select_table import show_tables

def format_number(number):
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    elif number >= 1_000:
        return f"{number / 1_000:.1f}K"
    else:
        return str(number)   

def to_percentage(value):
    try:
        return f"{float(value) * 100:.2f}%"
    except (ValueError, TypeError):
        return "N/A"        

def format_unix_timestamp(timestamp_ms):

    timestamp_s = timestamp_ms / 1000.0
    
    current_time = datetime.utcfromtimestamp(timestamp_s)
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")
    
    return formatted_time[:-3]   

def has_place_order_sell_off(symbol: str) -> bool:

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()
    
    query = """
        SELECT 1 FROM Orders
        WHERE symbol = ? AND orderType = 'placeOrderSellOff'
        LIMIT 1
    """
    cursor.execute(query, (symbol,))
    result = cursor.fetchone()
    
    conn.close()
    return result is not None

def range_order_exists(symbol, range_sell):
    try:
        conn = sqlite3.connect('histFinanData.db')
        cursor = conn.cursor()        
            
        query = """
        SELECT 1 
        FROM Orders
        WHERE symbol = ? AND range_sell = ? AND status = 'Processing'
        LIMIT 1;
        """
        cursor.execute(query, (symbol, range_sell))
        
        # Verificar si existe al menos un registro
        result = cursor.fetchone()
        return result is not None

    except sqlite3.Error as e:
        return False

    finally:
        if conn:
            conn.close()

def persist_trade_signal_raw(symbol, close, bid_price, bot_price, range_value):

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()    

    purchasePrediction = "RAW_SIGNAL"

    cursor.execute('''
        INSERT INTO TradeSignalSell (
            symbol, close, bid_price, bot_price, range, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        symbol,
        close, 
        bid_price, 
        bot_price,
        range_value,
        print_current_time()
    ))

    conn.commit()
    conn.close()

def order_exists_by_range(symbol, status, orderType):
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()
    
    query = """
    SELECT range_sell FROM Orders
    WHERE symbol = ? AND status = ? AND orderType = ?
    ORDER BY range_sell DESC
    LIMIT 1
    """
    
    cursor.execute(query, (symbol, status, orderType))
    record = cursor.fetchone()
    
    conn.close()
    
    return record[0] if record else None

def order_exists(symbol, status, orderType):

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()
    
    query = """
    SELECT EXISTS(
        SELECT 1 FROM Orders
        WHERE symbol = ? AND status = ? AND orderType = ?
    )
    """
    
    cursor.execute(query, (symbol, status, orderType))
    exists = cursor.fetchone()[0]  # 1 si existe, 0 si no
    
    conn.close()
    
    return bool(exists)

def check_and_take_profits(symbol, real_time_positions, MAX_LOSS_TOLERANCE_PER_TRADE, port, ib, close, bot_price):

    # if m.symbol in real_time_positions:

    #     bot_price = real_time_positions[m.symbol]

    #     if m.close >= bot_price * 1.10:

    #         if port == 7497: # Avoid sales in Real account
    asyncio.create_task(sellStock(ib, symbol, real_time_positions, close, bot_price))

async def sellStock(ib, symbol, real_time_positions, polygon_second_close, bot_price):
    
    if await has_active_sell_order(ib, symbol) == True:
        print(f"Ya existe una orden de venta activa para {symbol}.")

    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)         

    stock = Stock(symbol, 'SMART', 'USD')    

    positions = ib.positions()
    positionSize = 0

    for pos in positions:
        if pos.contract.symbol == symbol:
            positionSize = int(pos.position)
            break

    if positionSize == 0:
        return   

    bid_price_validation = client.get_last_quote(symbol).bid_price      

    persist_trade_signal_raw(symbol, polygon_second_close, bid_price_validation, bot_price, "not")                      

    if bid_price_validation >= bot_price * 1.10:    

        if order_exists(symbol, "Filled", "SELL"):

            range_sell = order_exists_by_range(symbol, "Filled", "SELL")
            # print(f"symbol ----> {symbol}")
            
            #The increase is calculated in 10% increments.
            range_sell = range_sell + 10      

            if not range_order_exists(symbol, range_sell):

                if polygon_second_close >= ( bot_price * (1 + range_sell / 100)):

                    persist_trade_signal_raw(symbol, polygon_second_close, bid_price_validation, bot_price, range_sell)            

                    print("")                        
                    porcentaje_aumento = ((polygon_second_close - bot_price) / bot_price) * 100
                    print(f"💹  ALERT: {symbol} is increasing  more that ({porcentaje_aumento:.2f}%)")
                    print(f"Current Price: {polygon_second_close}, Bot Price: {bot_price}")
                    print(f"range_sell = {range_sell}")

                    #The value of the positions has already exceeded 20%, so we will start selling 5% of my positions.            
                    FIVE_PERCENT = 0.05

                    quantity_to_sell = int(positionSize * 0.05)  

                    if quantity_to_sell > 0:

                        start_timestampTemp = print_current_time()
                        save_order_to_db_sell(symbol, start_timestampTemp, 0, "Processing", "log", "SELL", 0, ask_price=0, ask_size=0, bid_price=0, bid_size=0, open_price=1, last_trade_price=0, polygon_second_close=polygon_second_close, range_sell=range_sell)

                        bid_price = client.get_last_quote(symbol).bid_price
                        limit_price = client.get_last_quote(symbol).ask_price
                        start_timestamp = print_current_time()

                        order = LimitOrder('SELL', quantity_to_sell, bid_price, outsideRth=True)

                        trade = ib.placeOrder(stock, order)

                        while not trade.isDone():
                            await asyncio.sleep(0.5)

                        new_qty = positionSize - quantity_to_sell
                        if new_qty > 0:
                            print(f" Quedan {new_qty} acciones -> {symbol}")
                        else:
                            print("real_time_positions.pop 1")
                            real_time_positions.pop(symbol, None)
                
                        save_order_to_db_sell(symbol, start_timestamp, trade.orderStatus.avgFillPrice, trade.orderStatus.status, trade, "SELL", quantity_to_sell, ask_price=limit_price, ask_size=0, bid_price=bid_price, bid_size=0, open_price=1, last_trade_price=0, polygon_second_close=polygon_second_close, range_sell=range_sell)
                        # print(trade.orderStatus)

                        return quantity_to_sell

            else:

                # print(f"Current range = {range_sell - 5}")
                # print(f"Trying to reach = {range_sell}")

                pullback_tolerance = bot_price * ( 1 + (range_sell - 5) / 100 )
                # print(pullback_tolerance)

                # if(polygon_second_close < pullback_tolerance):
                #     print(f"Current Price = {polygon_second_close} - pullback = {pullback_tolerance}")
                    # await sellOffStock(ib, symbol, real_time_positions, polygon_second_close)

                    #Cuando baja no lo vamos a ejecutar para dejarlo que llegue hasta donde el momentum le diga... al final si se desploma el proceso de 
                    # check_and_alert_loss lo va manejar.

                #When a stock has risen by increments—let’s say it climbed 5%, then 10%, then 15%, and so on up to maybe 30% 
                #But then it starts losing momentum and doesn’t reach the next level, say 35%, and instead it falls back to 28%, 27%, or 25%, 
                # that’s called a pullback or a retracement.”

                #The stock hit a peak around 30% up from your entry point, but then it started to pull back and retrace some of those gains. 
                # It didn’t have enough momentum to push higher, and now it’s in a retracement phase.            

        else:

            #The initial sale range is 10%.
            range_sell = 10

            if not range_order_exists(symbol, range_sell):

                # FIRST TIME
                start_timestampTemp = print_current_time()
                save_order_to_db_sell(symbol, start_timestampTemp, 0, "Processing", "log", "SELL", 0, ask_price=0, ask_size=0, bid_price=0, bid_size=0, open_price=1, last_trade_price=0, polygon_second_close=polygon_second_close, range_sell=range_sell)

                print("")                        
                porcentaje_aumento = ((polygon_second_close - bot_price) / bot_price) * 100
                print(f"💹  ALERT: {symbol} is increasing  more that ({porcentaje_aumento:.2f}%)")
                print(f"Current Price: {polygon_second_close}, Bot Price: {bot_price}")      

                #The value of the positions has already exceeded 10%, so we will start selling 5% of my positions.            
                FIVE_PERCENT = 0.05

                quantity_to_sell = int(positionSize * FIVE_PERCENT)  

                bid_price = client.get_last_quote(symbol).bid_price
                limit_price = client.get_last_quote(symbol).ask_price
                start_timestamp = print_current_time()

                print(f"quantity_to_sell = {quantity_to_sell}")
                order = LimitOrder('SELL', quantity_to_sell, bid_price, outsideRth=True)

                trade = ib.placeOrder(stock, order)

                while not trade.isDone():
                    await asyncio.sleep(0.5)

                new_qty = positionSize - quantity_to_sell

                print(new_qty)
                if new_qty > 0:
                    print(f" Quedan {new_qty} acciones -> {symbol}")
                else:
                    print("real_time_positions.pop 2")
                    real_time_positions.pop(symbol, None)            

                save_order_to_db_sell(symbol, start_timestamp, trade.orderStatus.avgFillPrice, trade.orderStatus.status, trade, "SELL", quantity_to_sell, ask_price=limit_price, ask_size=0, bid_price=bid_price, bid_size=0, open_price=1, last_trade_price=0, polygon_second_close=polygon_second_close, range_sell=range_sell)

                return quantity_to_sell        

def check_and_alert_loss(symbol, close, real_time_positions, port, ib):

    # if m.symbol in real_time_positions:
    #     bot_price = real_time_positions[m.symbol]

    #     if m.close < bot_price * MAX_LOSS_TOLERANCE_PER_TRADE:                                                
    #     # if m.close <= bot_price:
    #         print("")                        
    #         porcentaje_caida = ((bot_price - m.close) / bot_price) * 100
    #         print(f"🔻 ALERTA: {m.symbol} ha caído más de ({porcentaje_caida:.2f}%)")
    #         print(f"Precio actual: {m.close}, Precio de compra: {bot_price}")      

    # if port == 7497: # Avoid sales in Real account
    asyncio.create_task(sellOffStock(ib, symbol, real_time_positions, close))      

async def sellOffStock(ib, symbol, real_time_positions, polygon_second_close):
    
    if has_place_order_sell_off(symbol):
        print(f"✅ Existe una orden 'placeOrderSellOff' para este símbolo = {symbol}")
        return

    save_order_to_db(symbol, print_current_time(), 0, " ", "Processing", "placeOrderSellOff", 0, ask_price=0, ask_size=0, bid_price=0, bid_size=0, open_price=1, last_trade_price=0, polygon_second_close=0)        

    if await has_active_sell_order(ib, symbol) == True:
        print(f"Ya existe una orden de venta activa para {symbol}.")

    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)                    
    stock = Stock(symbol, 'SMART', 'USD')

    positions = ib.positions()
    quantity_to_sell = 0

    for pos in positions:
        if pos.contract.symbol == symbol:
            quantity_to_sell = int(pos.position)
            break

    if quantity_to_sell == 0:
        # print(f"No shares to sell for {symbol}")
        return    

    bid_price = client.get_last_quote(symbol).bid_price
    limit_price = client.get_last_quote(symbol).ask_price
    start_timestamp = print_current_time()

    order = LimitOrder('SELL', quantity_to_sell, bid_price, outsideRth=True)

    trade = ib.placeOrder(stock, order)

    while not trade.isDone():
        await asyncio.sleep(0.5)

    # print("Order Status: ")    
    save_order_to_db(symbol, start_timestamp, trade.orderStatus.avgFillPrice, trade.orderStatus.status, trade, "SELL", quantity_to_sell, ask_price=limit_price, ask_size=0, bid_price=bid_price, bid_size=0, open_price=1, last_trade_price=0, polygon_second_close=polygon_second_close)
    del real_time_positions[symbol]        
    print(real_time_positions)                       

def save_order_to_db_sell(symbol, start_timestamp, avgFillPrice, status, tradeLog, orderType, totalQuantity, ask_price, ask_size, bid_price, bid_size, open_price, last_trade_price, polygon_second_close, range_sell):    

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()    
    cursor.execute('''
        INSERT INTO Orders (symbol, end_timestamp, start_timestamp, filledPrice, status, log, orderType, totalQuantity, ask_price, ask_size, bid_price, bid_size, open_price, last_trade_price, polygon_second_close, range_sell)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, print_current_time(), start_timestamp, avgFillPrice, status,  str(tradeLog), orderType, totalQuantity, ask_price, ask_size, bid_price, bid_size, open_price, last_trade_price, polygon_second_close, range_sell))

    conn.commit()
    conn.close()

def save_order_to_db(symbol, start_timestamp, avgFillPrice, status, tradeLog, orderType, totalQuantity, ask_price, ask_size, bid_price, bid_size, open_price, last_trade_price, polygon_second_close):    

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()    
    cursor.execute('''
        INSERT INTO Orders (symbol, end_timestamp, start_timestamp, filledPrice, status, log, orderType, totalQuantity, ask_price, ask_size, bid_price, bid_size, open_price, last_trade_price, polygon_second_close)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, print_current_time(), start_timestamp, avgFillPrice, status,  str(tradeLog), orderType, totalQuantity, ask_price, ask_size, bid_price, bid_size, open_price, last_trade_price, polygon_second_close))

    conn.commit()
    conn.close()

async def has_active_sell_order(ib, symbol: str) -> bool:

    open_trades = await ib.reqCompletedOrdersAsync()
        # open_trades = await ib.reqAllOpenOrdersAsync()

    for trade in open_trades:

        print(trade)

        if ( trade.contract.symbol.upper() == symbol.upper()
            and trade.order.action == 'SELL' and trade.orderStatus.status in ('PreSubmitted', 'Submitted') ):
            print(f"Cancelando orden de venta para {symbol}...")
            ib.cancelOrder(trade.order)
            return True
            






    return False      

async def  print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]    

def tradeSignalQuery():

    # conn = sqlite3.connect('histFinanData.db')
    # cursor = conn.cursor()  

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    
    cursor = db_connection.cursor()    

    symbol = input("Symbol? ").upper()

    # Seleccionamos todas las columnas de la tabla, filtrando por el símbolo
    cursor.execute("SELECT * FROM TradeSignalsBuyPerSecond WHERE symbol = ?", (symbol,))

    conn.commit()
    rows = cursor.fetchall()

    # Definir los nombres de las columnas para que coincidan con el orden en la tabla
    column_names = [
        'ID', 'Consumer ID', 'Symbol', 'Trade-S', 'Trades-#', 'Unix Timestamp', 'Local UTC', 'Ask T', 'Ask Price', 'Open', 'Open T', 'Volume', 
        'Relative V', 'Last Price', 'Close', 'Purchase P', 'Low Float', 'Timestamp', 'News #', 'Attempts Count', 'News Metadata', 'Timestamp News', 
        'VWAP', 'Accumulated V', 'Average Day V', 'Aggregates Per S', 'Relative Volume H', 'trade_id', 'exchange', 'trf_id'
    ]


    # Iterar sobre los resultados y mostrar cada fila como una lista
    for row in rows:
        print(" ")
        print(Fore.YELLOW + f"--- Trade Signal: {row[2]} ---" + Fore.RESET)  # Restablecer color después del símbolo
        print(" ")
        print(f"Unix Timestamp = {row[5]} to {format_unix_timestamp(int(row[5]))}")
        print(" ")
        for i, col_name in enumerate(column_names):            
            print(f"{col_name}= {Fore.YELLOW}{row[i]}{Fore.RESET}")  # Solo el valor en amarillo        
        print("-" * 50)  # Separador para las siguientes entradas



    cursor.execute("SELECT * FROM Orders WHERE symbol = ?", (symbol,))

    conn.commit()
    rows = cursor.fetchall()

    # Definir los nombres de las columnas para que coincidan con el orden en la tabla
    orders_column_names = [
        'ID', 'Symbol', 'Start Timestamp', 'End Timestamp', 'Filled Price', 'Status', 'Order Type', 'Total Quantity', 
        'Trade Signals Count', 'Range Sell', 'Bid Price', 'Ask Price', 'Ask Timestamp', 'Polygon Second Close', 
        'Last Trade Price', 'Last Trade Timestamp', 'Open Price', 'Open Timestamp', 'Bid Size', 'Ask Size', 'Log'
    ]

    for row in rows:
        print(" ")
        print(Fore.YELLOW + f"--- Order: {row[1]} ---" + Fore.RESET) 
        print(" ")
        for i, col_name in enumerate(orders_column_names):
            print(f"{col_name}= {Fore.YELLOW}{row[i]}{Fore.RESET}")  
        print("-" * 50) 

    conn.close()

async def cleanDayDataBaseData():
    clear_intradia_tables()

async def processDataForTomorrow():

    question = input("Process data for tomorrow? ").upper()

    if question == 'YES':
        
        clear_day_work_tables()        
        getPreviousClose()       
        get_float()         
        getHistoricalData()    
        getRelativeVolumeFactor()

def checkRelativeVolumeRatioHour():

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )
    

    symbol = input("Symbol? ").upper()

    if symbol:
        query = """
        SELECT * FROM RelativeVolumeRatioHour WHERE symbol = %s
        """
        mysql_cursor = db_connection.cursor()
        mysql_cursor.execute(query, (symbol,))
        rows = mysql_cursor.fetchall()      

        # Usar PrettyTable para mostrar los resultados
        table = PrettyTable()
        
        # Definir los nombres de las columnas
        table.field_names = ["id", "symbol", "hour", "amPm", "relative_volume"]

        # Agregar las filas a la tabla
        for row in rows:
            table.add_row(row)

        # Imprimir la tabla
        print(table)

        # Cerrar el cursor y la conexión
    mysql_cursor.close()
    db_connection.close()    



async def getShortSqueezeCandidates():

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    
    mysql_cursor = db_connection.cursor()

    print(Fore.CYAN + "Short Squeeze Candidates")
    print(Style.RESET_ALL)    
    print( Fore.YELLOW + "-" * 50)

    query = """
        SELECT ticker, close, float_value, short_percent_float
        FROM Stocks
        WHERE float_value < 10000000
            AND short_percent_float > 0.1 ORDER BY short_percent_float DESC;
    """
    mysql_cursor.execute(query)

    rows = mysql_cursor.fetchall()

    print(f"{'Symbol':<10} {'Close':<10} {'Float':<10} {'Short Interest':<15}")
    print("-" * 50)
    print(Style.RESET_ALL)        

    for row in rows:
        
        if row[2] <= 4000000 and row[2] > 500000 and row[3] > 0.20:            
            print( Fore.RED + f"{row[0]:<10} ${row[1]:<9} { format_number(row[2]):<14} {to_percentage(row[3]):<20}")
            print(Style.RESET_ALL)                    
        else:
            print(f"{row[0]:<10} ${row[1]:<9} { format_number(row[2]):<14} {to_percentage(row[3]):<20}")

    mysql_cursor.close()
    db_connection.close()    

async def has_active_sell_order(ib) -> bool:
    print("-" * 120)

    open_trades = await ib.reqCompletedOrdersAsync(apiOnly=True) 

    count = 0

    print("Completed Order:")     
    print(" ")           

    for trade in open_trades:

        count = count + 1

        symbol = trade.contract.symbol
        action = trade.order.action
        status = trade.orderStatus.status
        lmt_price = trade.order.lmtPrice
        total_quantity = trade.order.totalQuantity
        order_id = trade.order.orderId
        
        print(f"   {count:<10} {symbol:<10} | Action: {action:<5} | Status: {status:<12} | "
                f"Price: {lmt_price:<8} | Quantity: {total_quantity:<5} | Order ID: {order_id}")

    open_trades = await ib.reqAllOpenOrdersAsync()   
    print("Open Orders: ")      
    print(" ")      

    for trade in open_trades:

        symbol = trade.contract.symbol
        action = trade.order.action
        status = trade.orderStatus.status
        lmt_price = trade.order.lmtPrice
        total_quantity = trade.order.totalQuantity
        order_id = trade.order.orderId
        
        print(f"Symbol: {symbol:<10} | Action: {action:<5} | Status: {status:<12} | "
                f"Price: {lmt_price:<8} | Quantity: {total_quantity:<5} | Order ID: {order_id}")               

    print("-" * 120)


    question = input("Cancel Orders? ")

    if question == 'yes':

        open_trades = await ib.reqAllOpenOrdersAsync()       

        for trade in open_trades:

            print(f"Cancelling order for {trade.contract.symbol}...")
            ib.cancelOrder(trade.order)

    return False 

def get_relative_volume(hour, minute, am_pm, symbol):

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    
    mysql_cursor = db_connection.cursor()

    mysql_cursor.execute('''
        SELECT `symbol`, `relative_volume`
        FROM `RelativeVolumeRatio`
        WHERE `hour` = %s 
        AND `minute` = %s
        AND `amPm` = %s
        AND `symbol` = %s
    ''', (hour, minute, am_pm, symbol))

    rows = mysql_cursor.fetchall()
    print(rows)

async def get_positions(ib):

    print("Positions Table")
    print("-" * 90)
    print(f"   {'#':<10} {'Trade - Seconds':<18}{'Trades':<10}{'Symbol':<10}{'Timestamp (CR)':<25}{'Local UTC Timestamp':<25}{'Position':<10}{'Avg Cost':<10}")
    print("-" * 90)

    positions = ib.positions()

    count = 0
    
    for pos in positions:

        count = count + 1

        symbol = pos.contract.symbol
        position = pos.position
        avg_cost = pos.avgCost
        timestamp_cr = "17:52:02:134"  # Este sería el timestamp real en tu caso
        local_utc_timestamp = "11:52:02 UTC"  # Este sería el tiempo UTC correspondiente
        
        trade_seconds = 1  # Aquí usas una lógica para calcular el tiempo o el valor adecuado
        
        # Imprimir la información formateada
        print(f"   {count:<10} {trade_seconds:<18}{0:<10}{symbol:<10}{timestamp_cr:<25}{local_utc_timestamp:<25}{position:<10}{avg_cost:<10}")
    
    print("-" * 90)

async def sellStock(ib):

    symbol = input("Symbol to sell? ").upper()

    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)                       
    
    bid_price = client.get_last_quote(symbol).bid_price
    stock = Stock(symbol, 'SMART', 'USD')
    
    positions = ib.positions()

    total_position = 0

    for pos in positions:
        if pos.contract.symbol.upper() == symbol.upper():
            total_position += pos.position

    order = LimitOrder('SELL', total_position, bid_price - 0.01, outsideRth=True)

    trade = ib.placeOrder(stock, order)

    while not trade.isDone():
        await asyncio.sleep(0.1)    

    if trade.orderStatus.status == "Filled":
        symbol = stock.symbol 
        quantity_sold = total_position
        price = bid_price  
        
        print(" ")
        print(f"💹 Trade Completed 💹")
        print(f"The order for symbol {symbol} has been successfully executed.")
        print(f"You have sold {quantity_sold} shares at a price of ${price:.2f} each.")
        print(" ")  
     


async def show_menu(ib):
    while True:
        print("\nMenu:")
        print("1. Trade Signals Query")                
        print("2. Orders and Queue Presure")                        
        print("3. Sell Positions")        
        print("4. Check Positions")
        print("5. Check Orders")
        print("6. Short Squeeze Candidates")
        print("7. Clean Day Database for Tomorrow")        
        print("8. Clean Day data")                
        print("9. Trade Signal Query")
        print("10. Relative Volume Ratio Hour")
        print("11. Exit")        
        choice = input("Select an option: ")

        if choice == '1':   
            os.system('clear')         
            show_trade_signals()
        elif choice == '2':   
            os.system('clear')             
            show_tables()            
        elif choice == '3':            
            os.system('clear')                     
            await sellStock(ib)
        elif choice == '4':
            os.system('clear')                     
            await get_positions(ib)            
        elif choice == '5':
            os.system('clear')                     
            await has_active_sell_order(ib)
        elif choice == '6':
            os.system('clear')                     
            await getShortSqueezeCandidates()           
        elif choice == '7':
            os.system('clear')                     
            await processDataForTomorrow()                        
        elif choice == '8':
            os.system('clear')  
            await cleanDayDataBaseData()                                    
        elif choice == '9':
            os.system('clear')                     
            tradeSignalQuery()                                    
        elif choice == '10':
            os.system('clear')                     
            checkRelativeVolumeRatioHour()                                                
        elif choice == '11':
            os.system('clear')                     
            print("Exiting...")
            ib.disconnect()
            break  # Sale del bucle y termina el programa
        else:
            print("Invalid option, please try again.")        


async def main():
    PAPER_PORT_IBKR_GATEWAY = 4002
    PORT_IBKR_GATEWAY = 4001
    ib = IB()


    await show_menu(ib)  # Ejecuta el menú interactivo    

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )


asyncio.run(main())