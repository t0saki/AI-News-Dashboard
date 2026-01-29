# AI AOD News Dashboard 📰

[中文](README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Docker](https://img.shields.io/badge/docker-automated-blue)](Dockerfile)

> 🚀 **Intelligent, AI-Driven News Aggregator & Curator for Tech Professionals.**

[English README](README-en.md) | [中文说明](README.md)

## 📖 Introduction

**News Dashboard** is an intelligent information processing pipeline designed to combat information overload. It utilizes a **Two-Stage AI Pipeline (L1 Filter + L2 Scorer)** to distill only the most valuable, "hardcore" technical insights from high-volume RSS feeds.

Instead of simple keyword matching, it leverages Large Language Models (LLMs) to genuinely understand content, performing **deduplication, scoring, rewriting (summarization)**, and ranking based on a unique **Gravity Ranking Algorithm**.

### ✨ Key Features

*   **🧠 Two-Stage AI Pipeline**:
    *   **L1 Filter**: Uses a lightweight model (e.g., GPT-4o-mini) to rapidly discard noise (politics, gossip) and keep only high-value tech news.
    *   **L2 Scorer**: Uses a powerful model (e.g., GPT-4o) for deep analysis, generating concise technical summaries, translating titles, and assigning a relevance score (0-100).
*   **📉 Gravity Ranking**: A smart ranking algorithm combining "Content Score" with a "Time Decay Factor". This ensures the feed stays fresh while allowing truly significant events (like a major model release) to stay on top longer.
*   **🔗 Smart Deduplication**: Automatically identifies and merges multi-source coverage of the same event, selecting the most informative source.
*   **🌐 Flexible Configuration**: Fully customizable RSS sources, AI models, and scheduling via `.env`.
*   **🐳 Docker Ready**: Ready-to-deploy Docker image included.

## 🛠️ Installation & Usage

### Method 1: Docker (Recommended)

1.  **Clone the repository**
    ```bash
    git clone https://github.com/your-username/news-dashboard.git
    cd news-dashboard
    ```

2.  **Configure Environment**
    Copy the example config:
    ```bash
    cp .env_example .env
    ```
    Edit `.env` and fill in your OpenAI API Key and other settings.

3.  **Run**
    You can use the pre-built Docker image directly:
    ```bash
    # Pull image
    docker pull ghcr.io/t0saki/ai-news-dashboard:latest
    
    # Run
    docker run -d \
      --name news-dashboard \
      --env-file .env \
      -v $(pwd)/news.db:/app/news.db \
      -v $(pwd)/dashboard.json:/app/dashboard.json \
      -v $(pwd)/top5.json:/app/top5.json \
      ghcr.io/t0saki/ai-news-dashboard:latest
    ```

    Or you can build it yourself:
    ```bash
    docker build -t news-dashboard .
    docker run -d --env-file .env -v $(pwd)/news.db:/app/news.db -v $(pwd)/dashboard.json:/app/dashboard.json -v $(pwd)/top5.json:/app/top5.json news-dashboard
    ```

### Method 2: Local Python

Requires Python 3.12+. We recommend `uv` for dependency management.

1.  **Install Dependencies**
    ```bash
    # Using uv (Recommended)
    uv sync
    
    # Or using standard pip
    pip install -r requirements.txt # (You may need to export this yourself first)
    ```

2.  **Run**
    ```bash
    # Using uv
    uv run main.py
    
    # Or standard python
    python main.py
    ```

## ⚙️ Configuration

Configure the core settings in your `.env` file:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `AI_API_KEY` | (Required) | API Key for your LLM provider. |
| `AI_BASE_URL` | https://api.openai.com/v1 | LLM API Endpoint (OpenAI compatible). |
| `AI_MODEL_L1` | gpt-4o-mini | Fast model for initial filtering. |
| `AI_MODEL_L2` | gpt-4o | Strong model for deep analysis. |
| `FETCH_INTERVAL_SECONDS`| 600 | RSS fetch interval in seconds. |
| `GRAVITY` | 1.1 | Time decay gravity factor (Lower = slower decay). |
| `RANKING_WINDOW_HOURS` | 72 | Time window for the ranking board (hours). |
| `RSS_FEEDS` | (See config.py) | JSON list of RSS feeds (Optional upgrade). |

## 🏗️ Architecture

1.  **Source Manager**: Polls RSS Feeds for new links.
2.  **L1 Filter**: Batches new items to decide if they are worth keeping (Tier 1/2/3).
3.  **L2 Scorer**: Deep analysis of passed items. Generates translated titles and technical summaries.
4.  **Database**: SQLite (`news.db`) stores all state.
5.  **Ranking Engine**: Calculates Gravity Score, outputting `dashboard.json` and `top5.json`.

## 📊 Output

The system generates JSON files for frontend or external consumption:

*   **`dashboard.json`**: Complete ranked list with scores, summaries, and metadata.
*   **`top5.json`**: Simplified top 5 list, ideal for E-ink displays or widgets.

## 🤝 Contributing

PRs and Issues are welcome! If you have optimized Prompts (in `prompts/`), please share them!

## 📄 License

MIT License
