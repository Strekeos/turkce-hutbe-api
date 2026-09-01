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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9",
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

def extract_text_from_doc_bytes(file_bytes, is_docx=False):
    """DOC veya DOCX dosya baytlarından düz metin ayıklar"""
    if is_docx:
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception:
            pass

    # Eski tip .doc formatı için antiword aracı
    try:
        process = subprocess.Popen(['antiword', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, _ = process.communicate(input=file_bytes)
        return out.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Word okuma hatası: {e}")
        return ""

def parse_hutbe_content(full_text):
    """Hutbe metnini ayet, hadis, özet ve gövde olarak parçalar"""
    if not full_text:
        return None

    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
    raw_content = "\n".join(lines)

    # Basit blok çıkarma mantığı
    verse_arabic = ""
    verse_translation = ""
    verse_source = ""
    hadith_text = ""
    hadith_source = ""

    # Arapça harf içeren blokları yakala
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+')
    arabic_blocks = [line for line in lines if len(arabic_pattern.findall(line)) > 3]
    if arabic_blocks:
        verse_arabic = arabic_blocks[0]

    # "Muhterem Müslümanlar" veya "Aziz Müminler" öncesi özet/giriştir
    body_start_idx = 0
    for idx, line in enumerate(lines):
        if any(keyword in line for keyword in ["Muhterem Müslümanlar", "Aziz Müminler", "Değerli Kardeşlerim", "Aziz Müslümanlar"]):
            body_start_idx = idx
            break

    summary = " ".join(lines[1:min(body_start_idx, 4)]) if body_start_idx > 1 else (lines[1] if len(lines) > 1 else "")
    body_text = "\n\n".join(lines[body_start_idx:]) if body_start_idx > 0 else raw_content

    return {
        "summary": summary.strip(),
        "verse": {
            "arabic": verse_arabic.strip(),
            "translation": "",
            "source": ""
        },
        "hadith": {
            "text": hadith_text.strip(),
            "source": hadith_source.strip()
        },
        "body": body_text.strip(),
        "raw_text": raw_content
    }

def fetch_hutbe_doc_content(doc_url):
    """Word dosyasını indirip metnini çeker"""
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
    print("Diyanet Türkçe hutbeleri ve Word içerikleri taranıyor...")
    response = requests.get(TARGET_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", {"id": "onetidDoclibViewTbl0"})
    if not table:
        print("Hata: Tablo bulunamadı!")
        return

    json_path = "hutbeler.json"
    existing_data = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for item in saved.get("data", []):
                    existing_data[item["id"]] = item
        except Exception:
            existing_data = {}

    rows = table.find_all("tr", class_=lambda x: x and "ms-itmhover" in x)
    updated_items = []

    # İlk 5 hutbenin (en güncellerin) detaylı Word metinlerini çek
    for idx, row in enumerate(rows):
        cols = row.find_all("td")
        if len(cols) < 6:
            continue

        raw_date = cols[1].get_text(strip=True)
        title = cols[2].get_text(strip=True)
        pdf_tag = cols[3].find("a")
        doc_tag = cols[4].find("a")
        ses_tag = cols[5].find("a")

        formatted_date, display_date = parse_date(raw_date)
        hutbe_id = f"hutbe_{formatted_date.replace('-', '')}_{idx + 1}"
        doc_url = clean_url(doc_tag["href"]) if doc_tag and doc_tag.has_attr("href") else None

        # Eğer veri zaten varsa ve içeriği çekilmişse tekrar indirme (hız tasarrufu)
        content_data = None
        if hutbe_id in existing_data and existing_data[hutbe_id].get("content"):
            content_data = existing_data[hutbe_id]["content"]
        elif idx < 5 and doc_url:
            print(f"Metin indiriliyor: {title}")
            content_data = fetch_hutbe_doc_content(doc_url)

        item = {
            "id": hutbe_id,
            "title": title,
            "date": formatted_date,
            "raw_date": display_date,
            "language": "tr",
            "pdf_url": clean_url(pdf_tag["href"]) if pdf_tag and pdf_tag.has_attr("href") else None,
            "doc_url": doc_url,
            "audio_url": clean_url(ses_tag["href"]) if ses_tag and ses_tag.has_attr("href") else None,
            "content": content_data
        }
        updated_items.append(item)
        existing_data[hutbe_id] = item

    final_list = list(existing_data.values())
    final_list.sort(key=lambda x: x.get("date", ""), reverse=True)

    payload = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "total_count": len(final_list),
        "data": final_list
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Başarılı! Toplam {len(final_list)} adet hutbe güncellendi.")

if __name__ == "__main__":
    main()
