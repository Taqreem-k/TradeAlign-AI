# 📈 TradeAlign-AI

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Gemini-Multimodal_v1beta-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0_Async-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![uv](https://img.shields.io/badge/uv-Package_Manager-DE5FE9?style=for-the-badge)

**TradeAlign-AI** is an autonomous Indian equity intelligence pipeline that monitors **NSE (National Stock Exchange)** corporate announcements in real time, reads raw filing PDFs using **Gemini's multimodal vision engine**, filters out routine SEBI compliance noise, and delivers structured market briefs via a live **Streamlit dashboard** and **End-of-Day HTML email digests**.

---

## Why TradeAlign-AI?

Every trading day, Indian listed companies publish **500 to 1,000+ corporate filing PDFs** under SEBI LODR regulations. Nearly 90% are routine procedural disclosures (trading window closures, lost share certificates, conference call audio links), while the 5–15 market-moving disclosures (quarterly earnings, order wins, dividends, M&A, leadership exits) are buried inside dense multi-page scanned PDFs.

TradeAlign-AI replaces manual research by:

1. **Prioritizing Your Watchlist:** Tracks your custom NSE portfolio symbols (`RELIANCE`, `TCS`, `ICICIBANK`, `HAL`, etc.) at the front of the processing queue and guarantees they appear in your daily alerts.
2. **Reading Scanned Tables Directly:** Feeds raw PDF bytes straight to Gemini (`types.Part.from_bytes`), avoiding brittle OCR/text-extraction libraries that flatten multi-column Indian financial statements.
3. **Scoring Materiality (1–10):** Tags routine compliance noise (`1–3`) vs. high-impact catalysts (`7–10`) so your inbox only gets signal.

---

## Live Previews

### 1. Real-Time Streamlit Dashboard
*Live dashboard running at `http://localhost:8501` with Watchlist prioritization, sentiment badges, extracted financial metrics, and one-click links to official `nsearchives.nseindia.com` PDFs.*

![TradeAlign-AI Live Dashboard](assets/dashboard-preview.png)

### 2. End-of-Day HTML Email Digest
*Automated 5:15 PM IST daily brief separating **★ Your Watchlist Alerts** from **Market-Wide High-Impact Briefs**.*

![TradeAlign-AI EOD Email Digest](assets/email-digest.png)

<details>
<summary><strong>View Docker Stack & Live Worker Logs</strong></summary>

*All three services (`postgres`, `worker`, `dashboard`) running healthy alongside live NSE ingestion and Gemini multimodal processing logs.*

![TradeAlign-AI Worker Logs](assets/worker-logs.png)

</details>

---

## System Architecture

```text
                       ┌──────────────────────────────────────┐
                       │      NSE Corporate Announcements     │
                       │  Primary: JSON API (curl_cffi TLS)   │
                       │  Fallback: Official XML RSS Feed     │
                       └──────────────────┬───────────────────┘
                                          │ Rolling 2-Day Window (15m IST Poll)
                                          ▼
                       ┌──────────────────────────────────────┐
                       │         PostgreSQL 16 Queue          │
                       │  • Idempotent ON CONFLICT Upsert     │
                       │  • Priority Index: Watchlist -> New  │
                       │  • JSONB Takeaways & Metrics         │
                       └─────────┬───────────────────┬────────┘
                                 │                   │
             Fetch PENDING PDFs  │                   │ Read MarketBriefs
           (13s RPM Pacing)      ▼                   ▼ (NullPool Async)
┌────────────────────────────────────────┐   ┌───────────────────────────────┐
│      Gemini Multimodal Analyzer        │   │      Streamlit Dashboard      │
│  • Raw PDF Vision (v1beta API)         │   │  • Live KPI Strip             │
│  • Strict Pydantic Constrained JSON    │   │  • Watchlist & Impact Filters │
│  • Auto-Failover Chain (404/429/503)   │   │  • Direct NSE PDF Links       │
└───────────────────┬────────────────────┘   └───────────────────────────────┘
                    │ Save MarketBrief
                    ▼
┌────────────────────────────────────────┐
│       Async EOD HTML Emailer           │
│  • APScheduler (17:15 IST, Mon–Fri)    │
│  • Watchlist Alerts + Impact >= 6      │
│  • Async SMTP via aiosmtplib           │
└────────────────────────────────────────┘
```

---

## Engineering Highlights

* **Anti-Bot Resilient Hybrid Ingestion (`src/ingestion/nse_client.py`):** Uses `curl_cffi` to impersonate Chrome's BoringSSL TLS/JA3 and HTTP/2 handshake with lazy cookie warm-up against NSE's JSON endpoint, and automatically degrades to NSE's official public XML RSS feed (`Online_announcements.xml`) on any API throttle or error.
* **Self-Healing PostgreSQL Queue (`src/db/repository.py`):** Uses PostgreSQL `ON CONFLICT (filing_id) DO NOTHING` for idempotent bulk upserts across midnight boundaries, backed by a composite index on `(status, is_watchlist, announced_at)` so Watchlist filings jump ahead of market-wide filings in a single indexed scan.
* **Constrained Multimodal Extraction (`src/ai/analyzer.py`, `schemas.py`):** Pins the `google-genai` async client to `v1beta` and enforces strict Pydantic structured outputs (`response_schema=MarketBriefOutput`, `temperature=0.1`) preserving Indian financial units (`₹ Crores`, `₹ Lakhs`, `YoY`, `QoQ`).
* **Multi-Model Failover & Rate-Limit Backpressure (`src/ai/analyzer.py`, `src/main.py`):** Walks an automatic fallback model chain (`gemini-4-hydrogen` → `gemini-3.8-flash` → `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite`) on `404`/`429`/`5xx`, paces requests at `<= 4.6 RPM` (13s interval), and leaves filings `PENDING` on `429`/`503` backpressure instead of permanently marking them `FAILED`.
* **Crash-Free Async Dashboard (`src/dashboard/app.py`):** Disposes a per-call `NullPool` SQLAlchemy async engine inside `@st.cache_data(ttl=60)`, preventing `RuntimeError: Future attached to a different loop` across Streamlit reruns without requiring a second sync driver.
* **Production Container Stack (`docker/` & `docker-compose.yml`):** Multi-service Docker Compose orchestration (`postgres`, `worker`, `dashboard`) with `uv` layer caching, `pg_isready` health checks, and `max_instances=1` / `coalesce=True` APScheduler guards.

---

## Project Structure

```text
TradeAlign-AI/
├── assets/
│   ├── dashboard-preview.png     # Live Streamlit UI screenshot
│   ├── email-digest.png          # Rendered EOD HTML email screenshot
│   └── worker-logs.png           # Docker Compose & worker log proof
├── docker/
│   ├── Dockerfile.dashboard      # Streamlit UI container (uv + Python 3.12)
│   └── Dockerfile.worker         # Async ingestion, Gemini & SMTP daemon
├── src/
│   ├── ai/
│   │   ├── analyzer.py           # Async Gemini v1beta client + model failover
│   │   └── schemas.py            # Strict Pydantic MarketBriefOutput contract
│   ├── dashboard/
│   │   └── app.py                # Live Streamlit UI with Watchlist & impact filters
│   ├── db/
│   │   ├── models.py             # SQLAlchemy 2.0 Announcement & MarketBrief tables
│   │   ├── repository.py         # Idempotent upserts & priority queue queries
│   │   └── session.py            # Async engine & transactional session manager
│   ├── delivery/
│   │   └── mailer.py             # Async HTML EOD digest renderer & SMTP sender
│   ├── ingestion/
│   │   ├── nse_client.py         # Hybrid NSE JSON API + Official RSS client
│   │   └── schemas.py            # Unified NSEAnnouncement validator (IST)
│   ├── config.py                 # Pydantic Settings + Watchlist parser
│   └── main.py                   # APScheduler IST orchestrator & RPM pacing
├── docker-compose.yml            # PostgreSQL 16 + Worker + Dashboard stack
├── pyproject.toml                # Hatchling build config & dependencies
└── uv.lock                       # Deterministic dependency lockfile
```

---

## Quickstart (Docker Compose)

### 1. Clone the Repository

```bash
git clone https://github.com/Taqreem-k/TradeAlign-AI.git
cd TradeAlign-AI
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```env
# PostgreSQL (Docker Compose)
POSTGRES_USER=tradealign
POSTGRES_PASSWORD=tradealign_pass
POSTGRES_DB=tradealign_db

# Local DB URL (Docker Compose automatically overrides host to 'postgres:5432')
DATABASE_URL=postgresql+asyncpg://tradealign:tradealign_pass@localhost:5433/tradealign_db

# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-4-hydrogen

# NSE Scraper & Personal Watchlist
NSE_POLL_INTERVAL_MINUTES=15
NSE_REQUEST_TIMEOUT_SECONDS=20
WATCHLIST_SYMBOLS=RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK,TATAMOTORS,ZOMATO,HAL

# Async SMTP Email Digest (Use a 16-char Gmail App Password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_16_char_app_password
RECIPIENT_EMAIL=your_email@gmail.com
```

### 3. Launch the Stack

```bash
docker compose up --build -d
```

### 4. Monitor & View Briefs

* **Live Dashboard:** Open **`http://localhost:8501`**
* **Worker Logs:** `docker compose logs -f worker`
* **Trigger EOD Email Manually:** `docker compose exec worker uv run --no-sync python -c "import asyncio; from src.main import run_eod_digest; asyncio.run(run_eod_digest())"`
* **Stop Services:** `docker compose down`

---

## Scheduling (IST — `Asia/Kolkata`)

| Job | Schedule | Behavior |
| :--- | :--- | :--- |
| **NSE Ingestion & Analysis** | Mon–Fri, `09:00–17:00 IST` (every 15 min) | Scrapes rolling 2-day NSE filings, deduplicates into Postgres, and analyzes up to 5 prioritized PDFs per cycle (Watchlist first). Runs once immediately on boot. |
| **EOD HTML Digest** | Mon–Fri, `17:15 IST` | Emails all unemailed Watchlist alerts plus market-wide briefs with `impact_score >= 6`, then stamps `emailed_at` to prevent duplicate sends. |

---

## Disclaimer

*TradeAlign-AI is an automated financial data extraction and summarization tool built for informational and engineering research purposes. All summaries link directly to official NSE filings for verification. Nothing generated by this system constitutes investment or financial advice.*

---

## Author

**Mohammad Taqreem Khan** — [GitHub (@Taqreem-k)](https://github.com/Taqreem-k)