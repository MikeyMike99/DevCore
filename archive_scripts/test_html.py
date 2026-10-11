from bs4 import BeautifulSoup

with open('templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
print(f"Body has {len(soup.body.contents)} children")
print(f"Scripts: {len(soup.find_all('script'))}")
print(f"Forms: {len(soup.find_all('form'))}")
