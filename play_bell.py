from playsound import playsound

from concurrent.futures import ThreadPoolExecutor
from polygon import RESTClient

executor = ThreadPoolExecutor(max_workers=5)

def process_signal_async():
    playsound('new_york_stock_exchange_opening_bell.m4a')

def play_bell():

    print("Hello")
    executor.submit(
        process_signal_async
    )
    print("bye!")

play_bell()