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
    "fatiha": 1, "fâtiha": 1, "bakara": 2, "al-i imran": 3, "âl-i imrân": 3, "al-i imrân": 3, "ali imran": 3,
    "nisa": 4, "nisâ": 4, "maide": 5, "mâide": 5, "enam": 6, "en'am": 6, "en'âm": 6, "araf": 7, "a'raf": 7, "a'râf": 7,
    "enfal": 8, "enfâl": 8, "tevbe": 9, "yunus": 10, "yûnus": 10, "hud": 11, "hûd": 11, "yusuf": 12, "yûsuf": 12,
    "rad": 13, "ra'd": 13, "ibrahim": 14, "ibrâhîm": 14, "hicr": 15, "nahl": 16, "isra": 17, "isrâ": 17, "kehf": 18,
    "meryem": 19, "taha": 20, "tâhâ": 20, "enbiya": 21, "enbiyâ": 21, "hac": 22, "muminun": 23, "mü'minûn": 23,
    "nur": 24, "nûr": 24, "furkan": 25, "furkân": 25, "suara": 26, "şuarâ": 26, "neml": 27, "kasas": 28,
    "ankebut": 29, "ankebût": 29, "rum": 30, "rûm": 30, "lokman": 31, "secde": 32, "ahzab": 33, "ahzâb": 33,
    "sebe": 34, "sebe'": 34, "fatir": 35, "fâtır": 35, "yasin": 36, "yâsîn": 36, "saffat": 37, "sâffât": 37,
    "sad": 38, "sâd": 38, "zumer": 39, "zümer": 39, "mumin": 40, "mü'min": 40, "fussilet": 41, "sura": 42, "şûrâ": 42,
    "zuhruf": 43, "duhan": 44, "duhân": 44, "casiye": 45, "câsiye": 45, "ahkaf": 46, "ahkâf": 46, "muhammed": 47,
    "fetih": 48, "hucurat": 49, "hucurât": 49, "kaf": 50, "kâf": 50, "zariyat": 51, "zâriyât": 51, "tur": 52, "tûr": 52,
    "necm": 53, "kamer": 54, "rahman": 55, "rahmân": 55, "vakia": 56, "vâkıa": 56, "hadid": 57, "hadîd": 57,
    "mucadele": 58, "mücâdele": 58, "hasr": 59, "haşr": 59, "mumtehine": 60, "mümtehine": 60, "saf": 61, "saff": 61,
    "cuma": 62, "munafikun": 63, "münâfikûn": 63, "tegabun": 64, "teğâbün": 64, "talak": 65, "talâk": 65, "tahrim": 66, "tahrîm": 66,
    "mulk": 67, "mülk": 67, "kalem": 68, "hakka": 69, "hâkka": 69, "mearic": 70, "meâric": 70, "nuh": 71, "nûh": 71,
    "cin": 72, "muzzemmil": 73, "müzzemmil": 73, "muddessir": 74, "müddessir": 74, "kiyame": 75, "kıyâme": 75,
    "insan": 76, "insân": 76, "murselat": 77, "mürselât": 77, "nebe": 78, "nebe'": 78, "naziat": 79, "nâziât": 79,
    "abese": 80, "tekvir": 81, "infitar": 82, "infitâr": 82, "mutaffifin": 83, "mutaffifîn": 83, "insikak": 84, "inşikâk": 84,
    "buruc": 85, "bürûc": 85, "tarik": 86, "târık": 86, "ala": 87, "a'lâ": 87, "gasiye": 88, "gâşiye": 88, "fecr": 89,
    "beled": 90, "sems": 91, "şems": 91, "leyl": 92, "duha": 93, "duhâ": 93, "insirah": 94, "inşirâh": 94, "tin": 95, "tîn": 95,
    "alak": 96, "kadir": 97, "kadr": 97, "beyyine": 98, "zilzal": 99, "zilzâl": 99, "adiyat": 100, "âdiyât": 100,
    "karia": 101, "kâria": 101, "tekasur": 102, "tekâsür": 102, "asr": 103, "humeze": 104, "hümeze": 104, "fil": 105, "fîl": 105,
    "kureys": 106, "kureyş": 106, "maun": 107, "mâûn": 107, "kevser": 108, "kafirun": 109, "kâfirûn": 109, "nasr": 110,
    "tebbet": 111, "ihlas": 112, "ihlâs": 112, "felak": 113, "nas": 114, "nâs": 114
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
        res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=20)
        res.raise_for_status()
        reader = PdfReader(io.BytesIO(res.content))
        full_text = "\n".join([page.extract_text() or "" for page in reader.pages])

        lines = [l.strip() for l in full_text.splitlines() if l.strip()]
        
        footnotes = {}
        content_lines = []
        fn_pattern = re.compile(r'^\[([ivxlcdm0-9]+)\]\s*(.+)', re.IGNORECASE)

        for line in lines:
            fn_match = fn_pattern.match(line)
            if fn_match:
                footnotes[fn_match.group(1).lower()] = fn_match.group(2).strip()
            elif "Din Hizmetleri Genel Müdürlüğü" not in line and not line.startswith("Tarih:"):
                content_lines.append(line)

        verse_arabic = ""
        verse_source = ""
        hadith_source = ""

        # Dipnotlardan ayet referansını tespit et
        for fn_id, fn_text in footnotes.items():
            match = re.search(r'([A-Za-zÇĞİÖŞÜçğıöşü\-\'\s]+),\s*(\d+)\s*/\s*(\d+)', fn_text)
            if match:
                sura_name = match.group(1).strip().lower()
                sura_num = SURA_MAP.get(sura_name, int(match.group(2)))
                ayah_num = int(match.group(3))
                verse_source = fn_text
                verse_arabic = fetch_arabic_ayah(sura_num, ayah_num)
                break

        # Hadis kaynağını tespit et
        for fn_id, fn_text in footnotes.items():
            if any(k in fn_text.lower() for k in ["buhârî", "buhari", "müslim", "tirmizî", "nesâî", "ebû dâvûd", "ibn mâce"]):
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
    json_path = "hutbeler.json"
    existing_contents = {}

    # Mevcut JSON varsa daha önce doldurulmuş içerikleri hafızaya al
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for item in saved.get("data", []):
                    if item.get("content"):
                        existing_contents[item["id"]] = item["content"]
            print(f"Mevcut önbellekten {len(existing_contents)} adet işlenmiş hutbe içeriği korundu.")
        except Exception:
            existing_contents = {}

    print("Playwright ile Diyanet sitesi açılıyor...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_selector("table", timeout=15000)

        rows = await page.query_selector_all("tr.ms-itmhover, tr")
        print(f"DOM üzerinden bulunan satır sayısı: {len(rows)}")

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

            # Önbellekte varsa tekrar PDF indirme, yoksa PDF'i indir ve metni ayıkla
            if hutbe_id in existing_contents and existing_contents[hutbe_id]:
                content_data = existing_contents[hutbe_id]
            elif pdf_url:
                print(f"[{idx+1}/{len(rows)}] Yeni PDF taranıyor: {title}")
                content_data = extract_pdf_content(pdf_url)
            else:
                content_data = None

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

    print(f"Tamamlandı! Toplam {len(hutbeler)} adet hutbenin tamamı 'hutbeler.json' dosyasına işlendi.")

if __name__ == "__main__":
    asyncio.run(main())
