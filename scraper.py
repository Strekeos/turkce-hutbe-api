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
    "fatiha": 1, "fâtiha": 1, "bakara": 2, "al-i imran": 3, "âl-i imrân": 3, "ali imran": 3,
    "nisa": 4, "nisâ": 4, "maide": 5, "mâide": 5, "enam": 6, "en'am": 6, "araf": 7,
    "enfal": 8, "tevbe": 9, "yunus": 10, "hud": 11, "yusuf": 12, "isra": 17, "isrâ": 17
}

def clean_url(rel_url):
    return urllib.parse.urljoin(BASE_URL, rel_url.strip()) if rel_url else None

def parse_date(date_str):
    try:
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d"), date_str.strip()
    except Exception:
        return date_str.strip(), date_str.strip()

def fetch_ayah_details(surah_num, ayah_num):
    """Arapça Mushaf metnini (Besmele dahil) ve Diyanet mealini çeker"""
    arabic_text = ""
    turkish_meal = ""
    try:
        res_ar = requests.get(f"https://api.alquran.cloud/v1/ayah/{surah_num}:{ayah_num}/quran-uthmani", timeout=6)
        if res_ar.status_code == 200:
            arabic_text = res_ar.json().get("data", {}).get("text", "")
            # Fatiha (1) ve Tevbe (9) dışındaki surelerin başına Besmele ekle
            if surah_num not in [1, 9] and not arabic_text.startswith("بِسْمِ"):
                arabic_text = "بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ\n" + arabic_text

        res_tr = requests.get(f"https://api.alquran.cloud/v1/ayah/{surah_num}:{ayah_num}/tr.diyanet", timeout=6)
        if res_tr.status_code == 200:
            turkish_meal = res_tr.json().get("data", {}).get("text", "")
    except Exception as e:
        print(f"Ayet API hatası ({surah_num}:{ayah_num}): {e}")
    return arabic_text, turkish_meal

def is_arabic(text):
    return len(re.findall(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]', text)) > 5

def extract_pdf_content(pdf_url):
    if not pdf_url:
        return None
    try:
        res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        res.raise_for_status()
        reader = PdfReader(io.BytesIO(res.content))
        full_text = "\n".join([page.extract_text() or "" for page in reader.pages])
        lines = [l.strip() for l in full_text.splitlines() if l.strip()]

        footnotes = {}
        content_lines = []
        arabic_lines = []
        fn_pattern = re.compile(r'^\[?([ivxlcdm0-9]+)\]?[\.\s]+(.+)', re.IGNORECASE)

        for line in lines:
            fn_match = fn_pattern.match(line)
            if fn_match and ("suresi" in line.lower() or "/" in line or any(h in line.lower() for h in ["buhârî", "buhari", "müslim", "nesâî", "tirmizî"])):
                footnotes[fn_match.group(1).lower()] = fn_match.group(2).strip()
            elif "Din Hizmetleri Genel Müdürlüğü" not in line and not line.startswith("Tarih:"):
                if is_arabic(line) or "﷽" in line:
                    arabic_lines.append(line)
                else:
                    content_lines.append(line)

        verse_arabic, verse_meal, verse_source = "", "", ""
        hadith_arabic, hadith_source, verse_fn_key = "", "", None

        # 1. Ayet ve Meal
        for fn_id, fn_text in footnotes.items():
            match = re.search(r'([A-Za-zÇĞİÖŞÜçğıöşü\-\'\s]+),\s*(\d+)\s*/\s*(\d+)', fn_text)
            if match:
                sura_name = match.group(1).strip().lower()
                sura_num = SURA_MAP.get(sura_name, int(match.group(2)))
                ayah_num = int(match.group(3))
                verse_source = fn_text
                verse_fn_key = fn_id
                verse_arabic, verse_meal = fetch_ayah_details(sura_num, ayah_num)
                break

        # 2. Hadis (PDF'in başındaki 3. ve 4. Arapça satırlar)
        if len(arabic_lines) >= 3:
            hadith_arabic = "\n".join(arabic_lines[2:])

        for fn_id, fn_text in footnotes.items():
            if fn_id != verse_fn_key and any(k in fn_text.lower() for k in ["nesâî", "buhârî", "buhari", "müslim", "tirmizî", "ebû dâvûd"]):
                hadith_source = fn_text
                break

        # Paragrafları derle
        paragraphs, current_para = [], []
        for line in content_lines:
            if any(line.startswith(k) for k in ["Muhterem Müslümanlar", "Aziz Müminler", "Kıymetli Kardeşlerim", "Değerli Müslümanlar", "Aziz Müslümanlar"]):
                if current_para:
                    paragraphs.append(" ".join(current_para))
                    current_para = []
                paragraphs.append(line)
            else:
                current_para.append(line)

        if current_para:
            paragraphs.append(" ".join(current_para))

        body_text = "\n\n".join(paragraphs)

        summary = ""
        for p in paragraphs:
            if not any(p.startswith(k) for k in ["Muhterem Müslümanlar", "Aziz Müminler", "Kıymetli Kardeşlerim", "VATAN SEVGİSİ"]):
                summary = p
                break
        if not summary and paragraphs:
            summary = paragraphs[0]
        if len(summary) > 220:
            summary = summary[:220] + "..."

        return {
            "summary": summary,
            "verse": {
                "arabic": verse_arabic,
                "translation": verse_meal,
                "source": verse_source
            },
            "hadith": {
                "arabic": hadith_arabic,
                "source": hadith_source
            },
            "body": body_text,
            "footnotes": footnotes
        }
    except Exception as e:
        print(f"PDF işlenemedi ({pdf_url}): {e}")
        return None

async def main():
    json_path = "hutbeler.json"
    print("Playwright ile Diyanet sitesi taranıyor...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36")
        page = await context.new_page()

        await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_selector("table", timeout=15000)
        rows = await page.query_selector_all("tr.ms-itmhover, tr")

        hutbeler = []
        for idx, row in enumerate(rows):
            cols = await row.query_selector_all("td")
            if len(cols) < 5:
                continue

            raw_date = (await cols[1].inner_text()).strip()
            title = (await cols[2].inner_text()).strip()
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

            print(f"İşleniyor: {title}")
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

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Tamamlandı: {len(hutbeler)} adet hutbe kaydedildi.")

if __name__ == "__main__":
    asyncio.run(main())
