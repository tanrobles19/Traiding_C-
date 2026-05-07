from benzinga import news_data
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timedelta
from datetime import date

@dataclass
class News:
    id: int
    author: Optional[str]
    created: str
    created_hour_cr: int
    created_minute_cr: int
    title: str
    url: str

def extract_cr_hour_minute(est_str: str) -> tuple[int, int]:
    """
    Convierte la hora en EST (hora estándar del este) a la hora de Costa Rica (CR).
    """
    dt = datetime.strptime(est_str, "%a, %d %b %Y %H:%M:%S %z")
    cr_time = dt - timedelta(hours=2)  # EST → UTC-5, CR = UTC-6 → diferencia usual = 1h
    return cr_time.hour, cr_time.minute

def is_recent_news(news_hour: int, news_minute: int, current_time: datetime) -> bool:

    news_time = timedelta(hours=news_hour, minutes=news_minute)
    current_time_in_minutes = timedelta(hours=current_time.hour, minutes=current_time.minute)
    
    time_diff = current_time_in_minutes - news_time
    FOR_THE_LAST_MINUTE =5
    return time_diff <= timedelta(minutes=FOR_THE_LAST_MINUTE)

def get_benzinga_news(symbol: str, fecha: str) -> List[News]:
    api_key = "bz.4KCPALWSMP2MNWOIFFYEHANTDL7ANAMJ"
    paper = news_data.News(api_key)

    stories = paper.news(company_tickers=symbol, base_date=fecha)
    news_list: List[News] = []

    current_time = datetime.now()

    for item in stories:
        hour, minute = extract_cr_hour_minute(item.get("created"))
        
        if is_recent_news(hour, minute, current_time):
            news = News(
                id=item.get("id"),
                author=item.get("author"),
                created=item.get("created"),
                created_hour_cr=hour,
                created_minute_cr=minute,
                title=item.get("title"),
                url=item.get("url")
            )
            news_list.append(news)

    return news_list

def print_news_summary_benzinga(news_list: List[News]) -> None:
    for news in news_list:
        hour = news.created_hour_cr
        minute = str(news.created_minute_cr).zfill(2) 
        print(f"Title = {news.title}")
        print(f"Date = {hour}:{minute}")
        print() 

# today = "2025-06-17"
# benzinga_news_list = get_benzinga_news("FGL", today)
# print(benzinga_news_list[0].id)

