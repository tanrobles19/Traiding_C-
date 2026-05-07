import sqlite3
from collections import defaultdict

globalCont = 0


def check_stock_conditions(ticker, close_threshold, volume_threshold, cursor):

    cursor.execute('''
        SELECT COUNT(*) FROM MinuteCandles WHERE ticker = ? AND close > ?
    ''', (ticker, close_threshold))
    close_check = cursor.fetchone()[0]

    cursor.execute('''
        SELECT COUNT(*) FROM MinuteCandles WHERE ticker = ? AND volume > ?
    ''', (ticker, volume_threshold))
    volume_check = cursor.fetchone()[0]

    print(f"Close check for {ticker}: {close_check}, Volume check: {volume_check}")

    if close_check > 0 or volume_check > 0:
        return True
    else:
        return False

def is_symbol_registered(symbol: str, conn, cursor) -> bool:

    try:
        cursor.execute("SELECT COUNT(*) FROM TradeSignalsBuy WHERE symbol = ?", (symbol,))
        
        count = cursor.fetchone()[0]

        return count > 0

    except sqlite3.Error as e:
        print(f"Error al acceder a la base de datos: {e}")
        return False

def get_close_price(ticker: str, conn, cursor) -> float:
    try:
        cursor.execute("SELECT close FROM Stocks WHERE ticker = ?", (ticker,))
        
        row = cursor.fetchone()

        if row:
            return row[0]
        else:
            return -1

    except sqlite3.Error as e:
        print(f"Error al acceder a la base de datos: {e}")
        return -1

def get_relative_volume(hour, minute, am_pm, ticker, cursor):
    cursor.execute('''
        SELECT relative_volume
            FROM RelativeVolumeRatio
                WHERE hour = ? 
                AND minute = ?
                AND amPm = ?
                AND symbol =?
    ''', (hour, minute, am_pm, ticker))

    row = cursor.fetchone()
    return row[0] if row is not None else -1

def minutes_since_midnight(hour, minute, am_pm):
    if am_pm == 'PM' and hour != 12:
        hour += 12
    elif am_pm == 'AM' and hour == 12:
        hour = 0
    return hour * 60 + minute

def fetch_and_test(stockID, conn, cursor):
    global globalCont
    activity_log = defaultdict(list)

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
        
        webSocketTest(stock_id, hour, minute, amPm, close, volume, cursor, activity_log)

    # Análisis de secuencias justo después de cada stock
    # revisar_secuencias_validas(activity_log)

def webSocketTest(symbol, hour, minute, amPM, close, volume, cursor, activity_log):
    global globalCont
    relative_volume = get_relative_volume(hour, minute, amPM, symbol, cursor)

    cursor.execute("""
        INSERT INTO MinuteCandles (ticker, hour, minute, close, volume) 
        VALUES (?, ?, ?, ?, ?)
    """, (symbol, hour, minute, close, volume))    

    conn.commit()    

    if isinstance(relative_volume, (int, float)) and relative_volume > 0 and relative_volume != -1:

        if relative_volume == 0:
            relative_volume = 1000

        relative_volume_factor = round(volume / relative_volume, 2)

        close_price = get_close_price(symbol, conn, cursor)

        if relative_volume_factor >= 10  and close >= close_price * 1.10:
            
            globalCont += 1
            # activity_log[symbol].append((hour, minute, amPM, relative_volume_factor, volume, close))
            # registros = activity_log[symbol]

            # if len(registros) >= 3:
            #     # Tomar las últimas 3 entradas
            #     v1, v2, v3= registros[-3:]

            #     t1 = minutes_since_midnight(v1[0], v1[1], v1[2])
            #     t2 = minutes_since_midnight(v2[0], v2[1], v2[2])
            #     t3 = minutes_since_midnight(v3[0], v3[1], v3[2])

            #     close1 = v1[5]
            #     close2 = v2[5]
            #     close3 = v3[5]

            #     if close2 > close1:
            #         if t2 == t1 + 1:

                        # print(f"Processing {symbol} - Hour: {hour}, Minute: {minute}, AM/PM: {amPM}, Relative Volume: {relative_volume_factor}X, Volume: {volume}, Close: {close}")                        

            if is_symbol_registered( symbol, conn, cursor)  == False:
                print(f"NEW SYMBOL {symbol} time {hour}:{minute} {amPM} Relative Volume Ratio: {relative_volume_factor}X Volume {volume} Close {close}")

            cursor.execute('''
                    INSERT INTO TradeSignalsBuy (
                        symbol, hour, minute, amPm, date, close, volume,
                        relative_volume, polygon_news, benzinga_news, finnhub_news
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    hour,  # hour
                    minute,  # minute
                    amPM,  # amPm
                    "",     # date — puedes reemplazar esto si tienes la fecha original
                    close,  # close
                    volume,  # volume
                    relative_volume_factor,  # relative_volume
                    None,   # polygon_news
                    None,   # benzinga_news
                    None    # finnhub_news
                ))    

            inserted_id = cursor.lastrowid
            conn.commit()

                        # executor.submit(search_news, inserted_id, symbol)     

conn = sqlite3.connect('histFinanData.db')
cursor = conn.cursor()

cursor.execute("SELECT ticker FROM Stocks")
symbols = cursor.fetchall()

print(f"Retrieved {len(symbols)} stocks.")

for (symbol,) in symbols:
    print(symbol)
    fetch_and_test(symbol, conn, cursor)

print(f"Total processed: {globalCont}")

conn.close()