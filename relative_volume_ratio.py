from datetime import datetime, timedelta
import sqlite3
import mysql.connector
from trading_config import get_symbols_from_database

# conn = sqlite3.connect('histFinanData.db')
# cursor = conn.cursor()

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

def get_stocks_in_range(mysql_cursor, float_limit, min_price, max_price):
    mysql_cursor.execute('''
        SELECT ticker, close
        FROM Stocks
        WHERE float_value < %s
        AND close > %s 
        AND close < %s
    ''', (float_limit, min_price, max_price))

    rows = mysql_cursor.fetchall()

    tickers = [row[0] for row in rows]
    return tickers

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

def store_relative_volume(hour, minute, am_pm, symbol, relative_volume):
    mysql_cursor.execute('''
            INSERT INTO RelativeVolumeRatio (symbol, hour, minute, amPm, relative_volume)
            VALUES (%s, %s, %s, %s, %s)
        ''', (symbol, hour, minute, am_pm, relative_volume))

    db_connection.commit()

def store_relative_volume_hour(hour, am_pm, symbol, relative_volume):
    mysql_cursor.execute('''
        INSERT INTO RelativeVolumeRatioHour (symbol, hour, amPm, relative_volume)
        VALUES (%s, %s, %s, %s)
    ''', (symbol, hour, am_pm, relative_volume))

    db_connection.commit()

def get_relative_volume(hour, minute, am_pm, ticker):
    mysql_cursor.execute('''
        SELECT SUM(volume) / COUNT(*) AS relative_volume
        FROM HistoryByMin
        WHERE hour = %s AND minute = %s AND amPm = %s AND stockID = %s
    ''', (hour, minute, am_pm, ticker))

    result = mysql_cursor.fetchone()[0]

    return result if result is not None else 0

def get_relative_volume_hour(hour, am_pm, ticker):
    mysql_cursor.execute('''
        SELECT SUM(volume) / COUNT(*) AS relative_volume
        FROM (
            SELECT volume
            FROM HistoryByMin
            WHERE hour = %s AND amPm = %s AND stockID = %s
        ) AS subquery
    ''', (hour, am_pm, ticker))

    result = mysql_cursor.fetchone()[0]

    return result if result is not None else 0

def calculate_relative_volume(symbol):

    start = datetime.strptime("02:00 AM", "%I:%M %p")
    # Hora final: 2:00 PM
    end = datetime.strptime("05:59 PM", "%I:%M %p")

    current = start
    while current <= end:
        hour = current.strftime("%I")  # hora con cero inicial
        minute = current.strftime("%M")  # minutos con cero inicial
        am_pm = current.strftime("%p")  # AM o PM
        current += timedelta(minutes=1)

        relative_volume = get_relative_volume(hour, minute,  am_pm, symbol)

        store_relative_volume(hour, minute, am_pm, symbol, relative_volume)

        if current > end + timedelta(minutes=1):
            break

def calculate_relative_volume_hour(symbol):

    start = datetime.strptime("02:00 AM", "%I:%M %p")
    # Hora final: 2:00 PM
    end = datetime.strptime("05:59 PM", "%I:%M %p")

    current = start
    while current <= end:
        hour = current.strftime("%I") 
        am_pm = current.strftime("%p")
        
        relative_volume = get_relative_volume_hour(hour, am_pm, symbol)
        
        store_relative_volume_hour(hour, am_pm, symbol, relative_volume)

        current += timedelta(hours=1)

        if current > end + timedelta(hours=1):
            break  


def getRelativeVolumeFactor(progress_callback=None):

    # mysql_cursor = db_connection.cursor()
    # mysql_cursor.execute("SELECT ticker FROM Stocks")
    # symbols = mysql_cursor.fetchall()

    # cursor.execute("SELECT ticker FROM Stocks")
    # cursor.execute("SELECT ticker FROM Stocks WHERE ticker = 'SNGX'")
    # symbols = cursor.fetchall()

    # db_connection = mysql.connector.connect(
    #     host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
    #     port=3306,
    #     user="admin",  # Reemplaza con tu usuario de MySQL
    #     password="E_I$S5PFri",  # Reemplaza con tu contraseña
    #     database="histFinanData"  # Reemplaza con el nombre de tu base de datos
    # )

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="E_I$S5PFri",
        database="histFinanData"
    )

    if db_connection.is_connected():
        print("Conexión exitosa a la base de datos RDS MySQL")

    # Create cursor (was missing)
    mysql_cursor = db_connection.cursor()

    # Use centralized symbol selection from trading_config
    symbols = get_symbols_from_database(mysql_cursor)
    total = len(symbols)

    # symbols = ['BCG']

    print(" ")
    print(f"\033[1;33mRunning Relative Volume... \033[0m")
    print(" ")
    print(f"Retrieved {total} stocks (using Trading Configuration criteria).")
    print(" ")
    #
    # symbols = ['THAR']

    for i, symbol in enumerate(symbols, 1):
        # Report progress to callback if provided
        if progress_callback:
            progress_callback(symbol, i, total)

        print(f"{i}/{total} - Relative Min stock: {symbol}")
        # calculate_relative_volume(symbol)
        # print(f"Relative H stock: {symbol}")
        calculate_relative_volume_hour(symbol)

    mysql_cursor.close()
    db_connection.close()
    
    print(" ")