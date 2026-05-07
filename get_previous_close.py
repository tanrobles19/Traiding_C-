import polygon
from polygon import RESTClient
import sqlite3
import mysql.connector
from colorama import Fore, Style, init
from trading_config import get_all_symbols

def update_stock_closes(api_key, db_name, progress_callback=None):
    client = RESTClient(api_key)

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="E_I$S5PFri",
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()

    # Last-Price step runs over EVERY ticker in the master registry —
    # we cannot price-filter yet because this is exactly what populates
    # the price column. Float-filtering would also be wrong (floats are
    # populated by the next pipeline step).
    tickers = get_all_symbols(mysql_cursor)
    total = len(tickers)
    count = 0

    print(f"Processing {total} symbols (full Stocks registry — no filter at this step)")

    for ticker in tickers:

        count += 1

        # Report progress to callback if provided
        if progress_callback:
            progress_callback(ticker, count, total)

        print(f"#{count}/{total} - Symbol: {ticker}")                  

        agg = client.get_previous_close_agg(ticker, adjusted="true")
        price = client.get_last_trade(ticker).price

        if price > 0:

            mysql_cursor.execute("""
                UPDATE Stocks
                SET close = %s
                WHERE ticker = %s
            """, (price, ticker))

            db_connection.commit()
        else:
            print("  ")
            print(f"\033[1;31m ****************** NOT FOUND {ticker} ******************")    
            print(Style.RESET_ALL)                                   
            print("  ")              

    mysql_cursor.close()
    db_connection.close()

    print("  ")
    print(f"Successfully updated the close for {count} stocks.")

def getPreviousClose(progress_callback=None):

    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    db_name = 'histFinanData.db'

    print(" ")
    print(f"\033[1;33mRunning Last Close \033[0m")
    print(" ")

    update_stock_closes(api_key, db_name, progress_callback)

    print(" ")