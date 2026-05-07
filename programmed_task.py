import schedule
import time
import asyncio
from multiprocessing_websocket_rv_hour import mainT

from datetime import datetime

def print_current_time():
    current_time = datetime.now()
    formatted_time = current_time.strftime("%H:%M:%S:%f")
    return formatted_time[:-3]

# Evita que se ejecute múltiples veces en el mismo ciclo
def job():
    print("Running the scheduled job...")
    mainT()
    print("Job completed.")

schedule.every().day.at("17:58").do(job)

print(" ")
print(f"Time 10:35= {print_current_time()}")               
print(" ")

# Control del ciclo principal
while True:
    schedule.run_pending()  # Ejecutar trabajos pendientes
    time.sleep(30)  # Intervalo e