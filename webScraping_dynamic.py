import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, date

def print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]


def get_press_releases(url):

    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    news_items = soup.find_all('div', class_='category-press-release')
    # print(articles)

    for item in news_items:
        title = item.find('h4', class_='news-item-title').text.strip()
        date = item.find('span', class_='news-item-date').text.strip()
        print(f"Título: {title}\nFecha: {date}\n")

print(print_current_time())
url = "https://www.impactbiomedinc.com/news/"
get_press_releases(url)
print(print_current_time())