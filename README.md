# PyViewStats

PyViewStats is an automated monitoring pipeline that fetches video rankings from ViewStats, enriches the data with YouTube metadata (such as video durations), translates the titles using Google Translate or Gemini (LLM), and sends the formatted results via Feishu interactive bot cards.

## Features

- **ViewStats API Integration**: Automatically fetches the latest top video rankings by category and country.
- **Data Enrichment**: Scrapes and parses YouTube watch pages to extract accurate video duration data.
- **Categorization**: Dynamically splits videos into "long" and "short" categories based on customizable duration thresholds.
- **Automated Translation**: Uses Google Translate or Gemini to translate video titles.
- **Feishu Bot Integration**: Delivers stunning interactive bot cards directly to a Feishu group.
- **Dockerized Cron Job**: Runs automatically using Docker & `crontab`.

## Requirements

- Python 3.10+
- Docker & Docker Compose (optional but recommended for deployment)
- Feishu Custom Bot Webhook URL
- ViewStats API Token
- Gemini API Key (Optional, if using Gemini as translation backend)

## Configuration

Copy `.env.example` to `.env` and fill in your details:

```bash
cp .env.example .env
```

Key environment variables:

- `VS_TOKEN`: ViewStats API token.
- `FEISHU_BOT_URL`: Webhook URL for the Feishu Custom Bot.
- `CATEGORY_ID`: YouTube category ID (default: 0 for all).
- `COUNTRY`: ViewStats country code (default: all).
- `INTERVAL`: Time interval for rankings (default: weekly).
- `DURATION_THRESHOLD_SECS`: Threshold to divide short vs long videos (default: 300).
- `TRANSLATE_BACKEND`: `gemini` or `google` (default: gemini).
- `GEMINI_API_KEY`: Required if using `gemini` backend.
- `TRANSLATE_TOP_N`: Number of top videos from each category to translate (default: 5).

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
