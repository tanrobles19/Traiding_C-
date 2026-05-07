import polygon
from polygon import RESTClient
import pandas as pd
import sqlite3
import mysql.connector
from datetime import datetime
import pytz
import time
from trading_config import get_symbols_from_database

def get_stocks_in_range(mysql_cursor, float_limit, min_price, max_price):
    mysql_cursor.execute('''
        SELECT ticker, close
        FROM Stocks
        WHERE float_value < %s
        AND close > %s 
        AND close < %s limit 100
    ''', (float_limit, min_price, max_price))

    rows = mysql_cursor.fetchall()

    tickers = [row[0] for row in rows]
    return tickers

def get_relative_volume(hour, minute, am_pm, stockID, cursor):
    cursor.execute('''
        SELECT SUM(volume) AS total_volume
        FROM (
            SELECT volume
            FROM HistoryByMin
            WHERE hour = ? AND minute = ? AND amPm = ? AND stockID = ?
        )
    ''', (hour, minute, am_pm, stockID))

    result = cursor.fetchone()[0]

    return result if result is not None else 0

def convert_utc_to_cr_time(timestamp):
    utc_zone = pytz.utc
    cr_zone = pytz.timezone('America/Costa_Rica')
    dt_utc = datetime.fromtimestamp(timestamp / 1000, tz=utc_zone)
    dt_cr = dt_utc.astimezone(cr_zone)

    date = dt_cr.strftime('%Y-%m-%d')  # 2025-05-20 (MySQL date format)
    hour = int(dt_cr.strftime('%I'))  # 1-12 (as integer)
    minute = int(dt_cr.strftime('%M'))  # 0-59 (as integer)
    am_pm = dt_cr.strftime('%p')  # AM/PM

    return date, hour, minute, am_pm

def get_Historical_Data_by_Hour(init_date, end_date, progress_callback=None):

    print(f"\033[1;33mHistory by Hour \033[0m")
    print(" ")

    # conn = sqlite3.connect('histFinanData.db')
    # cursor = conn.cursor()

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="E_I$S5PFri",
        database="histFinanData"
    )

    if db_connection.is_connected():
        print("Conexión exitosa a la base de datos RDS MySQL")


    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)

    mysql_cursor = db_connection.cursor()

    # Use centralized symbol selection from trading_config
    tickers = get_symbols_from_database(mysql_cursor)
    # tickers = ['LFS']
    total = len(tickers)

    print(f"Retrieved {total} stocks (using Trading Configuration criteria).")
    print(" ")

    total_data_count = 0
    stock_counter = 1

    for ticker in tickers:
        # Report progress to callback if provided
        if progress_callback:
            progress_callback(ticker, stock_counter, total)

        try:
            aggregates = []

            for a in client.list_aggs(
                ticker,
                1,
                "hour",
                init_date,
                end_date,
                adjusted="true",
                sort="asc",
                limit=120,
            ):
                # print(a)
                aggregates.append({
                    "timestamp": a.timestamp,
                    "close": a.close,
                    "volume": a.volume
                })

            df = pd.DataFrame(aggregates)

            if df.empty:
                print(f"{stock_counter}/{total}. Stock[H] {ticker} -> No data available")
                stock_counter += 1
                time.sleep(0.1)  # Small delay to avoid rate limiting
                continue

            mysql_cursor.execute('START TRANSACTION')

            for i, (index, row) in enumerate(df.iterrows(), 1):

                # date, hour, minute, am_pm = convert_utc_to_cr_time(row['timestamp'])
                # timestamp_seconds = row['timestamp'] / 1000
                # dt = datetime.utcfromtimestamp(timestamp_seconds)
                # hour = dt.hour - 6
                # # print(hour)

                date, hour, minute, am_pm = convert_utc_to_cr_time(row['timestamp'])

                insert_query = '''
                    INSERT INTO HistoryByMin (stockID, close, volume, date, hour, minute, amPm)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                '''
                data = (ticker, row['close'], row['volume'], date, hour, minute, am_pm)

                try:
                    mysql_cursor.execute(insert_query, data)
                except mysql.connector.Error as err:
                    print(f"Error inserting data for {ticker}: {err}")
                    continue

            db_connection.commit()

            total_data_count += len(df)

            print(f"{stock_counter}/{total}. Stock[H] {ticker} -> {len(df)}")

        except Exception as e:
            print(f"{stock_counter}/{total}. Stock[H] {ticker} -> ERROR: {str(e)}")
            db_connection.rollback()

        stock_counter += 1
        time.sleep(0.15)  # Rate limiting delay (150ms between requests)

    mysql_cursor.close()
    db_connection.close()

    print(" ")
    print(f"Total data points saved in HistoryByMin: {total_data_count}")

def get_Historical_Data_by_minute(init_date, end_date):

    print(f"\033[1;33mHistory by Minute \033[0m")              
    print(" ")

    db_connection = mysql.connector.connect(
        host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
        port=3306,
        user="admin",  # Reemplaza con tu usuario de MySQL
        password="E_I$S5PFri",  # Reemplaza con tu contraseña
        database="histFinanData"  # Reemplaza con el nombre de tu base de datos
    )

    if db_connection.is_connected():
        print("Conexión exitosa a la base de datos RDS MySQL")

    
    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)

    mysql_cursor = db_connection.cursor()

    tickers = get_stocks_in_range(mysql_cursor, 30000000, 0.90, 8)
    
    print(f"Retrieved {tickers} stocks.")
    print(f"Retrieved {len(tickers)} stocks.")
    print(" ")

    total_data_count = 0
    stock_counter = 1

    for ticker in tickers:
        aggregates = []

        for a in client.list_aggs(
            ticker,
            1,
            "minute",
            init_date,
            end_date,
            adjusted="true",
            sort="asc",
            limit=120,
        ):
            aggregates.append({
                "timestamp": a.timestamp,
                "close": a.close,
                "volume": a.volume
            })

        df = pd.DataFrame(aggregates)

        # cursor.execute('BEGIN TRANSACTION')
        mysql_cursor.execute('START TRANSACTION')

        for i, (index, row) in enumerate(df.iterrows(), 1):

            date, hour, minute, am_pm = convert_utc_to_cr_time(row['timestamp'])

            insert_query = '''
                INSERT INTO HistoryByMin (stockID, close, volume, date, hour, minute, amPm)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            '''
            data = (ticker, row['close'], row['volume'], date, hour, minute, am_pm)

            try:
                mysql_cursor.execute(insert_query, data)
            except mysql.connector.Error as err:                
                print(f"Error al insertar datos para el ticker {ticker}: {err}")
                print(f"Datos que fallaron: {data}")
            except Exception as e:
                print(f"Error inesperado: {e}")
                print(f"Datos que fallaron: {data}")            

        db_connection.commit()

        total_data_count += len(df)
        
        print(f"{stock_counter}. Stock[M] {ticker} -> {len(df)}")
        stock_counter += 1

    # conn.close()
    mysql_cursor.close()
    db_connection.close()    

    print(" ")
    print(f"Total data points saved in HistoryByMin: {total_data_count}")

def get_Historical_Data_Experiment():
    
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()
    
    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)

    mysql_cursor = db_connection.cursor()


    mysql_cursor.execute("SELECT ticker FROM Stocks")
    tickers = mysql_cursor.fetchall()


    print(f"Retrieved {len(tickers)} stocks.")

    total_data_count = 0  # Variable to store total data points inserted
    stock_counter = 1  # Counter for stock processing

    for (ticker,) in tickers:
        aggregates = []
        
        for a in client.list_aggs(
            ticker,
            1,
            "hour",
            "2025-07-01",
            "2025-08-04",
            adjusted="true",
            sort="asc",
            limit=120,
        ):
            aggregates.append({
                "timestamp": a.timestamp,
                "close": a.close,
                "volume": a.volume
            })

        df = pd.DataFrame(aggregates)

        if 'volume' in df.columns and not df['volume'].empty:
            avg_volume = int(df['volume'].mean())
            print(f"Volumen promedio {ticker}: {avg_volume}")
            cursor.execute("UPDATE Stocks SET avg_month_volume = ? WHERE ticker = ?", (avg_volume, ticker))
            conn.commit()
        else:
            print(f"No se encontraron datos de volumen para el ticker {ticker}")
    conn.close()        


def getHistoricalData(init_date=None, end_date=None, progress_callback=None):

    print(f"\033[1;33mRetrieving historical data... \033[0m")

    start_time = time.time()

    # If dates not provided, ask for them or use defaults
    if init_date is None:
        init_date = input("Init Date? 📅  ").upper()
    if end_date is None:
        end_date = input("End Date? 🗓️  ").upper()

    # Fallback to today's date if still empty
    if not init_date or not end_date:
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        init_date = init_date or today
        end_date = end_date or today

    print("  ")
    print(f"Init Date = {init_date}")
    print(f"End Date = {end_date}")

    print("  ")
    # get_Historical_Data_by_minute(init_date, end_date)
    print("  ")
    get_Historical_Data_by_Hour(init_date, end_date, progress_callback)    

    end_time = time.time()

    elapsed_time = end_time - start_time
    print(" ")
    print(f"Total Time: {elapsed_time}")



# getHistoricalData()