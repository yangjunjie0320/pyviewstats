# ViewStats Monitor

Python async service that fetches YouTube ranking data from ViewStats, enriches
with video duration, translates titles to Chinese, and pushes Feishu interactive
cards via lark-oapi SDK. Generates weekly Feishu documents with embedded short
videos. Runs on a cron schedule inside Docker via `supercronic`.

## Commands

```bash
docker compose up --build -d                      # Start scheduled runs
docker compose run --rm monitor python main.py    # One-off run
docker compose logs -f                            # Check output
```

## Tech Stack

Python 3.12-slim, httpx (async), pycryptodome (AES-GCM), diskcache, python-dotenv,
google-genai (Gemini translation backend), lark-oapi (Feishu SDK for IM + Docx + Drive),
yt-dlp + ffmpeg (short video download). Scheduler: `supercronic` inside Docker.

## Architecture

```
viewstats_monitor/
├── main.py               # Single entrypoint, pipeline orchestration
├── config.py             # Frozen dataclass from env vars; sole reader of os.environ
├── models.py             # Frozen dataclasses: VideoEntry, RankingResult
├── services/
│   ├── viewstats.py      # API client + AES-GCM decrypt; camelCase → snake_case
│   ├── youtube.py        # Duration scraper + yt-dlp video downloader
│   ├── translator.py     # Gemini API translation backend
│   ├── feishu.py         # Daily Feishu IM card sender (via lark-oapi)
│   ├── feishu_doc.py     # Weekly Feishu Docx creator with inline video embeds via `Table` blocks
│   └── video_registry.py # Tracks videos using week_key to strictly prevent duplicates
├── utils/
│   ├── crypto.py         # Pure AES-GCM decrypt logic, no HTTP
│   ├── cache.py          # Shared diskcache.Cache factory, dir = /app/.cache
│   └── logging.py        # configure_logging(), call once in main()
├── crontab               # "0 12 * * * python /app/main.py"
├── Dockerfile            # python:3.12-slim + supercronic + ffmpeg
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

Module boundaries: `services/` = one class per external integration, each owns its
HTTP client and cache read/write. `utils/` = shared infra, no external API calls.
`main.py` = pipeline orchestration only.

## Code Conventions

1. All code, comments, docs in English. Answer user prompts in their language.
2. `dataclasses` (frozen) for all models. No Pydantic.
3. `logging.getLogger(__name__)` everywhere. No `print()`.
4. Type hints on all functions. Modern idioms: `match`, `asyncio.gather()`.
5. Services return new `VideoEntry` via `dataclasses.replace()`. Never mutate.
6. No raw API dicts beyond `services/viewstats.py`.
7. lark-oapi SDK is synchronous; wrap all calls with `asyncio.to_thread()`.

## Data Models (`models.py`)

```python
@dataclass(frozen=True)
class VideoEntry:
    rank: int
    video_id: str
    title: str
    channel: str
    views: int
    outlier_score: float | None = None
    duration_secs: int | None = None
    translated_title: str | None = None
    upload_date: str | None = None
    like_count: int | None = None
    comment_count: int | None = None

@dataclass(frozen=True)
class RankingResult:
    long_videos: tuple[VideoEntry, ...]
    short_videos: tuple[VideoEntry, ...]
```

## Pipeline Flow (`main.py`)

### Daily (every cron run):
1. `load_settings()` → frozen Settings dataclass
2. `ViewStatsClient.fetch_video_rankings()` → `list[VideoEntry]`
3. `YouTubeDurationFetcher.enrich_durations(entries)` → durations filled
4. `VideoRegistry.add_to_weekly_buffer(entries)` → track new videos for doc dedup
5. Split by `DURATION_THRESHOLD_SECS` into long/short lists
6. `Translator.translate_entries(top_n)` → translated titles for card
7. `FeishuNotifier.send_ranking_card()` → daily card via lark-oapi IM API

### Weekly (triggered when ISO week changes):
8. `VideoRegistry.get_week_buffer(prev_week)` → all unique videos from last week
9. Enrich durations + translate ALL titles
10. `FeishuDocArchiver.archive_weekly_report()` → create Feishu document
    - Downloads all short videos via yt-dlp
    - Uploads to Feishu Drive
    - Creates Docx with embedded file blocks
11. `VideoRegistry.archive_week()` → mark as archived (won't appear in future docs)

## Video Registry (`services/video_registry.py`)

Ensures weekly documents are **不重不漏** (no duplicates, no gaps):

| Cache Key | TTL | Purpose |
|---|---|---|
| `registry:archived` | permanent | Set of all video IDs in past docs |
| `registry:buffer:{week}` | permanent | Dict of VideoEntry per week |
| `registry:doc_done:{week}` | permanent | Bool: whether doc was generated |

## Feishu Integration

### Card Sending (`services/feishu.py`)
Uses **lark-oapi IM v1 API** (`client.im.v1.message.create`) with `msg_type="interactive"`.
Requires `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_CHAT_ID`.
All threshold and top-N values in card text are dynamic (no hardcoded "5分钟").

### Document Archival (`services/feishu_doc.py`)
Uses **lark-oapi Docx v1 API** for document creation and block insertion.
Uses **Drive v1 API** for uploading short video files.
Requires `FEISHU_FOLDER_TOKEN` (optional; skips doc archival if unset).

## AES-GCM Decryption (`utils/crypto.py`)

Constants extracted from ViewStats frontend JS. If decrypt raises ValueError,
they rotated keys; re-extract from their site.

## Cache Strategy

| Key pattern | TTL |
|---|---|
| `rankings:{cat}:{country}:{interval}` | 6 hours |
| `duration:{video_id}` | 30 days |
| `translation:{lang}:{md5_of_text}` | 30 days |
| `registry:*` | permanent |

Cache dir: `/app/.cache`, mounted as Docker named volume for persistence.

## Translator Backend (`services/translator.py`)

```python
class GeminiTranslator:   # Uses google-genai SDK, model "gemini-2.0-flash"
class GoogleTranslator:   # Uses unofficial Google Translate endpoint (httpx)
```

Both share cache key pattern (`translation:zh:{md5}`). Gemini auto-falls back
to Google Translate on failure. Backend selected by `TRANSLATE_BACKEND` env var.

## Error Handling

| Scenario | Action |
|---|---|
| ViewStats non-2xx / AES decrypt failure | Raise immediately |
| YouTube fetch fails for one video | WARN, set `duration_secs=0`, continue |
| Video download fails (yt-dlp) | WARN, skip embed, continue doc |
| Translate fails for one title | WARN, keep `translated_title=None` |
| Gemini API key invalid or quota exceeded | WARN, fall back to Google Translate |
| Feishu IM API error | ERROR with code/msg, raise |
| Feishu Docx/Drive API error | ERROR with code/msg, raise |
| Missing required env var | Let `KeyError` crash at startup |

## Environment Variables

| Variable | Default | Note |
|---|---|---|
| `VS_TOKEN` | required | ViewStats Bearer token |
| `FEISHU_APP_ID` | required | Feishu app credentials |
| `FEISHU_APP_SECRET` | required | Feishu app credentials |
| `FEISHU_CHAT_ID` | required | Target chat for daily card |
| `FEISHU_FOLDER_TOKEN` | optional | Target folder for weekly docs |
| `CATEGORY_ID` | `0` | 0 = all |
| `COUNTRY` | `all` | |
| `INTERVAL` | `weekly` | weekly / monthly |
| `DURATION_THRESHOLD_SECS` | `300` | Long/short split |
| `TRANSLATE_BACKEND` | `gemini` | `gemini` or `google` |
| `GEMINI_API_KEY` | required if gemini | Gemini API key |
| `TRANSLATE_TOP_N` | `5` | Per category in daily card |

## Docker Notes

Dockerfile: python:3.12-slim + supercronic + ffmpeg. docker-compose mounts
`cache_vol` to `/app/.cache` and uses `env_file: .env`.

## Git / Code Management

- **GitHub Remote**: `git@github.com:yangjunjie0320/pyviewstats.git`
- **Main Branch**: `main`
- **Ignored Files**: `.env`, `.cache/`, `logs/`

## Pending

- [ ] VS_TOKEN auto-refresh
- [ ] pytest for utils/crypto.py and models.py
- [ ] Per-run cache hit/miss counts in log output