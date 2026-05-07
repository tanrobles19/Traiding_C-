import sqlite3

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
        "RawTrades",        
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

def clear_all_tables():

    print(f"\033[1;33mClearing DAY Work Tables... \033[0m")          

    print(" ")
    
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    tables = [
        "Orders",
        "RawTrades",        
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