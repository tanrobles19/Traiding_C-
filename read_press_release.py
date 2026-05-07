import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz

def print_current_time():
    current_time = datetime.now()
    
    formatted_time = current_time.strftime("%H:%M:%S:%f")

    return formatted_time[:-3]

def get_press_releases(url, symbol):

    headers = {"User-Agent": "Mozilla/5.0"} 
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    # Buscar todas las noticias
    for div in soup.find_all("div", class_="category-press-release"):
        a_tag = div.find("h4")
        a_div = div.find("time")
        a_url = div.find("a")
        url = ""
        title = ""
        datetime_str = ""
        if a_tag:
            url = a_url["href"]
            title = a_tag.text.strip()

        if a_div: 
            datetime_str = a_div.text.strip()

        print(f"Title: {title}")
        print(f"URL: {url}")
        print(f"Date and Time: {datetime_str}")
        print(" ")

# print(get_press_releases("https://www.acurxpharma.com/news-media/press-releases", "HCWB"))
print(print_current_time())
get_press_releases("https://www.impactbiomedinc.com/news/", "IBO")
print(print_current_time())