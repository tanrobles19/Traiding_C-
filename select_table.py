import sqlite3
import mysql.connector
from colorama import Fore, Style, init
from datetime import datetime, timezone
import pytz
import time


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

def show_tables():

    init(autoreset=True)

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()              

    print("\n" + "-"*100 + "\n")

    mysql_cursor.execute("SELECT COUNT(*) FROM HistoryByMin")
    result = mysql_cursor.fetchone()
    
    history_by_min_data = result[0]

    print(f"History By Minute            = {history_by_min_data}")        

    mysql_cursor.execute("SELECT COUNT(*) FROM RelativeVolumeRatio")
    result = mysql_cursor.fetchone()
    
    relative_volume_value = result[0]    

    print(f"Relative Volume Count        = {relative_volume_value}")            
    print(" ")

    mysql_cursor.execute("SELECT queue_id, SUM(number_trades) AS total_trades FROM QueueBehavior WHERE queue_id = 'trade_queue' GROUP BY queue_id;")

    rows = mysql_cursor.fetchall()
    if rows:
        total_trades = rows[0][1] 
        print(f"Total trades processed Queue = {total_trades}")
    else:
        print("No data found in QueueBehavior table.")

    mysql_cursor.execute("SELECT AVG(market_trade_latency_offset) AS avg_latency FROM QueueBehavior;")

    result = mysql_cursor.fetchone()

    avg_latency = result[0]

    print(f"Average latency Offset       = {avg_latency}")    
    print("    ")

    mysql_cursor.execute("SELECT * FROM QueueBehavior ORDER BY timestamp desc")

    print(Fore.YELLOW + f"{'Type':<12} {'Presure':<15} {'Count':<8} {'Latency Offset':<18} {'Old Trades Count':<20} {'Timestamp':<20}")
    print("-" * 100)

    for row in mysql_cursor.fetchall():
        queue_type = "Trade" if row[1] == "trade_queue" else "Quote"
        print(f"{queue_type:<12} {row[2]:<15} {row[3]:<14} {row[5]:<18} {row[6]:<13} {row[4]:<18}")
    print("-" * 100)

    print("\n" + Fore.YELLOW + "Orders Table:")
    print("-" * 80)

    print("-" * 170)

    # mysql_cursor.execute("SELECT trade_activity_seconds, tradeSignalsCount, symbol, timestamp, local_utc_timestamp, purchasePrediction, relative_volume, open, close, low_float, ask_timestamp, ask_price FROM TradeSignalsBuyPerSecond WHERE purchasePrediction = 'BUY' ORDER by id DESC")
    mysql_cursor.execute("SELECT trade_activity_seconds, tradeSignalsCount, symbol, timestamp, local_utc_timestamp, purchasePrediction, relative_volume, open, close, low_float, ask_timestamp, ask_price FROM TradeSignalsBuyPerSecond WHERE purchasePrediction = 'BUY'")

    rows = mysql_cursor.fetchall()

    # Imprimir el encabezado de la tabla, moviendo "Purchase Prediction" al final
    print(Fore.YELLOW + f"{'Trade-Seconds':<15} {'Trades':<7} {'Symbol':<10} {'Timestamp (CR)':<15} {'Local UTC':<12} {'Relative Volume':<18} {'Open':<10} {'Close':<10} {'Low Float':<10} {'Ask T':<10} {'Ask price':<10}")
    print("-" * 170)

    # Iterar sobre los resultados y convertir timestamps
    for row in rows:
        # Obtener el valor de "Purchase Prediction"
        purchase_prediction = row[5]
        
        # Si "Purchase Prediction" es igual a "BUY", aplicamos color rojo y negrita
        if purchase_prediction == "BUY":
            print(Fore.RED + Style.BRIGHT + 
                f"{row[0]:<16} {row[1]:<7} {row[2]:<10} {row[3]:<17} {row[4]:<12} {row[6]:<15} {row[7]:<10} {row[8]:<10} {row[9]:<10} {row[10]:<10} {row[11]:<10}")
        else:
            print(f"{row[0]:<16} {row[1]:<7} {row[2]:<10} {row[3]:<17} {row[4]:<12} {row[6]:<15} {row[7]:<10} {row[8]:<10} {row[9]:<10} {row[10]:<10} {row[11]:<10}")


    mysql_cursor.execute("SELECT symbol, start_timestamp, end_timestamp, filledPrice, status, totalQuantity, orderType, open_price, ask_price, bid_price, ask_size, bid_size, last_trade_price, log, active_seconds_count, range_sell FROM Orders")

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