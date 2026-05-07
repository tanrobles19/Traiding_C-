from polygon import RESTClient
from polygon.rest.models import TickerNews
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
import pytz

costa_rica_tz = pytz.timezone('America/Costa_Rica')

@dataclass
class PolygonNews:
    ticker: str
    title: str
    description: str
    url: str
    published_utc: str
    sentiment: Optional[str]
    keywords: List[str]
    publisher: Optional[str]
    hora_cr: int
    minuto_cr: int
    fecha_cr: datetime

    @staticmethod
    def from_ticker_news(ticker: str, news: TickerNews) -> 'PolygonNews':
        # Convertir string UTC a datetime y luego a hora local CR
        dt_utc = datetime.strptime(news.published_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
        dt_cr = dt_utc.astimezone(costa_rica_tz)

        return PolygonNews(
            ticker=ticker,
            title=news.title,
            description=news.description,
            url=news.article_url,
            published_utc=news.published_utc,
            sentiment=news.insights[0].sentiment if news.insights else None,
            keywords=news.keywords,
            publisher=news.publisher.name if news.publisher else None,
            hora_cr=dt_cr.hour,
            minuto_cr=dt_cr.minute,
            fecha_cr=dt_cr
        )

def get_polygon_news(symbol: str, fecha: str) -> List[PolygonNews]:    
    client = RESTClient("0oQUg6UgH34Ala4OF_YYObsT_5Jh2IBJ")
    noticias: List[PolygonNews] = []
    
    # Obtener hora actual en Costa Rica
    now_cr = datetime.now(costa_rica_tz)

    for n in client.list_ticker_news(
        ticker=symbol,
        published_utc=fecha,
        order="asc",
        limit="10",
        sort="published_utc",
    ):
        news = PolygonNews.from_ticker_news(symbol, n)
        
        # Filtrar noticias que hayan sido publicadas en los últimos 10 minutos
        if (now_cr - news.fecha_cr).total_seconds() <= 600:  # 600 segundos = 10 minutos
            noticias.append(news)

    return noticias

# resultado = get_polygon_news("IMRX", "2025-06-17")
# print(resultado[0].title)

# if(len(resultado) == 0):
#     print("No hay noticias para el ticker LYRA en la fecha 2025-06-02")

# for n in resultado:
#     print(n)
