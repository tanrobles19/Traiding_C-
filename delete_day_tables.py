import sqlite3

conn = sqlite3.connect('histFinanData.db')
cursor = conn.cursor()

print("Delete Orders....")
print(" ")
cursor.execute("DELETE FROM Orders")
print("Delete TradeSignalsBuyPerSecond....")
print(" ")
cursor.execute("DELETE FROM TradeSignalsBuyPerSecond")
print("Delete QueueBehavior....")
print(" ")
cursor.execute("DELETE FROM QueueBehavior")
print("Delete RelativeVolumeRatioHour....")
print(" ")
cursor.execute("DELETE FROM RelativeVolumeRatioHour")
print("Delete RelativeVolumeRatio....")
print(" ")
cursor.execute("DELETE FROM RelativeVolumeRatio")
conn.commit()
# cursor.execute("SELECT symbol, timestamp_unix, local_utc_timestamp, purchasePrediction FROM TradeSignalsBuyPerSecond")
# cursor.execute("SELECT timestamp_unix, local_utc_timestamp FROM TradeSignalsBuyPerSecond")
conn.commit()
rows = cursor.fetchall()

for row in rows:
    print(row)

conn.close()