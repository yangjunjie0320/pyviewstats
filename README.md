# PyViewStats

PyViewStats is an automated monitoring pipeline that fetches video rankings from ViewStats, enriches the data with YouTube metadata (such as video durations), translates the titles using Gemini, and automatically creates comprehensive weekly Feishu documents with inline embedded videos via the `lark-oapi` SDK.

## Features

- **ViewStats API Integration**: Automatically fetches the latest top video rankings by category and country.
- **Data Enrichment**: Scrapes and parses YouTube watch pages to extract accurate video duration data.
- **Categorization & De-duplication**: Dynamically splits videos into "long" and "short" categories. Uses a persistent Video Registry to ensure videos don't duplicate across weeks.
- **Automated Translation**: Uses Gemini API to translate video titles.
- **Feishu Document Automation**: Generates rich interactive Feishu Docx format weekly reports. Automatically downloads short videos via `yt-dlp` and embeds them directly into the document in a side-by-side table layout using the Drive and Docx APIs.
- **Feishu IM Notifications**: Pushes document links seamlessly to Feishu groups via the Bot API.
- **Dockerized Environment**: Runs on a scheduled cron configuration using `supercronic` in Docker.

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
