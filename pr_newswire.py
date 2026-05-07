import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz

def get_prnewswire_news(symbol):

    today = datetime.now().strftime("%b %d, %Y")  # Ejemplo: Jun 23, 2025
    current_time = datetime.now(pytz.timezone('America/Costa_Rica'))  # Hora actual en Costa Rica

    # Zona horaria de Costa Rica (CST)
    cr_timezone = pytz.timezone('America/Costa_Rica')

    url = f"https://www.prnewswire.com/search/all/?keyword={symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    # Buscar todas las noticias
    news_cards = soup.find_all("div", class_="card posOrder")
    news_list = []

    for card in news_cards:
        # Extraer la fecha
        date = card.find("small")
        date = date.text.strip() if date else "No date found"

        # Convertir la fecha a la zona horaria correcta (CST)
        if "ET" in date:
            date = date[:-3]
            
            try:
                date_obj = datetime.strptime(date, "%b %d, %Y, %I:%M %p")  # Para fechas con AM/PM
            except ValueError:

                date_obj = datetime.strptime(date, "%b %d, %Y, %H:%M")  # Para fechas en formato de 24 horas
            date_obj = pytz.timezone('US/Eastern').localize(date_obj)  # La hora está en Eastern Time (ET)
            date_obj = date_obj.astimezone(cr_timezone)  # Convertir a Costa Rica (CST)
            date = date_obj.strftime("%b %d, %Y, %I:%M %p CST")

        if today not in date:
            continue

        time_difference = current_time - date_obj
        LAST_60_MINUTES = 5
        if time_difference > timedelta(minutes=LAST_60_MINUTES):
            continue

        title_tag = card.find("a", class_="news-release")
        title = title_tag.text.strip() if title_tag else "No title found"
        url = "https://www.prnewswire.com" + title_tag['href'] if title_tag else "No URL found"

        return title

    # print(f"No recent news found for the symbol -> {symbol}")
    # print(f"URL -> {url}")

    return "none"

print(get_prnewswire_news("HCWB"))
