import sqlite3
# from ib_insync import *

# # Conéctate al contenedor de IBKR Gateway (en el mismo servidor: localhost)
# ib = IB()
# ib.connect('127.0.0.1', 4002, clientId=1)

# # Verifica la conexión
# print(f"Connected: {ib.isConnected()}")

# positions = ib.positions()
    
# for pos in positions:

#     print(pos)


conn = sqlite3.connect('histFinanData.db')
cursor = conn.cursor()     



conn.close()         