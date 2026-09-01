import json
import os
import sys
import urllib.parse
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib3

# SSL uyarılarını kapat
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://dinhizmetleri.diyanet.gov.tr"
TARGET_URL = f"{BASE_URL}/kategoriler/yayinlarimiz/hutbeler/t%C3%BCrk%C3%A7e"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive"
}

def clean_url(rel_url):
    if not rel_url:
        return None
    return urllib.parse.urljoin(BASE_URL, rel_url.strip())

def parse_date(date_str):
    try:
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str.strip()

def fetch_turkish_hutbeler():
    print(f"[{datetime.utcnow()}] Diyanet Türkçe hutbeleri çekiliyor...")
    try:
        session = requests.Session()
        response = session.get(TARGET_URL, headers=HEADERS, timeout=30, verify=False)
        response.raise_for_status()
    except Exception as e:
        print(f"Bağlantı hatası: {e}")
        # Hata anında build'in tamamen çökmemesi için
        sys.exit(1)

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", {"id": "onetidDoclibViewTbl0"})

    if not table:
        table = soup.find("table", class_=lambda x: x and "ms-listviewtable" in x)

    if not table:
        print("Hata: Hutbe tablosu DOM içinde bulunamadı!")
        sys.exit(1)

    hutbeler = []
    rows = table.find_all("tr", class_=lambda x: x and "ms-itmhover" in x)

    for idx, row in enumerate(rows):
        cols = row.find_all("td")
        if len(cols) < 6:
            continue

        raw_date = cols[1].get_text(strip=True)
        title = cols[2].get_text(strip=True)

        pdf_tag = cols[3].find("a")
        doc_tag = cols[4].find("a")
        ses_tag = cols[5].find("a")

        formatted_date = parse_date(raw_date)

        hutbeler.append({
            "id": f"hutbe_{formatted_date.replace('-', '')}_{idx + 1}",
            "title": title,
            "date": formatted_date,
            "raw_date": raw_date,
            "language": "tr",
            "pdf_url": clean_url(pdf_tag["href"]) if pdf_tag and pdf_tag.has_attr("href") else None,
            "doc_url": clean_url(doc_tag["href"]) if doc_tag and doc_tag.has_attr("href") else None,
            "audio_url": clean_url(ses_tag["href"]) if ses_tag and ses_tag.has_attr("href") else None
        })

    payload = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "total_count": len(hutbeler),
        "data": hutbeler
    }

    with open("hutbeler.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Başarılı: {len(hutbeler)} adet hutbe 'hutbeler.json' dosyasına kaydedildi.")

if __name__ == "__main__":
    fetch_turkish_hutbeler()
