import os
import time
import logging
from datetime import datetime, timedelta

from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import requests
import google.generativeai as genai

# --- API Anahtarları Doğrudan Kodda ---
YOUTUBE_API_KEY = "AIzaSyDTLmEa9Gqa_mgekVps4WuEHRRli4riXXY"
GEMINI_API_KEY = "AIzaSyD4FvPjl6uIF9js3UBbb-TQUpKXpvnk2c8"
TELEGRAM_BOT_TOKEN = "8452545680:AAEVuFuaxcg-A7oCfAy5B_jDhE4aLCK5M5M"
TELEGRAM_CHAT_ID = "-1003129826607"
# --------------------------------------

MAX_VIDEOS = 100
MAX_VIDEOS_PER_CHANNEL = 10

logging.basicConfig(level=logging.INFO)

GEMINI_PROMPT = """
## 🎯 Ana Hedef
Bir YouTube videosunun transkriptini, konuya hakim ancak uzman olmayan bir hedef kitle için, videodaki **uzman seviyesindeki temel bilgileri ve fark yaratan içgörüleri** öne çıkaran, damıtılmış ve yapılandırılmış bir metne dönüştür.

## ⚠️ Temel Prensip: Sinyali Güçlendir, Gürültüyü Temizle
Bu bir özetleme değil, **damıtma** görevidir. Amaç, konuşmadaki "gürültüyü" (dolgu kelimeleri, tekrarlar, giriş/kapanış sohbetleri) temizleyerek "sinyali" (ana fikirler, kritik detaylar, uzman tavsiyeleri, stratejiler) güçlendirmektir. Sıradan ve genel geçer bilgiler yerine, konunun kilit noktalarını ve pratik değer taşıyan bilgileri korumaya odaklan.

## 📐 Uygulama Kuralları
1. **Formatlama:** Çıktıyı tamamen **Markdown** kullanarak yapılandır.
   - Ana konu başlıkları için `##` kullan.
   - Alt başlıklar veya listeler için madde imi (`-`, `*`) kullan.
   - Önemli kavramları, araç isimlerini, teknik terimleri ve özel isimleri `**kalın**` yazarak vurgula.

2. **İçerik Temizliği:**
   - **Giriş/Kapanış:** "Merhaba", "kanalıma hoş geldiniz", "videoyu beğenmeyi unutmayın" gibi standart YouTube ifadelerini tamamen kaldır.
   - **Dolgu Kelimeleri:** `yani`, `işte`, `şey`, `gibi`, `falan`, `aslında` gibi anlamsal değeri olmayan kelimeleri çıkar.
   - **Anlamsal Tekrarlar:** Aynı fikri farklı kelimelerle ifade eden cümleleri birleştirerek en net ve tek bir ifadeye dönüştür.

3. **Cümle Yapısı ve Ton:**
   - Cümleleri aktif ve net bir dilde yeniden kur.
   - **Öncelik: Okunabilirlik.** Metnin net, profesyonel ve bilgilendirici bir tona sahip olmasını sağla. Konuşmacının orijinal samimi tonunu korumak yerine, metnin akıcılığını ve anlaşılırlığını önceliklendir.
   - **Hedef:** Cümleleri ortalama 15-20 kelime uzunluğunda tutarak okunabilirliği artır. Ancak, bir fikrin bütünlüğünü korumak için bu kuralı esnetebilirsin. Anlamı bozacak şekilde cümleleri bölme.

4. **Özel İsimlerin Korunması:**
   - Bahsedilen tüm **araç, yazılım, teknoloji, YouTube kanalı** ve **kişi** isimlerini koru ve `**` ile vurgula.

5. **Örneklerin ve Hikayelerin İşlenmesi:**
   - Uzun kişisel hikayelerden veya örneklerden sadece bahsederek geçme. Bunun yerine, hikayenin ana dersini veya **Problem -> Eylem -> Sonuç** yapısını 1-2 cümleyle özetle.
   - *Örnek:* "Geçen hafta bir projede Notion kullanırken yaşadığım bir sorunu anlatayım..." yerine, `- **Notion**'da filtre ayarlarının yanlış yapılmasının görev takibini engellediği bir vaka paylaştı ve çözüm olarak filtrelerin yeniden yapılandırılması gerektiğini gösterdi.` şeklinde, öğrenimi içeren bir ifade kullan.

6. **Mantıksal Akış:**
   - Konuşmanın orijinal **mantıksal sırasını** koru. Fikirleri konularına göre yeniden gruplama, konuşmacının anlattığı sırayı takip et.

7. **Teknik ve Görsel Unsurlar:**
   - Endüstri standardı teknik terimleri (`API`, `Git`, `React`) olduğu gibi koru.
   - Konuşmacının videodaki görsellere, grafiklere veya seslere yaptığı referansları (`ekranda gördüğünüz gibi...`, `şimdi bu sese kulak verin...`) tamamen metinden çıkar.

8. **Birden Fazla Konuşmacı:**
   - Eğer transkriptte birden fazla konuşmacı varsa, her birini `**Konuşmacı Adı:**` formatında belirterek konuşmalarını ayır.

Transkript:
"""

def load_channels(filename="channels.txt"):
    channels = []
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                channels.append(line)
    return channels

def fetch_recent_videos(youtube, channel_id):
    now = datetime.utcnow()
    published_after = (now - timedelta(days=1)).isoformat("T") + "Z"
    videos = []
    try:
        req = youtube.search().list(
            channelId=channel_id,
            part="id,snippet",
            order="date",
            publishedAfter=published_after,
            maxResults=MAX_VIDEOS_PER_CHANNEL,
            type="video"
        )
        res = req.execute()
        for item in res.get("items", []):
            videos.append({
                "videoId": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "channelTitle": item["snippet"]["channelTitle"],
                "publishedAt": item["snippet"]["publishedAt"],
            })
    except Exception as e:
        logging.warning(f"Kanal taranamadı: {channel_id} - {e}")
    return videos

def get_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["tr"])
        return " ".join([seg["text"] for seg in transcript])
    except (TranscriptsDisabled, NoTranscriptFound):
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
            return " ".join([seg["text"] for seg in transcript])
        except (TranscriptsDisabled, NoTranscriptFound):
            try:
                transcript_obj = YouTubeTranscriptApi.list_transcripts(video_id)
                transcript = transcript_obj.find_generated_transcript(['tr', 'en'])
                return " ".join([seg["text"] for seg in transcript.fetch()])
            except Exception:
                return None
    except Exception as e:
        logging.warning(f"Transkript hatası: {video_id} - {e}")
    return None

def summarize_with_gemini(transcript):
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(GEMINI_PROMPT + transcript)
        return response.text
    except Exception as e:
        logging.warning(f"Gemini özetleme hatası: {e}")
        return None

def send_telegram_message(text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode
    }
    r = requests.post(url, json=payload)
    if r.status_code != 200:
        logging.warning(f"Telegram mesajı gönderilemedi: {r.text}")

def split_message(msg, max_len=4000):
    return [msg[i:i+max_len] for i in range(0, len(msg), max_len)]

def main():
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    channels = load_channels()
    all_videos, processed, failed = [], 0, 0
    for channel_id in channels:
        videos = fetch_recent_videos(youtube, channel_id)
        all_videos.extend(videos)
        if len(all_videos) >= MAX_VIDEOS:
            break
    all_videos = all_videos[:MAX_VIDEOS]
    for v in all_videos:
        transcript = get_transcript(v["videoId"])
        if not transcript:
            failed += 1
            continue
        summary = summarize_with_gemini(transcript)
        if not summary:
            failed += 1
            continue
        msg = f"""🎬 **{v['title']}**

📺 Kanal: {v['channelTitle']}
🔗 Link: https://www.youtube.com/watch?v={v['videoId']}

---

{summary}

---
⏱️ İşlenme: {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
        # Telegram mesajı uzun ise böl
        if len(msg) > 4000:
            for part in split_message(msg):
                send_telegram_message(part)
                time.sleep(2)
        else:
            send_telegram_message(msg)
            time.sleep(2)
        processed += 1

    # Günlük rapor
    report = f"""📊 **GÜNLÜK ÖZET RAPORU**

✅ Toplam işlenen video: {processed}
❌ Başarısız: {failed}
📹 Taranan toplam video: {len(all_videos)}
📺 Taranan kanal sayısı: {len(channels)}

⏱️ {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
    send_telegram_message(report)

if __name__ == "__main__":
    main()
