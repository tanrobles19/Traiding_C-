import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz

def get_globenewswire_news(symbol):
    url = f"https://www.globenewswire.com/en/search/keyword/{symbol}/date/24HOURS?pageSize=10"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    now_cr = datetime.now(pytz.timezone("America/Costa_Rica"))

    for div in soup.find_all("div", class_="mainLink"):
        a_tag = div.find("a")
        if a_tag:
            title = a_tag.text.strip()
            link = "https://www.globenewswire.com" + a_tag["href"]

            parent = div.find_parent("div", class_="newsLink")
            if parent:
                date_span = parent.find("div", class_="date-source").find("span")
                if date_span:
                    raw_date = date_span.text.strip().replace("ET", "").strip()
                    dt_naive = datetime.strptime(raw_date, "%B %d, %Y %H:%M")
                    
                    eastern = pytz.timezone("US/Eastern")
                    dt_est = eastern.localize(dt_naive)

                    cr_tz = pytz.timezone("America/Costa_Rica")
                    dt_cr = dt_est.astimezone(cr_tz)

                    # Verificar que la noticia sea de hoy
                    if dt_cr.date() != now_cr.date():
                        continue  # Si no es de hoy, saltamos a la siguiente noticia

                    FOR_THE_LAST_5_MINUTES =60

                    if now_cr - dt_cr > timedelta(minutes=FOR_THE_LAST_5_MINUTES):
                        continue  # Si la noticia tiene más de 5 minutos, saltamos a la siguiente

                    # Imprimir fecha en Costa Rica
                    print(f"Título: {title}")
                    print(f"Enlace: {link}")
                    print(f"Fecha en Costa Rica: {dt_cr.strftime('%Y-%m-%d %H:%M:%S')}")

                    return title  # Retornar el título de la primera noticia válida
    return "none"


def get_globenewswire_news_count(symbol):
    url = f"https://www.globenewswire.com/en/search/keyword/{symbol}/date/24HOURS?pageSize=10"

    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    # Contar las noticias encontradas
    news_count = len(soup.find_all("div", class_="mainLink"))

    if news_count > 0:
        return news_count
    else:
        return 0

print(get_globenewswire_news("AGM"))                    