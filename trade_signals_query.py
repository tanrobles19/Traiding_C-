import sqlite3
import mysql.connector
from datetime import datetime
import pytz
from colorama import Fore, Style, init
from datetime import datetime, timezone
import pytz
import time
from tabulate import tabulate

def open_timestamp_data(timestamp):

    # timestamp = 1764850000000.0

    timestamp_seconds = timestamp / 1000

    utc_time = datetime.utcfromtimestamp(timestamp_seconds)
    
    cr_tz = pytz.timezone('America/Costa_Rica')
    cr_time = utc_time.replace(tzinfo=pytz.utc).astimezone(cr_tz)

    human_readable_date = cr_time.strftime('%H:%M:%S') + f".{int(timestamp % 1000):03d}"
    # human_readable_date = cr_time.strftime('%Y-%m-%d %H:%M:%S') + f".{int(timestamp % 1000):03d}"    

    return human_readable_date

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

def show_trade_signals():

    init(autoreset=True)

    costa_rica_tz = pytz.timezone('America/Costa_Rica')

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    if db_connection.is_connected():
        print("Conexión exitosa a la base de datos RDS MySQL")  

    mysql_cursor = db_connection.cursor()              

    print(Fore.CYAN + "TradeSignalsBuyPerSecond Table")
    print("-" * 170)

    mysql_cursor.execute("SELECT COUNT(*) FROM TradeSignalsBuyPerSecond")
    rows = mysql_cursor.fetchall()

    print(f"Trade Signal Count   : {rows[0][0]}")

    mysql_cursor.execute("SELECT COUNT(*) FROM TradeSignalsBuyPerSecond WHERE purchasePrediction = 'Bearish Candle'")
    rows = mysql_cursor.fetchall()    
    
    print(f"Trade Signal Bearish : {rows[0][0]}") 

    mysql_cursor.execute("SELECT COUNT(*) FROM TradeSignalsBuyPerSecond WHERE purchasePrediction = 'Doji Candle'")
    rows = mysql_cursor.fetchall()    

    print(f"Trade Signal Doji    : {rows[0][0]}")      

    mysql_cursor.execute("SELECT COUNT(*) FROM TradeSignalsBuyPerSecond WHERE purchasePrediction LIKE 'Price increase less than%'")
    rows = mysql_cursor.fetchall()    

    print(f"Increase less that   : {rows[0][0]}")
    print(" ")

    mysql_cursor.execute("SELECT trade_activity_seconds, tradeSignalsCount, symbol, timestamp, local_utc_timestamp, purchasePrediction, relative_volume, open, close, low_float  FROM TradeSignalsBuyPerSecond WHERE purchasePrediction = 'hola'")
    rows = mysql_cursor.fetchall()

    for row in rows:
        print(f"Count: {row}")


    symbol = input("Symbol? ").upper()

    if symbol:

        query = """
        SELECT trade_activity_seconds, tradeSignalsCount, symbol, timestamp, 
            local_utc_timestamp, purchasePrediction, relative_volume, 
            open, close, low_float, news_metadata, consumer_id, newsCount, timestamp_news, temp_action, relative_volume_hour, volume, open_timestamp, trade_id, exchange, trf_id, high, low
        FROM TradeSignalsBuyPerSecond
        WHERE symbol = %s ORDER BY timestamp_unix DESC;
        """

        mysql_cursor.execute(query, (symbol,))
        rows = mysql_cursor.fetchall()  
    else:

        mysql_cursor.execute("SELECT trade_activity_seconds, tradeSignalsCount, symbol, timestamp, local_utc_timestamp, purchasePrediction, relative_volume, open, close, low_float, news_metadata, consumer_id, newsCount, timestamp_news, temp_action, relative_volume_hour, volume, open_timestamp, trade_id, exchange, trf_id, high, low FROM TradeSignalsBuyPerSecond ORDER BY timestamp_unix DESC;")
        rows = mysql_cursor.fetchall()

    # print(Fore.YELLOW + f" {'Id':<5} {'Trade-Seconds':<14} {'Trades':<8} {'Symbol':<8} {'Timestamp (CR)':<15} {'Local UTC':<10} {'Open TimeStamp':<15} {'Trade Id':<12} {'Exchange':<12} {'trf_id':<12} {'Relative H':<12} {'Volume':<10} {'Open':<7} {'Close':<7} {'Low Float':<7} {'Purchase Prediction':<33} {'Temp Action':<20} {'News Count':<20} {'News TimeStamp':<20} {'Info':<20}")
    print(Fore.YELLOW + f" {'Symbol':<8} {'Timestamp (CR)':<15} {'Local UTC':<10} {'Open TimeStamp':<16} {'Trade-Id':<17} {'Exchange':<12} {'trf_id':<12} {'Relative H':<12} {'Volume':<10} {'Open':<12} {'High':<9} {'Low':<7} {'Close':<10} {'Low Float':<12} {'Purchase Prediction':<33} {'Temp Action':<20}")    
    print("-" * 250)

    for row in rows:
        purchase_prediction = row[5]
        info = row[10]

        newsCount = row[12]

        if newsCount is None:
            newsCount = 0

        news_timestamp = row[13]

        if news_timestamp is None:
            news_timestamp = "n/a"     

        temp_action = row[14]
        relative_volume_hour = row[15]

        if relative_volume_hour is None:
            relative_volume_hour = "---"            

        if temp_action is None:
            temp_action = "---"

        volume = row[16]

        if volume is None:
            volume = "---"     


        trade_id = row[18]
        exchange = row[19]
        trf_id = row[20]

        if trade_id is None:
            trade_id = "---"     

        if exchange is None:
            exchange = "---"     

        if trf_id is None:
            trf_id = "---"    

        high = row[21]        
        low = row[22]                

        if high is None:
            high = "---"    

        if low is None:
            low = "---"                

        # print(row[3])
        local_timestamp_value = convert_timestamp_to_costa_rica_time(float(row[3]))

        open_to_local_timestamp_value = "n/a"

        try:
            # print(float(row[17]))
            open_to_local_timestamp_value = open_timestamp_data(float(row[17]))
            # print(f"open_to_local_timestamp_value = {open_to_local_timestamp_value}")

        except Exception as e:
            open_to_local_timestamp_value = "n/a"    
        
        if purchase_prediction == "BUY" or temp_action == "short_squeeze" or temp_action == "track_stock_price_increase":
            print(Fore.RED + Style.BRIGHT + 
                f" {row[2]:<8} {local_timestamp_value:<18} {row[4]:<8} {open_to_local_timestamp_value:<17} {trade_id:<18} {exchange:<11} {trf_id:<11} {relative_volume_hour:<12} {volume:<9} O {row[7]:<10} {high:<8} {low:<8} $ {row[8]:<10} {row[9]:<11} {row[5]:<35} {temp_action:<35} ")
                # f"{row[11]:<10} {row[0]:<12} {row[1]:<7} {row[2]:<7} {local_timestamp_value:<18} {row[4]:<8} {open_to_local_timestamp_value:<17} {trade_id:<12} {exchange:<11} {trf_id:<11} {relative_volume_hour:<12} {volume:<9} {row[7]:<8} {row[8]:<10} {row[9]:<7} {row[5]:<35} {temp_action:<35} {newsCount:<10} {news_timestamp:<30} {row[10]:<30} ")                
        else:
            # print(f"{row[11]:<10} {row[0]:<12} {row[1]:<7} {row[2]:<7} {local_timestamp_value:<18} {row[4]:<8} {open_to_local_timestamp_value:<17} {trade_id:<12} {exchange:<11} {trf_id:<11} {relative_volume_hour:<12} {volume:<9} {row[7]:<8} {row[8]:<10} {row[9]:<7} {row[5]:<35} {temp_action:<35} {newsCount:<10} {news_timestamp:<30} {row[10]:<30} ")
            print(f" {row[2]:<8} {local_timestamp_value:<18} {row[4]:<8} {open_to_local_timestamp_value:<17} {trade_id:<18} {exchange:<11} {trf_id:<11} {relative_volume_hour:<12} {volume:<9} O {row[7]:<10} {high:<8} {low:<8} $ {row[8]:<10} {row[9]:<11} {row[5]:<35} {temp_action:<35} ")            


    if symbol:



        hour = int(input("Hour? "))
        minute = int(input("Minute? "))

        query = """
            SELECT * FROM trades
            WHERE symbol = %s AND hour = %s AND minute = %s
        """
        mysql_cursor.execute(query, (symbol, hour, minute))

        results = mysql_cursor.fetchall()

        headers = ['Symbol', 'price', 'volume', 'timestamp', 'trade_id', 'conditions', 'exchange', 'trf_id', 'hour', 'minute']

        formatted_results = []


        for row in results:

            formatted_hour_minute = f"{int(row[8]):02d}:{int(row[9]):02d}"                    

            price = f"${row[1]}"
            volume = f"{row[3]}"
            
            formatted_row = list(row)
            formatted_row[1] = price
            formatted_row[3] = open_timestamp_data(float(row[3]))
            formatted_row[4] = row[4]
            formatted_row[8] = formatted_hour_minute
            formatted_row[9] = formatted_hour_minute
            
            formatted_results.append(formatted_row)

        print(tabulate(formatted_results, headers=headers, tablefmt='grid'))







        query = "SELECT symbol, start_timestamp, end_timestamp, filledPrice, status, totalQuantity, orderType, open_price, ask_price, bid_price, ask_size, bid_size, last_trade_price, log, active_seconds_count, range_sell FROM Orders WHERE symbol = %s"

        mysql_cursor.execute(query, (symbol,))        

        rows = mysql_cursor.fetchall()

        print("  ")
        print("\n" + Fore.YELLOW + "Orders")    
        print("  ")

        print("-" * 170)
        print(Style.BRIGHT + f"{'Symbol':<7} {'Start Timestamp':<17} {'End Timestamp':<15} {'Filled Price':<14} {'Status':<10} {'Total Quantity':<16} {'Sell Range':<16} {'Order Type':<17} {'Open Price':<12} {'Bid price':<12} {'Bid size':<12} {'Last Price':<12} {'Ask price':<12} {'Ask size':<12} {'Spread':<10} {'Activity ⏳':<30} {'Log':<40}")
        print("-" * 170)

        for i, row in enumerate(rows):
            symbol, start_timestamp, end_timestamp, filled_price, status, total_quantity, order_type, open_price, ask_price, bid_price, ask_size, bid_size, last_trade_price, log, active_seconds_count, range_sell = row
            
            filled_price = filled_price if filled_price is not None else 0
            total_quantity = total_quantity if total_quantity is not None else 0
            status = status if status is not None else "Unknown"
            order_type = order_type if order_type is not None else "Unknown"
            open_price = open_price if open_price is not None else 0
            ask_price = ask_price if ask_price is not None else 0
            range_sell = range_sell if range_sell is not None else " "
            bid_price = bid_price if bid_price is not None else "N/A"
            log = log if log is not None else "No Log"

            spread = ask_price - bid_price 

            spread = round(spread, 2)

            truncated_log = log[:80] + ('...' if len(log) > 80 else '')  # Si el log es mayor a 40 caracteres, agregar '...'

            start_timestamp_value = convert_timestamp_to_costa_rica_time(float(start_timestamp))

            end_timestamp_value = convert_timestamp_to_costa_rica_time(float(end_timestamp))

            
            if i % 2 == 0:  # Fila par: negrita y blanco
                print(Fore.WHITE + Style.BRIGHT + f"{symbol:<8} {start_timestamp_value:<15} {end_timestamp_value:<20} {filled_price:<10} {status:<15} {total_quantity:<12} {range_sell:<18} {order_type:<18} {open_price:<12} {bid_price:<10} {bid_size:<10} $ -> {last_trade_price:<10} {ask_price:<11} {ask_size:<11} {spread:<11} {active_seconds_count:<14} {truncated_log:<40}")
            else:  # Fila impar: gris claro
                print(Fore.YELLOW + f"{symbol:<8} {start_timestamp_value:<15} {end_timestamp_value:<20} {filled_price:<10} {status:<15} {total_quantity:<12} {range_sell:<18} {order_type:<18} {open_price:<12} {bid_price:<10} {bid_size:<10} $ -> {last_trade_price:<10} {ask_price:<11} {ask_size:<11} {spread:<11} {active_seconds_count:<14} {truncated_log:<40}")

        print("-" * 170)










    mysql_cursor.close()
    db_connection.close()   

     


# from datetime import datetime
# import pytz

# # El timestamp en milisegundos
# # timestamp = 1764867836592
# timestamp = 1764871146229.0


# # Convertir el timestamp de milisegundos a segundos
# timestamp_seconds = timestamp / 1000

# # Convertir a una fecha legible en formato UTC
# utc_time = datetime.utcfromtimestamp(timestamp_seconds)

# # Convertir a zona horaria de Costa Rica (UTC-6)
# cr_tz = pytz.timezone('America/Costa_Rica')
# cr_time = utc_time.replace(tzinfo=pytz.utc).astimezone(cr_tz)

# # Formatear la hora para que incluya milisegundos
# human_readable_date = cr_time.strftime('%Y-%m-%d %H:%M:%S') + f".{int(timestamp % 1000):03d}"

# print(human_readable_date)



# # local_timestamp_value = convert_timestamp_to_costa_rica_time(float("1764850000000"))
# # print(local_timestamp_value)
    