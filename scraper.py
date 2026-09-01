import io
import json
import os
import re
import subprocess
import urllib.parse
from datetime import datetime
import docx
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://dinhizmetleri.diyanet.gov.tr"
TARGET_URL = f"{BASE_URL}/kategoriler/yayinlarimiz/hutbeler/t%C3%BCrk%C3%A7e"

# Test edilip çalışan sade başlıklar
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

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
    except Exception as e:
        print(f"Arapça ayet API hatası ({surah_num}:{ayah_num}): {e}")
    return ""

def extract_text_from_doc_bytes(file_bytes, is_docx=False):
    if is_docx:
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception:
            pass

    try:
        process = subprocess.Popen(['antiword', '-m', 'UTF-8.txt', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, _ = process.communicate(input=file_bytes)
        decoded = out.decode('utf-8', errors='ignore')
        if decoded.strip():
            return decoded
    except Exception:
        pass

    try:
        process = subprocess.Popen(['antiword', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, _ = process.communicate(input=file_bytes)
        return out.decode('utf-8', errors='ignore')
    except Exception:
        return ""

def parse_hutbe_content(full_text):
    if not full_text:
        return None

    full_text = re.sub(r'\[pic\]', '', full_text, flags=re.IGNORECASE)
    lines = [l.strip() for l in full_text.splitlines()]
    
    footnotes = {}
    content_lines = []
    fn_pattern = re.compile(r'^\[([ivxlcdm0-9]+)\]\s*(.+)', re.IGNORECASE)

    for line in lines:
        line_clean = re.sub(r'[ \t\u00A0\u3000]+', ' ', line).strip()
        if not line_clean or set(line_clean) <= {'-', '_', '='}:
            continue
        
        fn_match = fn_pattern.match(line_clean)
        if fn_match:
            footnotes[fn_match.group(1).lower()] = fn_match.group(2).strip()
        elif "Din Hizmetleri Genel Müdürlüğü" not in line_clean:
            content_lines.append(line_clean)

    body_paragraphs = []
    current_para = []

    for line in content_lines:
        is_hitap = any(line.startswith(k) for k in [
            "Muhterem Müslümanlar", "Aziz Müminler", "Kıymetli Kardeşlerim", 
            "Değerli Müslümanlar", "Kıymetli Müminler", "Aziz Müslümanlar"
        ])
        if is_hitap:
            if current_para:
                body_paragraphs.append(" ".join(current_para))
                current_para = []
            current_para.append(line)
        else:
            current_para.append(line)

    if current_para:
        body_paragraphs.append(" ".join(current_para))

    body_text = "\n\n".join(body_paragraphs)

    verse_arabic = ""
    verse_source = ""
    hadith_source = ""
    verse_fn_ref = None

    for fn_id, fn_text in footnotes.items():
        match = re.search(r'([A-Za-zÇĞİÖŞÜçğıöşü\-\'\s]+),\s*(\d+)\s*/\s*(\d+)', fn_text)
        if match:
            sura_name = match.group(1).strip().lower()
            sura_num = int(match.group(2))
            ayah_num = int(match.group(3))
            
            if sura_name in SURA_MAP:
                sura_num = SURA_MAP[sura_name]
            
            verse_source = fn_text
            verse_fn_ref = fn_id
            print(f"Arapça ayet çekiliyor: Sure {sura_num}, Ayet {ayah_num}")
            verse_arabic = fetch_arabic_ayah(sura_num, ayah_num)
            break

    for fn_id, fn_text in footnotes.items():
        if fn_id != verse_fn_ref:
            if any(k in fn_text.lower() for k in ["buhârî", "buhari", "müslim", "tirmizî", "tirmizi", "nesâî", "nesai", "ebû dâvûd", "ibn mâce"]):
                hadith_source = fn_text
                break

    summary = body_paragraphs[0] if body_paragraphs else ""
    if len(summary) > 250:
        summary = summary[:250] + "..."

    return {
        "summary": summary,
        "verse": {
            "arabic": verse_arabic,
            "translation": "",
            "source": verse_source
        },
        "hadith": {
            "text": "",
            "source": hadith_source
        },
        "body": body_text,
        "footnotes": footnotes
    }

def fetch_hutbe_doc_content(doc_url):
    if not doc_url:
        return None
    try:
        res = requests.get(doc_url, headers=HEADERS, timeout=20)
        res.raise_for_status()
        is_docx = doc_url.lower().endswith(".docx")
        text = extract_text_from_doc_bytes(res.content, is_docx=is_docx)
        return parse_hutbe_content(text)
    except Exception as e:
        print(f"Word indirilemedi ({doc_url}): {e}")
        return None

def main():
    print("Diyanet Türkçe hutbeleri taranıyor...")
    response = requests.get(TARGET_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Kırılmaz Seçici: İçinde .pdf veya .doc linki olan tüm satırları bul
    rows = []
    seen_rows = set()
    
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].lower()
        if ".pdf" in href or ".doc" in href:
            tr_parent = a_tag.find_parent("tr")
            if tr_parent and tr_parent not in seen_rows:
                seen_rows.add(tr_parent)
                rows.append(tr_parent)

    print(f"Bulunan geçerli hutbe satırı: {len(rows)}")
    if not rows:
        print("Hata: Sayfada hutbe satırı bulunamadı!")
        return

    hutbeler = []

    for idx, row in enumerate(rows):
        cols = row.find_all("td")
        if len(cols) < 5:
            continue

        # Tarih ve Başlık kolonlarını güvenli al
        raw_date = cols[1].get_text(strip=True)
        title = cols[2].get_text(strip=True)

        pdf_link = None
        doc_link = None
        ses_link = None

        for a in row.find_all("a", href=True):
            h = a["href"].lower()
            if ".pdf" in h and not pdf_link:
                pdf_link = clean_url(a["href"])
            elif (".doc" in h or ".docx" in h) and not doc_link:
                doc_link = clean_url(a["href"])
            elif ".mp3" in h and not ses_link:
                ses_link = clean_url(a["href"])

        formatted_date, display_date = parse_date(raw_date)
        hutbe_id = f"hutbe_{formatted_date.replace('-', '')}_{idx + 1}"

        content_data = None
        # İlk 10 güncel hutbenin Word dosyasını çekip ayrıştır
        if idx < 10 and doc_link:
            print(f"[{idx+1}/10] İçerik işleniyor: {title}")
            content_data = fetch_hutbe_doc_content(doc_link)

        hutbeler.append({
            "id": hutbe_id,
            "title": title,
            "date": formatted_date,
            "raw_date": display_date,
            "language": "tr",
            "pdf_url": pdf_link,
            "doc_url": doc_link,
            "audio_url": ses_link,
            "content": content_data
        })

    payload = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "total_count": len(hutbeler),
        "data": hutbeler
    }

    with open("hutbeler.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Tamamlandı! Toplam {len(hutbeler)} hutbe 'hutbeler.json' dosyasına kaydedildi.")

if __name__ == "__main__":
    main()
