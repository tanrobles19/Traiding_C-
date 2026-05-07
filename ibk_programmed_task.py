import schedule
import time
import subprocess
import os
from datetime import datetime

def print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]

def job():
    print("Running the scheduled job...")

    os.chdir('/home/ubuntu/ib-gateway-docker') 

    subprocess.run(["docker-compose", "down"], check=True)

    subprocess.run(["docker-compose", "up", "--build"], check=True)

schedule.every().day.at("10:00").do(job)

print(" ")
print(f"Time 10:00= {print_current_time()}")               
print(" ")

while True:
    schedule.run_pending()
    time.sleep(30)