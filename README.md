# AI AOD News Dashboard 📰

[English](README-en.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Docker](https://img.shields.io/badge/docker-automated-blue)](Dockerfile)

> 🚀 **专为技术极客设计的 AI 驱动新闻聚合与筛选系统**。
> Intelligent news curator for technical professionals.

[English README](README-en.md) | [中文说明](README.md)

## 📖 项目简介 (Introduction)

**News Dashboard** 是一个智能化的新闻处理管道，旨在解决信息过载问题。它通过两阶段的 AI 处理流程（L1 快速筛选 + L2 深度分析），从海量 RSS 订阅源中提炼出对开发者、算法工程师和硬核科技爱好者最有价值的信息。

系统不仅进行简单的关键词匹配，而是利用大语言模型（LLM）真正理解新闻内容，进行**去重、评分、中文摘要重写**，并基于独创的**重力算法（Gravity Ranking）** 生成最终的热度排行榜。

### ✨ 核心特性

*   **🧠 双流 AI 架构 (Two-Stage AI Pipeline)**:
    *   **L1 Filter**: 使用轻量级模型 (GPT-4o-mini) 快速过滤掉政治、娱乐等无关噪音，保留技术硬核内容。
    *   **L2 Scorer**: 使用强力模型 (GPT-4o) 进行深度阅读，生成中文技术摘要，重写标题，并进行 0-100 的深度评分。
*   **📉 重力排序算法 (Gravity Ranking)**: 结合新闻的“内容质量分”与“时间衰减因子”，确保榜单既体现热度，又兼顾时效性。让真正的大事（如 DeepSeek 发布）能长时间霸榜。
*   **🔗 智能去重**: 自动识别并合并同一事件的多来源报道，选取最佳信源。
*   **🌐 灵活配置**: 支持自定义 RSS 源、AI 模型参数、扫描间隔等 (通过 `.env`)。
*   **🐳 Docker Ready**: 提供完整的 Docker 支持，一键部署。

## 🛠️ 安装与运行 (Installation)

### 方法一：Docker 部署 (推荐)

1.  **Clone 项目**
    ```bash
    git clone https://github.com/your-username/news-dashboard.git
    cd news-dashboard
    ```

2.  **配置环境变量**
    复制示例配置并修改：
    ```bash
    cp .env_example .env
    ```
    编辑 `.env` 文件，填入你的 OpenAI API Key 和其他配置。

3.  **运行**
    可以直接使用预构建的 Docker 镜像：
    ```bash
    # 拉取镜像
    docker pull ghcr.io/t0saki/ai-news-dashboard:latest
    
    # 运行
    docker run -d \
      --name news-dashboard \
      --env-file .env \
      -v $(pwd)/news.db:/app/news.db \
      -v $(pwd)/dashboard.json:/app/dashboard.json \
      -v $(pwd)/top5.json:/app/top5.json \
      ghcr.io/t0saki/ai-news-dashboard:latest
    ```

    或者你也可以选择自己构建：
    ```bash
    docker build -t news-dashboard .
    docker run -d --env-file .env -v $(pwd)/news.db:/app/news.db -v $(pwd)/dashboard.json:/app/dashboard.json -v $(pwd)/top5.json:/app/top5.json news-dashboard
    ```

### 方法二：本地 Python 运行

需要 Python 3.12+。使用 `uv` 进行依赖管理（推荐）或直接使用 `pip`。

1.  **安装依赖**
    ```bash
    # 使用 uv (推荐)
    uv sync
    
    # 或使用 pip
    pip install -r requirements.txt # (需自行导出)
    ```

2.  **运行**
    ```bash
    # 使用 uv
    uv run main.py
    
    # 或直接 python
    python main.py
    ```

## ⚙️ 配置说明 (Configuration)

在 `.env` 文件中进行核心配置：

| 变量名 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `AI_API_KEY` | (Required) | LLM 服务商的 API Key |
| `AI_BASE_URL` | https://api.openai.com/v1 | LLM API 端点 (支持 OpenAI 兼容接口) |
| `AI_MODEL_L1` | gpt-4o-mini | L1 阶段使用的快速模型 |
| `AI_MODEL_L2` | gpt-4o | L2 阶段使用的强力模型 |
| `FETCH_INTERVAL_SECONDS`| 600 | RSS 抓取循环间隔 (秒) |
| `GRAVITY` | 1.1 | 时间重力衰减因子 (越小衰减越慢) |
| `RANKING_WINDOW_HOURS` | 72 | 排行榜的时间窗口 (小时) |
| `RSS_FEEDS` | (See config.py) | JSON 格式的 RSS 源列表 (可选，覆盖默认) |

## 🏗️ 系统架构 (Architecture)

1.  **Source Manager**: 轮询 RSS Feeds，获取最新文章链接。
2.  **L1 Filter**: 批处理新文章，判断是否值得保留（Tier 1/2/3 分级）。
3.  **L2 Scorer**: 对通过 L1 的文章进行全文（或摘要）分析，生成中文标题和技术摘要。
4.  **Database**: SQLite (`news.db`) 存储所有状态。
5.  **Ranking Engine**: 计算 Gravity Score，输出 `dashboard.json` 和 `top5.json`。

## 📊 输出格式

系统会生成 JSON 文件供前端或其他服务调用：

*   **`dashboard.json`**: 包含完整的排行榜数据、分数、中文摘要等。
*   **`top5.json`**: 精简版 Top 5，适合做这种 E-ink 仪表盘或状态栏显示。

## 🤝 贡献 (Contributing)

欢迎提交 PR 或 Issue！如果你有更好的 Prompt (位于 `prompts/` 目录)，请务必分享！

## 📄 License

MIT License
