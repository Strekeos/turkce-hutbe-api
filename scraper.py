import asyncio
import io
import json
import os
import re
import urllib.parse
from datetime import datetime
from pypdf import PdfReader
from playwright.async_api import async_playwright
import requests

BASE_URL = "https://dinhizmetleri.diyanet.gov.tr"
TARGET_URL = f"{BASE_URL}/kategoriler/yayinlarimiz/hutbeler/t%C3%BCrk%C3%A7e"

SURA_MAP = {
    "fatiha": 1, "bakara": 2, "al-i imran": 3, "âl-i imrân": 3, "ali imran": 3,
    "nisa": 4, "nisâ": 4, "maide": 5, "mâide": 5, "enam": 6, "en'am": 6, "araf": 7,
    "enfal": 8, "tevbe": 9, "yunus": 10, "hud": 11, "yusuf": 12, "isra": 17, "isrâ": 17
}

def clean_url(rel_url):
    if not rel_url:
        return None
    return urllib.parse.urljoin(BASE_URL, rel_url.strip())

def parse_date(date_str):
    try:
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d"), date_str.strip()
    except Exception:
        return date_str.strip(), date_str.strip()

def fetch_arabic_ayah(surah_num, ayah_num):
    try:
        url = f"https://api.alquran.cloud/v1/ayah/{surah_num}:{ayah_num}/quran-uthmani"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return res.json().get("data", {}).get("text", "")
    except Exception:
        pass
    return ""

def extract_pdf_content(pdf_url):
    if not pdf_url:
        return None
    try:
        res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        res.raise_for_status()
        reader = PdfReader(io.BytesIO(res.content))
        full_text = "\n".join([page.extract_text() or "" for page in reader.pages])

        lines = [l.strip() for l in full_text.splitlines() if l.strip()]
        
        # Dipnotları ve paragrafları ayıkla
        footnotes = {}
        content_lines = []
        fn_pattern = re.compile(r'^\[([ivxlcdm0-9]+)\]\s*(.+)', re.IGNORECASE)

        for line in lines:
            fn_match = fn_pattern.match(line)
            if fn_match:
                footnotes[fn_match.group(1).lower()] = fn_match.group(2).strip()
            elif "Din Hizmetleri Genel Müdürlüğü" not in line and not line.startswith("Tarih:"):
                content_lines.append(line)

        # Ayet API tespiti
        verse_arabic = ""
        verse_source = ""
        hadith_source = ""

        for fn_id, fn_text in footnotes.items():
            match = re.search(r'([A-Za-zÇĞİÖŞÜçğıöşü\-\'\s]+),\s*(\d+)\s*/\s*(\d+)', fn_text)
            if match:
                sura_name = match.group(1).strip().lower()
                sura_num = SURA_MAP.get(sura_name, int(match.group(2)))
                ayah_num = int(match.group(3))
                verse_source = fn_text
                verse_arabic = fetch_arabic_ayah(sura_num, ayah_num)
                break

        for fn_id, fn_text in footnotes.items():
            if any(k in fn_text.lower() for k in ["buhârî", "buhari", "müslim", "tirmizî", "nesâî"]):
                hadith_source = fn_text
                break

        body_text = "\n\n".join(content_lines)
        summary = content_lines[0] if content_lines else ""
        if len(summary) > 220:
            summary = summary[:220] + "..."

        return {
            "summary": summary,
            "verse": {
                "arabic": verse_arabic,
                "source": verse_source
            },
            "hadith": {
                "source": hadith_source
            },
            "body": body_text,
            "footnotes": footnotes
        }
    except Exception as e:
        print(f"PDF okunamadı ({pdf_url}): {e}")
        return None

async def main():
    print("Playwright ile Diyanet sitesi açılıyor...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Sayfayı yükle
        await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_selector("table", timeout=15000)

        # Tablo satırlarını topla
        rows = await page.query_selector_all("tr.ms-itmhover, tr")
        print(f"DOM üzerinden bulunan satır sayısı: {len(rows)}")

        hutbeler = []
        for idx, row in enumerate(rows):
            cols = await row.query_selector_all("td")
            if len(cols) < 5:
                continue

            raw_date = (await cols[1].inner_text()).strip()
            title = (await cols[2].inner_text()).strip()

            # Linkleri topla
            pdf_el = await row.query_selector("a[href*='.pdf']")
            doc_el = await row.query_selector("a[href*='.doc']")
            ses_el = await row.query_selector("a[href*='.mp3']")

            pdf_url = clean_url(await pdf_el.get_attribute("href")) if pdf_el else None
            doc_url = clean_url(await doc_el.get_attribute("href")) if doc_el else None
            ses_url = clean_url(await ses_el.get_attribute("href")) if ses_el else None

            if not title or not raw_date:
                continue

            formatted_date, display_date = parse_date(raw_date)
            hutbe_id = f"hutbe_{formatted_date.replace('-', '')}_{idx + 1}"

            content_data = None
            if idx < 6 and pdf_url:
                print(f"[{idx+1}/6] PDF içeriği ve Arapça ayet taranıyor: {title}")
                content_data = extract_pdf_content(pdf_url)

            hutbeler.append({
                "id": hutbe_id,
                "title": title,
                "date": formatted_date,
                "raw_date": display_date,
                "language": "tr",
                "pdf_url": pdf_url,
                "doc_url": doc_url,
                "audio_url": ses_url,
                "content": content_data
            })

        await browser.close()

    payload = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "total_count": len(hutbeler),
        "data": hutbeler
    }

    with open("hutbeler.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Tamamlandı! {len(hutbeler)} adet hutbe başarıyla 'hutbeler.json' dosyasına yazıldı.")

if __name__ == "__main__":
    asyncio.run(main())
