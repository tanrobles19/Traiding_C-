from ib_insync import *
from polygon import RESTClient
from datetime import datetime, timedelta, date
import time
import asyncio

def print_current_time_microseconds():
    current_time = datetime.now()
    # %f = microsegundos (6 dígitos)
    formatted_time = current_time.strftime("%H:%M:%S.%f")
    return formatted_time

def get_real_time_news(symbol, clientId): 
    ib = IB()
    ib.connect('127.0.0.1', 7496, clientId=clientId)

    # Obtener los proveedores de noticias disponibles
    newsProviders = ib.reqNewsProviders()
    print(newsProviders)
    print("  ")

    codes = '+'.join(np.code for np in newsProviders)
    # print(f"Códigos de proveedores de noticias: {codes}")

    mogo = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(mogo)

    ib.reqMktData(mogo, "mdoff,292:" + codes, False, False, [])

    # Sobrecargar el método tickNews para recibir noticias en tiempo real
    def tickNews(tickerId, timeStamp, providerCode, articleId, headline, extraData):
        # Convertir el timestamp de milisegundos a segundos
        formatted_time = datetime.datetime.fromtimestamp(timeStamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
        print(f"\nFecha: {formatted_time}")
        print(f"Proveedor: {providerCode}")
        print(f"Titular: {headline}")
        print(f"Extra Data: {extraData}")

    # Registrar el método para recibir noticias
    ib.wrapper.tickNews = tickNews

    # Esperar para recibir noticias en tiempo real
    ib.run()

    # Desconectar
    ib.disconnect()


def get_news(symbol):

    ib = IB()
    ib.connect('127.0.0.1', 7497, clientId=101)

    newsProviders = ib.reqNewsProviders()

    codes = '+'.join(np.code for np in newsProviders)

    amd = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(amd)

    headlines = ib.reqHistoricalNews(amd.conId, codes, '', '', 10)

    if not headlines:
        print(f"NO HEADLINES FOUND**************** {symbol}")
        return

    today = datetime.now().date()

    count = 0

    for headline in headlines:

        # formatted_time = headline.time.strftime('%Y-%m-%d %H:%M:%S')
        # print(f"\nFecha: {formatted_time}")
        # print(f"Proveedor: {headline.providerCode}")
        print(f"Titular: {headline.headline}")
        count += 1

    print(f"Total de noticias obtenidas: {count}")
    
    ib.disconnect()   
    return count
    
def has_active_sell_order(symbol: str, clientId: int, port: int) -> bool:
    ib = IB()
    ib.connect('127.0.0.1', port, clientId=clientId)

    open_trades = ib.reqAllOpenOrders()
    print(f"Órdenes abiertas: {open_trades}")


    # time.sleep(60)  # Esperar un poco para asegurarse de que las órdenes se hayan cargado

    for trade in open_trades:
        if (
            trade.contract.symbol.upper() == symbol.upper()
            and trade.order.action == 'SELL'
            and trade.orderStatus.status in ('PreSubmitted', 'Submitted')

        ):
            print(f"Cancelando orden de venta para {symbol}...")
            # ib.cancelOrder(trade.order)
            return True

    # ib.disconnect()
    return False    

async def put_order_interactive_brokers(client, ib, port, symbol, number):    

    stock = Stock(symbol, 'SMART', 'USD')

    order = LimitOrder('BUY',number, client.get_last_quote(symbol).ask_price, outsideRth=True)

    trade = ib.placeOrder(stock, order)

    print(trade)


def get_current_positions(ib):
    positions = ib.positions()
    for pos in positions:
        print(pos)    




# PAPER_PORT = 7497                    # Port used to connect to the IBK Paper account.
PORT = 7496                           # Port used for real money trading.

# symbol = "ZVSA"

# async def process_trade_signal(ib):
# newsCount = get_news("ATHE")
# print(f"Total de noticias obtenidas: {newsCount}")
#     print("4")

# async def main():
#     print("1")
#     ib = IB()
#     await ib.connectAsync('127.0.0.1', 7497, clientId=1)

#     # Crear 10 tareas concurrentes
#     tasks = [process_trade_signal(ib) for _ in range(10)]
#     await asyncio.gather(*tasks)

#     print("3")

#     ib.disconnect()

# asyncio.run(main())

# print("Final") 

# has_active_sell_order('SNAL', 0, PAPER_PORT)

# api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
# client = RESTClient(api_key)

# PAPER_PORT_IBKR_GATEWAY = 4002

# put_order_interactive_brokers(client, 0, PAPER_PORT_IBKR_GATEWAY, "SGBX", 1)

# ib = IB()
# ib.connect('127.0.0.1', PORT, clientId=0)



# print(print_current_time())
# put_order_interactive_brokers(client, ib, PORT, "TSLA", 1)
# # print(client.get_last_quote("TSLA").ask_price)
# print(print_current_time())

# ib.disconnect()

# print("Has active sell order:", has_active_sell_order('AMBC', 0, PAPER_PORT))

# ib = IB()
# ib.connect('127.0.0.1', 7497, clientId=34)

# get_current_positions(ib)


# api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
# client = RESTClient(api_key)         

# symbol = "APM"


# PRE_ask_price = client.get_last_quote(symbol).ask_price
# ask_size = client.get_last_quote(symbol).ask_size

# bid_price = client.get_last_quote(symbol).bid_price
# bid_size = client.get_last_quote(symbol).bid_size  

# last_trade_price = client.get_last_trade(symbol).price


# print("Last Trade")
# print(client.get_last_trade(symbol))

# print("Last Quote")
# print(client.get_last_quote(symbol))

async def test():
    print(f"{print_current_time_microseconds()} = Test")

    PAPER_PORT_IBKR_GATEWAY = 4002

    ib = IB()    

    await ib.connectAsync('127.0.0.1', PAPER_PORT_IBKR_GATEWAY, clientId=1)    
    # await ib.connectAsync('127.0.0.1', PORT_IBKR_GATEWAY, clientId=0)    

    api_key = "0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ"
    client = RESTClient(api_key)
    
    client.get_last_quote("SGBX").ask_price

    put_order_interactive_brokers(client, ib, PAPER_PORT_IBKR_GATEWAY, "SGBX", 1)


# async def main():

#     print(print_current_time_microseconds())
#     asyncio.create_task(
#         # get_real_time_news('PFE', clientId=19)
#     )
#     print(print_current_time_microseconds())



# asyncio.run(main())

get_real_time_news('PFE', clientId=19)