
import time
import redis
import sqlite3

# -------------------
# Redis setup (local)
# -------------------
r = redis.Redis(host='localhost', port=6379, decode_responses=True)



conn = sqlite3.connect('histFinanData.db')
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS TradeSignalsRaw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    hour INTEGER,
    minute INTEGER,
    close REAL,
    volume INTEGER,
    relative_volume REAL,
    timestamp INTEGER,
    purchasePrediction TEXT,
    relative_volume_hour REAL
)
""")
conn.commit()


def benchmark_redis(n=1000):
    start = time.perf_counter()
    for i in range(n):
        key = f"trade:{i}"
        value = {
            "symbol": "AAPL",
            "hour": 10,
            "minute": 30,
            "close": 150.25,
            "volume": 35000 + i,
            "relative_volume": 1.5,
            "timestamp": int(time.time() * 1000),
            "purchase_prediction": "BUY",
            "relative_volume_hour": 2.0
        }
        r.hset(key, mapping=value)
    elapsed = (time.perf_counter() - start) * 1000
    return elapsed / n


def benchmark_sqlite(n=1000):
    start = time.perf_counter()
    for i in range(n):
        cursor.execute("""
            INSERT INTO TradeSignalsRaw
            (symbol, hour, minute, close, volume, relative_volume, timestamp, purchasePrediction, relative_volume_hour)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("AAPL", 10, 30, 150.25, 35000 + i, 1.5, int(time.time() * 1000), "BUY", 2.0))
    conn.commit()
    elapsed = (time.perf_counter() - start) * 1000
    return elapsed / n



N = 1000
redis_avg = benchmark_redis(N)
sqlite_avg = benchmark_sqlite(N)

print(f"Redis avg per insert:  {redis_avg:.4f} ms")
print(f"SQLite avg per insert: {sqlite_avg:.4f} ms")