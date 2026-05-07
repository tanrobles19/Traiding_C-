import sqlite3
from colorama import Fore, Style, init

# Inicializar colorama
init(autoreset=True)

conn = sqlite3.connect('histFinanData.db')
cursor = conn.cursor()

# Mostrar la tabla QueueBehavior
print(Fore.CYAN + "Stocks Table - Short Squeeze Candidates")
print("\n" + "-"*40 + "\n")

# Ejecutar consulta para QueueBehavior
# cursor.execute("SELECT * FROM TradeSignalsBuyPerSecond")

# rows = cursor.fetchall()

# print(f"TradeSignalsBuyPerSecond = {len(rows)}")

cursor.execute("SELECT * FROM Stocks WHERE float <= 7000000  AND short_percent_float > 0.09  AND close BETWEEN 1 AND 7")

rows = cursor.fetchall()

for row in rows:
    print(row)


cursor.execute("SELECT * FROM Stocks WHERE ticker = 'NERV'")

rows = cursor.fetchall()

print("  ")
for row in rows:
    print(row)


conn.close()