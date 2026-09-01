import json
import os
import re
import urllib.parse
from datetime import datetime
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://dinhizmetleri.diyanet.gov.tr"
SHAREPOINT_RPC_URL = f"{BASE_URL}/_vti_bin/owssvr.dll?CS=65001&XMLDATA=1&RowLimit=0&View=%7B3371EE93-ABFB-4357-8754-14A7F3175DA5%7D"
FALLBACK_PAGE_URL = f"{BASE_URL}/kategoriler/yayinlarimiz/hutbeler/t%C3%BCrk%C3%A7e"

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
        # 2026-08-28T00:00:00Z veya 28.08.2026
        if "-" in date_str and "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d"), dt.strftime("%d.%m.%Y")
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d"), date_str.strip()
    except Exception:
        return date_str.strip(), date_str.strip()

def fetch_via_sharepoint_xml():
    """SharePoint'in tüm arşivi tek XML içinde döndüren servisi"""
    print("SharePoint XML veri servisi deneniyor (Tüm Arşiv)...")
    try:
        response = requests.get(SHAREPOINT_RPC_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        # XML Namespace temizleme veya doğrudan z:row yakalama
        xml_text = response.text
        root = ET.fromstring(xml_text)
        
        rows = root.findall(".//{http://schemas.microsoft.com/sharepoint/dsp}row") or \
               root.findall(".//{urn:schemas-microsoft-com:rowset}data/{urn:schemas-microsoft-com:rowset}row") or \
               root.findall(".//*[@ows_Title]")

        if not rows:
            # Düz regex ile z:row arama (SharePoint özel formatı)
            items = []
            for m in re.finditer(r'<z:row\s+([^>]+)/>', xml_text):
                attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
                items.append(attrs)
            if items:
                return parse_xml_rows(items)
        else:
            return parse_xml_element_rows(rows)
    except Exception as e:
        print(f"XML servisi okunamadı ({e}), standart HTML yöntemine geçiliyor...")
    return None

def parse_xml_rows(items):
    results = []
    for item in items:
        title = item.get("ows_Title") or item.get("ows_LinkFilename", "")
        raw_date = item.get("ows_Tarih") or item.get("ows_Created", "")
        file_ref = item.get("ows_FileRef", "")
        
        if not title:
            continue
            
        formatted_date, display_date = parse_date(raw_date)
        
        # Link ayıklama
        pdf = item.get("ows_PDF") or ""
        doc = item.get("ows_Word") or ""
        ses = item.get("ows_Ses") or ""

        pdf_url = pdf.split(",#")[0] if ",#" in pdf else pdf
        doc_url = doc.split(",#")[0] if ",#" in doc else doc
        ses_url = ses.split(",#")[0] if ",#" in ses else ses

        if not pdf_url and file_ref.endswith(".pdf"):
            pdf_url = file_ref

        results.append({
            "id": f"hutbe_{formatted_date.replace('-', '')}_{title[:15].strip()}",
            "title": title.replace(",.", "").strip(),
            "date": formatted_date,
            "raw_date": display_date,
            "language": "tr",
            "pdf_url": clean_url(pdf_url) if pdf_url else None,
            "doc_url": clean_url(doc_url) if doc_url else None,
            "audio_url": clean_url(ses_url) if ses_url else None
        })
    return results

def parse_xml_element_rows(elements):
    items = [el.attrib for el in elements]
    return parse_xml_rows(items)

def fetch_via_html_page():
    """Son 30 kaydı HTML tablosundan çeken yedek mekanizma"""
    print("HTML sayfası üzerinden güncel liste taranıyor...")
    response = requests.get(FALLBACK_PAGE_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", {"id": "onetidDoclibViewTbl0"})
    if not table:
        return []

    results = []
    rows = table.find_all("tr", class_=lambda x: x and "ms-itmhover" in x)
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 6:
            continue

        raw_date = cols[1].get_text(strip=True)
        title = cols[2].get_text(strip=True)
        pdf_tag = cols[3].find("a")
        doc_tag = cols[4].find("a")
        ses_tag = cols[5].find("a")

        formatted_date, display_date = parse_date(raw_date)

        results.append({
            "id": f"hutbe_{formatted_date.replace('-', '')}_{title[:15].strip()}",
            "title": title,
            "date": formatted_date,
            "raw_date": display_date,
            "language": "tr",
            "pdf_url": clean_url(pdf_tag["href"]) if pdf_tag and pdf_tag.has_attr("href") else None,
            "doc_url": clean_url(doc_tag["href"]) if doc_tag and doc_tag.has_attr("href") else None,
            "audio_url": clean_url(ses_tag["href"]) if ses_tag and ses_tag.has_attr("href") else None
        })
    return results

def main():
    json_path = "hutbeler.json"
    existing_data = []
    
    # 1. Mevcut hutbeler.json varsa oku
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                existing_data = saved.get("data", [])
                print(f"Mevcut kayıtlı hutbe sayısı: {len(existing_data)}")
        except Exception as e:
            print(f"Mevcut JSON okunamadı: {e}")

    # 2. Yeni/Tüm verileri çek
    scraped_hutbeler = fetch_via_sharepoint_xml()
    if not scraped_hutbeler:
        scraped_hutbeler = fetch_via_html_page()

    print(f"Çekilen hutbe sayısı: {len(scraped_hutbeler)}")

    # 3. Akıllı Birleştirme (Mevcut verilerle yenileri harmanla, ID'ye göre tekilleştir)
    merged_dict = {}
    
    # Önce mevcutları ekle (arşiv kaybolmasın)
    for h in existing_data:
        merged_dict[h["id"]] = h

    # Yenileri ekle / güncelle
    for h in scraped_hutbeler:
        merged_dict[h["id"]] = h

    # Tarihe göre yeniden eskiye sırala
    final_list = list(merged_dict.values())
    final_list.sort(key=lambda x: x.get("date", ""), reverse=True)

    payload = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "total_count": len(final_list),
        "data": final_list
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Tamamlandı! Toplam {len(final_list)} adet hutbe 'hutbeler.json' dosyasında hazır.")

if __name__ == "__main__":
    main()
