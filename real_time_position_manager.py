from datetime import datetime, timedelta, date, timezone
import time
import random
import asyncio
from ib_insync import *
from ib_insync import IB, Stock
from polygon import RESTClient
import sqlite3
import mysql.connector  
from datetime import datetime, timedelta, date, timezone
import pytz

def has_place_order_sell_off(mysql_cursor, symbol: str) -> bool:

    query = """
        SELECT 1 FROM Orders
        WHERE symbol = %s AND orderType = 'placeOrderSellOff'
        LIMIT 1
    """
    mysql_cursor.execute(query, (symbol,))
    result = mysql_cursor.fetchone()

    return result is not None


    # query = """
    #     SELECT 1 FROM Orders
    #     WHERE symbol = ? AND orderType = 'placeOrderSellOff'
    #     LIMIT 1
    # """
    # mysql_cursor.execute(query, (symbol,))
    # result = mysql_cursor.fetchone()
    
    # return result is not None

def range_order_exists(db_connection, mysql_cursor, symbol, range_sell):

    query = """
    SELECT 1 
    FROM Orders
    WHERE symbol = %s AND range_sell = %s AND status = 'Processing'
    LIMIT 1;
    """
    
    mysql_cursor.execute(query, (symbol, range_sell))

    result = mysql_cursor.fetchone()
    
    return result is not None


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


def order_exists_by_range(db_connection, mysql_cursor, symbol, status, orderType):
        
    query = """
    SELECT range_sell FROM Orders
    WHERE symbol = %s AND status = %s AND orderType = %s
    ORDER BY range_sell DESC
    LIMIT 1
    """
    
    mysql_cursor.execute(query, (symbol, status, orderType))
    record = mysql_cursor.fetchone()
    
    return record[0] if record else None

def order_exists(db_connection, mysql_cursor, symbol, status, orderType):
    
    query = """
    SELECT 1 FROM Orders
    WHERE symbol = %s AND status = %s AND orderType = %s
    LIMIT 1
    """
    
    mysql_cursor.execute(query, (symbol, status, orderType))
    result = mysql_cursor.fetchone() 
    
    return bool(result)

def check_and_take_profits(db_connection, mysql_cursor, real_time_positions ,symbol, close, bot_price):

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(sellStock(db_connection, mysql_cursor, symbol, real_time_positions, close, bot_price))        

    

async def sellStock(db_connection, mysql_cursor, symbol, real_time_positions, polygon_second_close, bot_price):

    increase_percentage = ((polygon_second_close - bot_price) / bot_price) * 100
    print("🚀  ALERT 🚀 ")
    print(f"{symbol} has increased by more than  {increase_percentage:.2f}%")
    print(f"Current Price: {polygon_second_close}, Buy Price: {bot_price}")


    PAPER_PORT_IBKR_GATEWAY = 4002 

    client_id = random.randint(200, 1000)

    ib = IB()

    await ib.connectAsync('127.0.0.1', PAPER_PORT_IBKR_GATEWAY, clientId=client_id)    
    
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

    # persist_trade_signal_raw(symbol, polygon_second_close, bid_price_validation, bot_price, "not")                      
    
    print(" ")
    print(f"SELL_STOCK -> {symbol}")
    print(f"bid_price_validation = {bid_price_validation}")
    print(f"bot_price = {bot_price}")
    print(" ")

    if bid_price_validation >= bot_price * 1.1:    
    # if bid_price_validation >= bot_price:    

        if order_exists(db_connection, mysql_cursor, symbol, "Filled", "SELL"):

            range_sell = order_exists_by_range(db_connection, mysql_cursor, symbol, "Filled", "SELL")
            print(f"Current range_sell ----> {range_sell}")
            
            if not range_order_exists(db_connection, mysql_cursor, symbol, range_sell + 10):

                #The increase is calculated in 10% increments.
                range_sell = range_sell + 10      

                print(f"Next range_sell ----> {range_sell}")

                next_level_price = bot_price * (1 + range_sell / 100)

                print(f"next_level_price = {next_level_price}")                

                # if polygon_second_close >= ( bot_price * (1 + range_sell / 100)):
                if polygon_second_close >= next_level_price:

                    # persist_trade_signal_raw(symbol, polygon_second_close, bid_price_validation, bot_price, range_sell)            

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
                        save_order_to_db_sell(
                            symbol, 
                            time.time(), 
                            0, 
                            "Processing", 
                            "log", 
                            "SELL", 
                            0, 
                            0,
                            ask_price=0, 
                            ask_timestamp=0,
                            ask_size=0, 
                            bid_price=0, 
                            bid_size=0, 
                            open_price=1, 
                            open_map_timestamp=0,
                            last_trade_price=0, 
                            last_trade_timestamp=" ",
                            polygon_second_close=polygon_second_close, 
                            active_seconds_count=0,
                            range_sell=range_sell
                            )                


                        bid_price = client.get_last_quote(symbol).bid_price
                        limit_price = client.get_last_quote(symbol).ask_price
                        start_timestamp = print_current_time()

                        order = LimitOrder('SELL', quantity_to_sell, bid_price, outsideRth=True)

                        trade = ib.placeOrder(stock, order)

                        while not trade.isDone():
                            await asyncio.sleep(0.5)

                        new_qty = positionSize - quantity_to_sell

                        if new_qty > 0:
                            print(f" QUEDAN {new_qty} acciones -> {symbol}")
                        else:
                            print("real_time_positions.pop 1")
                            real_time_positions.pop(symbol, None)            

                        save_order_to_db_sell(
                            symbol, 
                            time.time(), 
                            trade.orderStatus.avgFillPrice, 
                            trade.orderStatus.status, 
                            trade, 
                            "SELL", 
                            quantity_to_sell, 
                            0,
                            ask_price=limit_price, 
                            ask_timestamp=0,
                            ask_size=0, 
                            bid_price=bid_price, 
                            bid_size=0, 
                            open_price=1, 
                            open_map_timestamp=0,
                            last_trade_price=0, 
                            last_trade_timestamp=" ",
                            polygon_second_close=polygon_second_close, 
                            active_seconds_count=0,
                            range_sell=range_sell
                            )   

                        return quantity_to_sell

                else:

                    range_sell = range_sell - 10

                    print(f"Current range = {range_sell}")


                    if range_sell == 10:
                        print("Case 10: Acción para el caso 10")

                        percent_50 = 7

                        pullback_tolerance = bot_price * ( 1 + (percent_50) / 100 )
                        print(pullback_tolerance)

                        if(polygon_second_close < pullback_tolerance):
                            print(f"Precio cayo por debajo del 5%... vende todo lo que queda de {symbol}")
                            print(f"pullback_tolerance = {pullback_tolerance} buy price = {bot_price} current price = {polygon_second_close}")

                            bid_price = client.get_last_quote(symbol).bid_price
                            order = LimitOrder('SELL', positionSize, bid_price, outsideRth=True)
                            trade = ib.placeOrder(stock, order)
                            while not trade.isDone():
                                await asyncio.sleep(0.5)

                            # await sellOffStock(db_connection, mysql_cursor, real_time_positions, symbol, polygon_second_close)                        


                    elif range_sell == 20:
                        print("Case 20: Acción para el caso 20")

                        percent_50 = 10

                        pullback_tolerance = bot_price * ( 1 + (percent_50) / 100 )
                        print(pullback_tolerance)

                        if(polygon_second_close < pullback_tolerance):
                            print(f"Precio cayo por debajo del 50%... vende todo lo que queda de {symbol}")
                            print(f"pullback_tolerance = {pullback_tolerance} buy price = {bot_price} current price = {polygon_second_close}")

                            bid_price = client.get_last_quote(symbol).bid_price
                            order = LimitOrder('SELL', positionSize, bid_price, outsideRth=True)
                            trade = ib.placeOrder(stock, order)
                            while not trade.isDone():
                                await asyncio.sleep(0.5)

                            # await sellOffStock(db_connection, mysql_cursor, real_time_positions, symbol, polygon_second_close)                        





                    elif range_sell == 30:
                        print("Case 30: Acción para el caso 30")
                    elif range_sell == 40:
                        print("Case 40: Acción para el caso 40")
                    elif range_sell == 50:
                        print("Case 50: Acción para el caso 50")
                    elif range_sell == 60:
                        print("Case 60: Acción para el caso 60")
                    elif range_sell == 70:
                        print("Case 70: Acción para el caso 70")
                    elif range_sell == 80:
                        print("Case 80: Acción para el caso 80")

                        percent_50 = 50

                        pullback_tolerance = bot_price * ( 1 + (percent_50) / 100 )
                        print(pullback_tolerance)

                        if(polygon_second_close < pullback_tolerance):
                            print(f"Precio cayo por debajo del 50%... vende todo lo que queda de {symbol}")
                            print(f"pullback_tolerance = {pullback_tolerance} buy price = {bot_price} current price = {polygon_second_close}")


                            bid_price = client.get_last_quote(symbol).bid_price
                            order = LimitOrder('SELL', positionSize, bid_price, outsideRth=True)
                            trade = ib.placeOrder(stock, order)
                            while not trade.isDone():
                                await asyncio.sleep(0.5)

                            # await sellOffStock(db_connection, mysql_cursor, real_time_positions, symbol, polygon_second_close)                        

                    elif range_sell == 90:
                        print("Case 90: Acción para el caso 90")
                    elif range_sell == 100:
                        print("Case 100: Acción para el caso 100")                    

                    pullback_tolerance = bot_price * ( 1 + (range_sell - 10) / 100 )
                    print(pullback_tolerance)

                    if(polygon_second_close < pullback_tolerance):
                        print(f"Current Price = {polygon_second_close} - pullback = {pullback_tolerance}")
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
            print("#The initial sale range is 10%.")

            if not range_order_exists(db_connection, mysql_cursor, symbol, range_sell):

                # FIRST TIME
                start_timestampTemp = print_current_time()

                save_order_to_db_sell(
                    symbol, 
                    time.time(), 
                    0, 
                    "Processing", 
                    "log", 
                    "SELL", 
                    0, 
                    0,
                    ask_price=0, 
                    ask_timestamp=0,
                    ask_size=0, 
                    bid_price=0, 
                    bid_size=0, 
                    open_price=1, 
                    open_map_timestamp=0,
                    last_trade_price=0, 
                    last_trade_timestamp=" ",
                    polygon_second_close=polygon_second_close, 
                    active_seconds_count=0,
                    range_sell=range_sell
                    )                

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

                save_order_to_db_sell(
                    symbol, 
                    time.time(), 
                    trade.orderStatus.avgFillPrice, 
                    trade.orderStatus.status, 
                    trade, 
                    "SELL", 
                    quantity_to_sell, 
                    0,
                    ask_price=limit_price, 
                    ask_timestamp=0,
                    ask_size=0, 
                    bid_price=bid_price, 
                    bid_size=0, 
                    open_price=1, 
                    open_map_timestamp=0,
                    last_trade_price=0, 
                    last_trade_timestamp=" ",
                    polygon_second_close=polygon_second_close, 
                    active_seconds_count=0,
                    range_sell=range_sell
                    )    

                print(f"Sold {quantity_to_sell} shares of {symbol} at {trade.orderStatus.avgFillPrice}")

                return quantity_to_sell        

def check_and_alert_loss(db_connection, mysql_cursor, real_time_positions, symbol, close):

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(sellOffStock(db_connection, mysql_cursor, symbol, real_time_positions, close))    
    
       
    

async def sellOffStock(db_connection, mysql_cursor, symbol, real_time_positions, polygon_second_close):

    PAPER_PORT_IBKR_GATEWAY = 4002

    client_id = random.randint(200, 1000)

    ib = IB()

    await ib.connectAsync('127.0.0.1', PAPER_PORT_IBKR_GATEWAY, clientId=client_id)    

    if has_place_order_sell_off(mysql_cursor, symbol):
        print(" ")
        return

    save_order_to_db(
        symbol, 
        time.time(), 
        0, 
        " ", 
        "Processing", 
        "placeOrderSellOff", 
        0, 
        0,
        ask_price=0, 
        ask_timestamp=0,
        ask_size=0, 
        bid_price=0, 
        bid_size=0, 
        open_price=1, 
        open_map_timestamp=0,
        last_trade_price=0, 
        last_trade_timestamp=" ",
        polygon_second_close=0, 
        active_seconds_count=0
        )

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
        print(f"No shares to sell for {symbol}")
        return    

    bid_price = client.get_last_quote(symbol).bid_price
    limit_price = client.get_last_quote(symbol).ask_price
    start_timestamp = print_current_time()

    order = LimitOrder('SELL', quantity_to_sell, bid_price, outsideRth=True)

    trade = ib.placeOrder(stock, order)

    while not trade.isDone():
        await asyncio.sleep(0.5)

    ib.disconnect()        

    print(f"\033[1;31m*********************** \033[0m")          
    print(f"\033[1;31m* Stock SOLD = {symbol}   * \033[0m")          
    print(f"\033[1;31m* Filled price: ${trade.orderStatus.avgFillPrice} * \033[0m")          
    print(f"\033[1;31m*********************** \033[0m")          
    print(" ")

    save_order_to_db(
        symbol, 
        time.time(), 
        trade.orderStatus.avgFillPrice, 
        trade.orderStatus.status, 
        trade, 
        "SELL", 
        quantity_to_sell, 
        0,
        ask_price=limit_price, 
        ask_timestamp=0,
        ask_size=0, 
        bid_price=bid_price, 
        bid_size=0, 
        open_price=1, 
        open_map_timestamp=0,
        last_trade_price=0, 
        last_trade_timestamp=" ",
        polygon_second_close=polygon_second_close, 
        active_seconds_count=0
        )                

def save_order_to_db_sell(symbol, start_timestamp, avgFillPrice, status, tradeLog, orderType, totalQuantity, trade_signals_count, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_map_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close, active_seconds_count, range_sell):    

    db_connection = mysql.connector.connect(
        host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
        port=3306,
        user="admin",  
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()      

    mysql_cursor.execute('''
        INSERT INTO Orders (`symbol`, `end_timestamp`, `start_timestamp`, `filledPrice`, `status`, `log`, `orderType`, `totalQuantity`, `tradeSignalsCount`, `ask_price`, `ask_timestamp`, `ask_size`, `bid_price`, `bid_size`, `open_price`, `open_timestamp`, `last_trade_price`, `last_trade_timestamp`, `polygon_second_close`, `active_seconds_count`, `range_sell`)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (symbol, time.time(), start_timestamp, avgFillPrice, status,  str(tradeLog), orderType, totalQuantity, trade_signals_count, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_map_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close, active_seconds_count, range_sell))

    db_connection.commit()    

    mysql_cursor.close()
    db_connection.close()     

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
    ''', (symbol, time.time(), start_timestamp, avgFillPrice, status,  str(tradeLog), orderType, totalQuantity, trade_signals_count, ask_price, ask_timestamp, ask_size, bid_price, bid_size, open_price, open_map_timestamp, last_trade_price, last_trade_timestamp, polygon_second_close, active_seconds_count))

    db_connection.commit()    

    mysql_cursor.close()
    db_connection.close()     

async def has_active_sell_order(ib, symbol: str) -> bool:

    open_trades = await ib.reqAllOpenOrdersAsync()
    
    for trade in open_trades:

        if ( trade.contract.symbol.upper() == symbol.upper()
            and trade.order.action == 'SELL' and trade.orderStatus.status in ('PreSubmitted', 'Submitted') ):
            print(f"Cancelando orden de venta para {symbol}...")
            ib.cancelOrder(trade.order)
            return True

    return False      

def print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]    

# def play_bell():    
#     playsound('piece-of-cake.mp3')                 


# conn = sqlite3.connect('histFinanData.db')
# cursor = conn.cursor()
# persist_trade_signal_raw(cursor, conn, "symbol", 1, 1.8, 0.90, 60)               

# print(print_current_time())
# if not range_order_exists("MASK", 30):
#     print("No se encontró ninguna orden con esos parámetros.")

# print(print_current_time())