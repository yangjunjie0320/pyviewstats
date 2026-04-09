# PyViewStats

Automated monitoring pipeline that fetches YouTube video rankings from ViewStats, enriches data (durations, likes), translates titles via Gemini, and automatically publishes weekly Feishu Docx reports with inline embedded short videos.

## Features

- **Rankings & Enrichment**: Fetches ViewStats top videos and scrapes YouTube for precise durations.
- **Auto-Categorization**: Splits videos into long/short and strictly deduplicates them across weeks.
- **Feishu Document Automation**: Generates Feishu Docx weekly reports, auto-downloading and embedding short videos via `yt-dlp` into side-by-side Table layouts.
- **Daily IM Notifications**: Sends interactive daily top-N summary cards to Feishu groups.
- **Dockerized Cron**: Runs scheduled tasks via `supercronic` in Docker.

## Requirements

- Python 3.12+
- Docker & Docker Compose
- Feishu API Application setup (App ID, App Secret, Folder Token, Chat ID)
- ViewStats API Token
- Gemini API Key

## Configuration

Copy `.env.example` to `.env` and fill in your details:

```bash
cp .env.example .env
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
- `TRANSLATE_TOP_N`: Number of top videos from each category to translate (default: 5 short / 5 long).

## Getting Started

### Local Development

1. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Run the main pipeline manually:
   ```bash
   python main.py
   ```

### Docker Deployment

Deploy the system with Docker Compose. It includes a configured crontab to run the pipeline periodically.

```bash
docker-compose up -d --build
```

The container handles cron scheduling using the included `crontab` file to trigger the Python job. Output logs map to `./logs/` by default.

## License
MIT
