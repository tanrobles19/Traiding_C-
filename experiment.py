import sqlite3


def get_avg_month_volume(cursor, ticker):    
    cursor.execute("SELECT avg_month_volume FROM Stocks WHERE ticker = ?", (ticker,))
    
    result = cursor.fetchone()
    
    if result:
        return result[0]
    else:
        print(f"Ticker {ticker} no encontrado en la base de datos.")
        return None

def read_history_by_min_today(cursor, avg_month_volume, stock_id):
    
    cursor.execute("SELECT close, volume, hour, minute, amPm FROM HistoryByMinToday WHERE stockID = ?", (stock_id,))
    
    accumulated_volume = 0
    
    rows = cursor.fetchall()
    for row in rows:
        volume = row[1]
        
        accumulated_volume += volume
        
        # print(f"Close: {close}, Volume: {volume}")
        hour = row[2]
        amPm = row[4]
        if accumulated_volume > avg_month_volume and hour < 7 and amPm == 'AM':
            close = row[0]
            minute = row[3]
            print(f"Ticker: {stock_id} - Close {close}, Hour: {hour}, Minute: {minute}, Accumulated Volume: {accumulated_volume}")
            break

conn = sqlite3.connect('histFinanData.db')
cursor = conn.cursor()

cursor.execute("SELECT ticker FROM Stocks")    
tickers = cursor.fetchall()

for (symbol,) in tickers:
    avg_month_volume = get_avg_month_volume(cursor, symbol)

    read_history_by_min_today(cursor, avg_month_volume, symbol)