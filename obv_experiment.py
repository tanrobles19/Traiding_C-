import sqlite3
import pandas as pd

conn = sqlite3.connect('histFinanData.db')
cursor = conn.cursor()

stock_id = 'RVYL'
query = """
    SELECT close, volume, date, hour, minute
    FROM HistoryByMin
    WHERE stockID = ?
    ORDER BY date, hour, minute
"""
cursor.execute(query, (stock_id,))

data = cursor.fetchall()
df = pd.DataFrame(data, columns=['close', 'volume', 'date', 'hour', 'minute'])

df['OBV'] = 0
for i in range(1, len(df)):
    if df['close'][i] > df['close'][i-1]:
        df.loc[i, 'OBV'] = df.loc[i-1, 'OBV'] + df.loc[i, 'volume']
    elif df['close'][i] < df['close'][i-1]:
        df.loc[i, 'OBV'] = df.loc[i-1, 'OBV'] - df.loc[i, 'volume']
    else:
        df.loc[i, 'OBV'] = df.loc[i-1, 'OBV']

df.to_csv('obv.csv', index=False)

conn.close()





import sqlite3
import numpy as np

conn = sqlite3.connect('histFinanData.db')
cursor = conn.cursor()

def calculate_relative_volume(symbol, hour, minute, ampm):

    query = """
    SELECT 
        COUNT(*) AS count_result, 
        SUM(volume) / COUNT(*) AS relative_volume
    FROM 
        HistoryByMin
    WHERE 
        stockID = ? 
        AND hour = ? 
        AND minute = ? 
        AND amPm = ?
    """

    cursor.execute(query, (symbol, hour, minute, ampm))

    result = cursor.fetchone()

    if result:
        count_result, relative_volume = result
        return count_result, relative_volume
    else:
        return 0, 0.0

def get_recent_prices(ticker, limit=7):
    import sqlite3

    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()

    query = """
        SELECT close
        FROM MinuteCandles
        WHERE ticker = ?
        ORDER BY id DESC
        LIMIT ?
    """
    cursor.execute(query, (ticker, limit))
    
    # Invertimos la lista porque se trae en orden descendente
    precios = [row[0] for row in cursor.fetchall()][::-1]

    conn.close()
    return precios if len(precios) >= limit else []    

def fetch_and_test(stockID):

    query = """
    SELECT * FROM HistoryByMinToday
    WHERE stockID = ?
    """
    
    cursor.execute(query, (stockID,))
    
    rows = cursor.fetchall()
    
    for row in rows:
        stock_id = row[1]  # stockID
        close = row[2]     # close
        volume = row[3]    # volume
        date = row[4]      # date
        hour = row[5]      # hour
        minute = row[6]    # minute
        amPm = row[7]      # amPm
        
        webSocketTest(stock_id, hour, minute, amPm, close, volume)

def webSocketTest(symbol, hour, minute, amPM, close, volume):

    cursor.execute("""
        INSERT INTO MinuteCandles (ticker, hour, minute, close, volume) 
        VALUES (?, ?, ?, ?, ?)
    """, (symbol, hour, minute, close, volume))    

    conn.commit()

    precios = get_recent_prices(symbol, limit=5)

    
    if len(precios) > 4:

        x = np.arange(len(precios))
        y = np.array(precios)
        print(precios)

        slope, intercept = np.polyfit(x, y, 1)      

        if slope > 0.03:
            slope_rounded = round(slope, 3)
            print(f"{symbol} - S: {slope_rounded} time {hour}:{minute} {amPM} $: {precios[-1]} V -> {volume}")

            if slope > 0.2:  # Condición extrema    
                print(f"{symbol} - S: {slope_rounded} $: {precios[-1]} Volume -> {volume}*************")        


    count, relative_volume = calculate_relative_volume(symbol, hour, minute, amPM)

    if count > 0:
        # Calcular el factor de Relative Volume
        relative_volume_factor = volume / relative_volume
        
        # Redondear a 2 decimales
        relative_volume_factor = round(relative_volume_factor, 2)

        if relative_volume_factor > 50:        
            print(f"{hour}:{minute} {amPM} - Count: {count}, Relative Volume: {relative_volume}, Volume: {volume}, Relative Volume Factor: {relative_volume_factor}X")

fetch_and_test('RVYL')

conn.close()
