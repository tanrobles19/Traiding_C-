import requests
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime, timedelta

@dataclass
class News:
    id: int
    author: Optional[str]
    created: str  # Fecha y hora completa legible en Costa Rica
    created_hour_cr: int
    created_minute_cr: int
    title: str
    url: str

def map_finnhub_to_news(item: dict) -> News:
    dt_utc = datetime.utcfromtimestamp(item['datetime'])
    dt_cr = dt_utc - timedelta(hours=6)

    return News(
        id=item['id'],
        author=item.get('source', None),
        created=dt_cr.strftime('%Y-%m-%d %H:%M:%S'),
        created_hour_cr=dt_cr.hour,
        created_minute_cr=dt_cr.minute,
        title=item['headline'],
        url=item['url']
    )

def is_recent_news(news_hour: int, news_minute: int, current_time: datetime) -> bool:
    news_time = timedelta(hours=news_hour, minutes=news_minute)
    current_time_minutes = timedelta(hours=current_time.hour, minutes=current_time.minute)
    time_diff = current_time_minutes - news_time
    return timedelta(minutes=0) <= time_diff <= timedelta(minutes=5)

def get_finnhub_news(symbol: str) -> List[News]:
    api_key = "d1aq0a1r01qjhvtqlbbgd1aq0a1r01qjhvtqlbc0"
    today = datetime.utcnow().strftime('%Y-%m-%d')  # Fecha actual en UTC (se ajustará a CR más adelante)
    url = f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from={today}&to={today}&token={api_key}"

    response = requests.get(url)
    if response.status_code == 200:
        news_data = response.json()
        all_news = [map_finnhub_to_news(item) for item in news_data]
        now_cr = datetime.utcnow() - timedelta(hours=6)

        recent_news = [
            n for n in all_news if is_recent_news(n.created_hour_cr, n.created_minute_cr, now_cr)
        ]
        return recent_news
    else:
        print("Error:", response.status_code)
        print(response.text)
        return []


# news_list = get_finnhub_news("URG")
# print(news_list)

# for news in news_list:
#     print(f"[{news.created_hour_cr:02d}:{news.created_minute_cr:02d}] {news.title}")