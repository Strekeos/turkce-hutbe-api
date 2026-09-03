def extract_pdf_content(pdf_url):
  if not pdf_url:
    return None
  try:
    res = requests.get(
        pdf_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        timeout=20,
    )
    res.raise_for_status()
    reader = PdfReader(io.BytesIO(res.content))
    full_text = "\n".join([page.extract_text() or "" for page in reader.pages])

    lines = [l.strip() for l in full_text.splitlines() if l.strip()]

    footnotes = {}
    content_lines = []
    arabic_header_lines = []

    fn_pattern = re.compile(r"^\[?([ivxlcdm0-9]+)\]?[\.\s]+(.+)", re.IGNORECASE)

    for line in lines:
      fn_match = fn_pattern.match(line)
      # Dipnotları ayıkla
      if fn_match and (
          "suresi" in line.lower()
          or "/" in line
          or any(
              h in line.lower()
              for h in ["buhârî", "buhari", "müslim", "nesâî", "tirmizî"]
          )
      ):
        footnotes[fn_match.group(1).lower()] = fn_match.group(2).strip()
      elif (
          "Din Hizmetleri Genel Müdürlüğü" not in line
          and not line.startswith("Tarih:")
      ):
        # Baş kısımdaki Arapça 4 satırı yakala
        if is_arabic_text(line) or any(k in line for k in ["﷽"]):
          arabic_header_lines.append(line)
        else:
          content_lines.append(line)

    verse_arabic = ""
    verse_source = ""
    hadith_source = ""
    hadith_arabic = ""

    # 1. Âyet: Mushaf API üzerinden hatasız çek
    for fn_id, fn_text in footnotes.items():
      match = re.search(
          r"([A-Za-zÇĞİÖŞÜçğıöşü\-\'\s]+),\s*(\d+)\s*/\s*(\d+)", fn_text
      )
      if match:
        sura_name = match.group(1).strip().lower()
        sura_num = SURA_MAP.get(sura_name, int(match.group(2)))
        ayah_num = int(match.group(3))
        verse_source = fn_text
        verse_arabic = fetch_arabic_ayah(sura_num, ayah_num)
        break

    # 2. Hadis: PDF'teki 3. ve 4. satırları Hadis bloğu olarak al
    # (arabic_header_lines[2:] -> "وَقَالَ رَسُولُ اللّٰهِ..." ve "جَاهِدُوا...")
    if len(arabic_header_lines) >= 3:
      hadith_arabic = "\n".join(arabic_header_lines[2:])

    for fn_id, fn_text in footnotes.items():
      if any(
          k in fn_text.lower()
          for k in ["nesâî", "buhârî", "buhari", "müslim", "tirmizî", "ebû dâvûd"]
      ):
        hadith_source = fn_text
        break

    body_text = "\n\n".join(content_lines)
    summary = content_lines[0] if content_lines else ""
    if len(summary) > 220:
      summary = summary[:220] + "..."

    return {
        "summary": summary,
        "verse": {"arabic": verse_arabic, "source": verse_source},
        "hadith": {
            "arabic": hadith_arabic,  # Hadisin Arapça metni buraya eklendi
            "source": hadith_source,
        },
        "body": body_text,
        "footnotes": footnotes,
    }
  except Exception as e:
    print(f"PDF işlenemedi ({pdf_url}): {e}")
    return None
