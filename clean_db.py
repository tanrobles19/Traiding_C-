import sqlite3
import mysql.connector

def clear_all_tables():

    print(f"\033[1;33mClearing all database tables... \033[0m")          

    print(" ")
    
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    tables = [
        "AggregatesByMin",
        "AggregatesBySecondOpen",
        "HistoryByMinToday",        
        "HistoryByMin",                
        "Orders",
        "QueueBehavior",
        "ResistanceSignals",
        "RelativeVolumeRatio",
        "TradeSignalsBuyPerSecond",
        "RelativeVolumeRatioHour",
        "TradeSignalsLive",
        "AggregatesBySecondExperiment",
        "TradeSignalsRaw",
        "TradeSignalSell",
        "TradeSignalsMonitorGrowth"
    ]

    for table in tables:
        cursor.execute(f"DELETE FROM {table}")
        print(f"Deleting data from: {table}")

    conn.commit()
    conn.close()

    print(" ")

def clear_day_work_tables():

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()                  

    print(f"\033[1;33mClearing Work day tables! \033[0m")

    print(" ")

    tables = [
        "QueueBehavior",
        "Orders",
        "trades",
        "HistoryByMin",       # Re-downloaded fresh by Step 4 (last 5 business days). Plain INSERT — without truncate, runs would accumulate duplicates.
        "HistoryByMinToday",  # CRITICAL: Clear intraday table
        "RelativeVolumeRatio",
        "TradeSignalsBuyPerSecond",
        "RelativeVolumeRatioHour",  # Recalculated from HistoryByMin in Step 5
        "minute_candlesticks",
    ]

    for table in tables:
        mysql_cursor.execute(f"DELETE FROM {table}")
        db_connection.commit()

        print(f"Deleting data from: {table}")

    mysql_cursor.close()
    db_connection.close()        

    print(" ")

def clear_intradia_tables():

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )

    mysql_cursor = db_connection.cursor()                  

    print(f"\033[1;33mClearing Work day tables! \033[0m")          

    print(" ")
    
    tables = [
        "QueueBehavior",
        "Orders",  
        "trades",
        "RelativeVolumeRatio",
        "TradeSignalsBuyPerSecond",
        "minute_candlesticks",
    ]   

    for table in tables:
        mysql_cursor.execute(f"DELETE FROM {table}")
        db_connection.commit()

        print(f"Deleting data from: {table}")

    mysql_cursor.close()
    db_connection.close()        

    print(" ")    
