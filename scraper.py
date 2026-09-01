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
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://dinhizmetleri.diyanet.gov.tr"
TARGET_URL = f"{BASE_URL}/kategoriler/yayinlarimiz/hutbeler/t%C3%BCrk%C3%A7e"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://dinhizmetleri.diyanet.gov.tr/",
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

    try:
        process = subprocess.Popen(['antiword', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, _ = process.communicate(input=file_bytes)
        return out.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Antiword okuma hatası: {e}")
        return ""

def parse_hutbe_content(full_text):
    """Hutbe metnini ayet, hadis, özet ve gövde olarak parçalar"""
    if not full_text:
        return None

    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
    raw_content = "\n\n".join(lines)

    verse_arabic = ""
    verse_translation = ""
    hadith_text = ""
    body_lines = []

    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+')
    
    body_started = False
    summary_lines = []

    for idx, line in enumerate(lines):
        if any(keyword in line for keyword in ["Muhterem Müslümanlar", "Aziz Müminler", "Değerli Kardeşlerim", "Aziz Müslümanlar"]):
            body_started = True

        if body_started:
            body_lines.append(line)
        else:
            if len(arabic_pattern.findall(line)) > 2 and not verse_arabic:
                verse_arabic = line
            elif line.startswith("“") or line.startswith('"') or "Ayet" in line or "Suresi" in line:
                if not verse_translation:
                    verse_translation = line
                elif not hadith_text:
                    hadith_text = line
            else:
                summary_lines.append(line)

    summary = " ".join(summary_lines[1:]) if len(summary_lines) > 1 else (summary_lines[0] if summary_lines else "")
    body_text = "\n\n".join(body_lines) if body_lines else raw_content

    return {
        "summary": summary.strip(),
        "verse": {
            "arabic": verse_arabic.strip(),
            "translation": verse_translation.strip(),
            "source": ""
        },
        "hadith": {
            "text": hadith_text.strip(),
            "source": ""
        },
        "body": body_text.strip(),
        "raw_text": raw_content
    }

def fetch_hutbe_doc_content(session, doc_url):
    """Word dosyasını indirip içeriğini döner"""
    if not doc_url:
        return None
    try:
        res = session.get(doc_url, headers=HEADERS, timeout=20, verify=False)
        res.raise_for_status()
        is_docx = doc_url.lower().endswith(".docx")
        text = extract_text_from_doc_bytes(res.content, is_docx=is_docx)
        return parse_hutbe_content(text)
    except Exception as e:
        print(f"Word indirilemedi ({doc_url}): {e}")
        return None

def main():
    print("Diyanet Türkçe hutbeleri taranıyor...")
    session = requests.Session()
    response = session.get(TARGET_URL, headers=HEADERS, timeout=30, verify=False)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Esnek satır bulma: Doğrudan SharePoint itmhover satırlarını ara
    rows = soup.find_all("tr", class_=lambda x: x and "ms-itmhover" in x)
    
    if not rows:
        # Tablo üzerinden yedek arama
        table = soup.find("table", {"id": "onetidDoclibViewTbl0"}) or soup.find("table", class_=lambda x: x and "ms-listviewtable" in x)
        if table:
            rows = table.find_all("tr")

    if not rows:
        print("Hata: Sayfada hutbe satırı bulunamadı!")
        return

    hutbeler = []
    print(f"Toplam {len(rows)} adet satır bulundu. Word içerikleri işleniyor...")

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

        content_data = None
        # İlk 10 güncel hutbenin Word dosyasını indir
        if idx < 10 and doc_url:
            print(f"[{idx+1}/10] Metin işleniyor: {title}")
            content_data = fetch_hutbe_doc_content(session, doc_url)

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
        hutbeler.append(item)

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
