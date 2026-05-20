# PyViewStats

Automated monitoring pipeline that fetches YouTube video rankings from ViewStats, enriches data (durations, likes), translates titles via Gemini, and automatically publishes weekly Feishu Docx reports with inline embedded short videos.

## Features

- **Rankings & Enrichment**: Fetches ViewStats top videos and scrapes YouTube for precise durations.
- **Auto-Categorization**: Splits videos into long/short and strictly deduplicates them across weeks.
- **Daily Pre-processing**: Translates all video titles and pre-downloads short videos daily with throttling (10s delay + exponential backoff retry), spreading network load evenly.
- **Feishu Document Automation**: Generates Feishu Docx weekly reports using pre-cached videos, embedding them into side-by-side Table layouts.
- **Daily IM Notifications**: Sends interactive daily top-N summary cards to Feishu groups.
- **Dockerized Cron**: Runs scheduled tasks via `supercronic` in Docker.

## Requirements

- Python 3.12+
- Docker & Docker Compose
- Feishu API Application setup (App ID, App Secret, Folder Token, Chat ID)
- ViewStats API Token
- Gemini API Key

## Configuration

Copy `config.example.yaml` to `config.yaml` and fill in your details:

```bash
cp config.example.yaml config.yaml
```

Key environment variables:

- `VS_TOKEN`: ViewStats API token.
- `FEISHU_APP_ID`: Feishu ISV / Internal application ID.
- `FEISHU_APP_SECRET`: Feishu application secret key.
- `FEISHU_CHAT_ID`: Destination Chat/Group ID where document links will be sent.
- `FEISHU_FOLDER_TOKEN`: Feishu Drive Folder token where weekly documents will be stored.
- `CATEGORY_ID`: YouTube category ID (default: 0 for all).
- `COUNTRY`: ViewStats country code (default: all).
- `DURATION_THRESHOLD_SECS`: Threshold to divide short vs long videos (default: 300).
- `GEMINI_API_KEY`: Google Gemini API Key for translations.
- `TRANSLATE_TOP_N`: Number of top videos per group shown in the daily card (default: 5).

## Getting Started

### Local Development

1. Install dependencies with `uv`:
   ```bash
   uv sync
   ```
2. Run the main pipeline manually:
   ```bash
   uv run python main.py
   ```
3. Run tests:
   ```bash
   uv run pytest tests/ -v
   ```

### Docker Deployment

Deploy the system with Docker Compose. It includes a configured crontab to run the pipeline periodically.

```bash
docker compose up -d --build
```

The container handles cron scheduling using the included `crontab` file to trigger the Python job. Output logs map to `./logs/` by default.

## Development

- **Architecture**: see `DESIGN.md` (local only, not committed to git).
- **AI collaboration**: see `CLAUDE.md` and `AGENTS.md` (local only).
- **Tests**: `tests/` directory, run with `uv run pytest`.

## License
MIT
