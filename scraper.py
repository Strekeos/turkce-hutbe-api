import json
import re
import urllib.parse
from datetime import datetime
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://dinhizmetleri.diyanet.gov.tr"
INITIAL_URL = f"{BASE_URL}/kategoriler/yayinlarimiz/hutbeler/t%C3%BCrk%C3%A7e"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
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

def extract_next_page_url(soup):
    # SharePoint sayfalandırma linkini onclick veya a taginden ayıklar
    next_link = soup.select_one("td#bottomPagingCellWPQ1 a")
    if not next_link:
        # Alternatif seçici
        next_img = soup.find("img", {"alt": "Sonraki"})
        if next_img and next_img.parent and next_img.parent.name == "a":
            next_link = next_img.parent

    if next_link and next_link.has_attr("onclick"):
        onclick_text = next_link["onclick"]
        # RefreshPageTo(event, "/Pages/Türkçe.aspx?Paged=TRUE...") desenini yakala
        match = re.search(r'RefreshPageTo\([^,]+,\s*["\']([^"\']+)["\']\)', onclick_text)
        if match:
            raw_path = match.group(1).replace("&amp;", "&")
            return clean_url(raw_path)

    return None

def fetch_all_turkish_hutbeler():
    current_url = INITIAL_URL
    all_hutbeler = []
    seen_ids = set()
    page_num = 1

    print("Diyanet Türkçe hutbe arşivinin tamamı taranıyor...")

    while current_url:
        print(f"Sayfa {page_num} çekiliyor: {current_url}")
        try:
            response = requests.get(current_url, headers=HEADERS, timeout=30)
            response.raise_for_status()
        except Exception as e:
            print(f"Sayfa çekilirken hata oluştu ({current_url}): {e}")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", {"id": "onetidDoclibViewTbl0"})

        if not table:
            print("Tablo bulunamadı veya sayfa sonuna gelindi.")
            break

        rows = table.find_all("tr", class_=lambda x: x and "ms-itmhover" in x)
        if not rows:
            break

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
            hutbe_id = f"hutbe_{formatted_date.replace('-', '')}_{title[:15].strip()}"

            # Yinelenen kayıtları önleme
            if hutbe_id in seen_ids:
                continue
            seen_ids.add(hutbe_id)

            all_hutbeler.append({
                "id": hutbe_id,
                "title": title,
                "date": formatted_date,
                "raw_date": raw_date,
                "language": "tr",
                "pdf_url": clean_url(pdf_tag["href"]) if pdf_tag and pdf_tag.has_attr("href") else None,
                "doc_url": clean_url(doc_tag["href"]) if doc_tag and doc_tag.has_attr("href") else None,
                "audio_url": clean_url(ses_tag["href"]) if ses_tag and ses_tag.has_attr("href") else None
            })

        # Sonraki sayfa bağlantısını al
        next_url = extract_next_page_url(soup)
        if next_url and next_url != current_url:
            current_url = next_url
            page_num += 1
        else:
            print("Son sayfaya ulaşıldı.")
            current_url = None

    payload = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "total_count": len(all_hutbeler),
        "data": all_hutbeler
    }

    with open("hutbeler.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\nİşlem Tamamlandı: Toplam {page_num} sayfadan {len(all_hutbeler)} adet hutbe başarıyla kaydedildi.")

if __name__ == "__main__":
    fetch_all_turkish_hutbeler()
