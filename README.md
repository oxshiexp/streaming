# YouTube Streaming Bot

Bot Python untuk otomatisasi live streaming YouTube menggunakan YouTube Data API v3 dengan dukungan pengujian di Vercel (serverless) dan deployment 24/7 di VPS. Bot ini memanfaatkan FastAPI untuk kontrol HTTP (start/stop/schedule), ffmpeg untuk menyiarkan konten, dan fitur pemantauan/reconnect otomatis.

## Fitur Utama
- Autentikasi OAuth 2.0 (refresh token) dan pemuatan credential via environment variables.
- Pembuatan dan pengikatan live broadcast/stream (judul, deskripsi, privasi).
- Pengaturan kualitas (resolusi/bitrate), looping konten, dan sumber fleksibel (file lokal/URL/playlist).
- Kontrol manual via HTTP API: mulai, berhenti, jadwalkan, kirim pesan chat, matikan chat.
- Pemantauan kesehatan stream, reconnect otomatis, notifikasi via webhook/email, dan log per sesi.
- Dukungan multi-stream (menyimpan banyak sesi) dan penjadwalan dengan APScheduler.
- Multi-destination: tambahkan RTMP/RTMPS endpoint lain (mis. Twitch/restream) melalui payload untuk streaming serentak.
- Endpoint dipakai bersama untuk Vercel (serverless) maupun VPS (uvicorn/gunicorn).

## Prasyarat
- Python 3.11+
- ffmpeg terpasang di lingkungan VPS.
- Kredensial OAuth 2.0 YouTube (client id, client secret, refresh token dengan scope `youtube.force-ssl` & `youtube.upload`).

## Konfigurasi Environment
Set env berikut di Vercel (Project Settings) maupun VPS:

```
YOUTUBE_OAUTH_CLIENT_ID=<client-id>
YOUTUBE_OAUTH_CLIENT_SECRET=<client-secret>
YOUTUBE_OAUTH_REFRESH_TOKEN=<refresh-token>

# Opsional
DEFAULT_PRIVACY_STATUS=unlisted
DEFAULT_RESOLUTION=1080p
DEFAULT_BITRATE=4500k

# Notifikasi
NOTIFY_WEBHOOK_URL=<https://...>        # untuk webhook Discord/Slack/ops
SMTP_HOST=<smtp.example.com>
SMTP_PORT=587
SMTP_USERNAME=<user>
SMTP_PASSWORD=<password>
NOTIFY_EMAIL_FROM=bot@example.com
NOTIFY_EMAIL_TO=admin@example.com

# Sosial (opsional)
SOCIAL_WEBHOOK_URL=<https://...>
```

## Instalasi Lokal/VPS
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn streaming_bot.web:app --host 0.0.0.0 --port 8000
```

Pastikan `ffmpeg` tersedia dan dapat diakses dari PATH. Bot akan menjalankan ffmpeg untuk mendorong RTMP ke ingestion URL YouTube.

## Endpoint HTTP (FastAPI)
- `GET /health` — pengecekan status.
- `POST /streams/start` — mulai stream baru segera.
  ```json
  {
    "name": "morning-show",
    "title": "Live Coding",
    "description": "Belajar streaming otomatis",
    "privacy_status": "unlisted",
    "resolution": "1080p",
    "bitrate": "4500k",
    "content": { "source": "/videos/loop.mp4", "is_loop": true, "tags": ["coding"] },
    "extra_ingestion_urls": ["rtmp://live.twitch.tv/app/<stream-key>"]
  }
  ```
- `POST /streams/stop` — hentikan stream: `{ "broadcast_id": "<id>" }`
- `GET /streams/{broadcast_id}` — status + analitik singkat.
- `POST /streams/schedule` — jadwalkan stream (butuh `scheduled_start_time` ISO8601).
- `POST /streams/chat` — kirim pesan chat.
- `POST /streams/disable-chat` — matikan live chat.
- `GET /streams` — daftar sesi yang disimpan.

## Pengujian di Vercel
- File `api/index.py` mengekspor `app` FastAPI untuk serverless.
- `vercel.json` mengarahkan semua route ke fungsi Python. Deploy dan uji endpoint start/stop/schedule menggunakan webhook/HTTP.
- Gunakan sumber konten yang dapat diakses (URL publik atau file yang tersedia di deployment) saat uji di Vercel; untuk streaming penuh gunakan VPS (butuh ffmpeg).

## Deployment 24/7 di VPS
- Jalankan `uvicorn streaming_bot.web:app --host 0.0.0.0 --port 8000` (atau via systemd/supervisor).
- Tempatkan file video lokal di VPS dan rujuk di `content.source`.
- Gunakan webhook/email untuk notifikasi gangguan; bot akan mencoba reconnect otomatis jika kesehatan stream menurun.

## Catatan Operasional
- ffmpeg dijalankan dengan opsi `-stream_loop -1` untuk looping konten. Bitrate/resolusi dikontrol via payload.
- Bot menyimpan log per sesi (10 terakhir via endpoint status) dan menyimpan PID ffmpeg untuk terminasi bersih.
- Untuk multi-stream, panggil endpoint `/streams/start` dengan `name` berbeda; daftar via `/streams`.
