# AI-Now

**AI News Aggregator** — Stay up-to-date with the latest AI research, news, and developments from leading labs and organizations.

---

## Features

- **Multi-source Aggregation**: Automatically collects content from:
  - RSS feeds from leading AI labs
  - YouTube channels for video content
  - Custom web scrapers for Anthropic, OpenAI, xAI, Qwen, Moonshot, Hugging Face, and more
  - Plugin architecture — add new sources by dropping in a single file

- **Modern UI**: Responsive interface built with React + TypeScript
  - Dark/light theme support
  - Mosaic feed layout
  - Real-time content updates

- **Robust Backend**: FastAPI-powered API with:
  - PostgreSQL database
  - Automatic deduplication
  - Thumbnail extraction
  - Token-based security
  - User authentication and preferences

---

## Project Structure

```
AI-Now/                            # React frontend (Vite + TypeScript)
├── client/
│   └── src/
│       ├── components/            # UI components (feed, layout, navigation, theme)
│       ├── pages/                 # Page components
│       ├── hooks/                 # React hooks
│       ├── context/               # React context providers
│       └── types/                 # TypeScript type definitions
└── shared/                        # Shared utilities

walker_app_api/                    # FastAPI backend
├── app/
│   ├── api/v1/endpoints/          # API endpoints (content, aggregation, analytics, auth, sources)
│   ├── core/                      # Configuration and security
│   ├── crud/                      # Database operations
│   ├── db/                        # Database models and setup
│   ├── schemas/                   # Pydantic schemas
│   └── services/
│       ├── aggregation/
│       │   ├── plugins/           # Source plugins (anthropic, openai, xai, youtube, rss, etc.)
│       │   ├── utils/             # Shared utilities (date parsing, HTML, webdriver)
│       │   ├── aggregator.py      # Core aggregation engine
│       │   ├── registry.py        # Plugin registry
│       │   └── user_source_engine.py
│       ├── auth_service.py
│       └── analytics_queue.py
├── alembic/                       # Database migrations
├── tests/                         # Test suite
├── pyproject.toml
└── uv.lock
```

---

## Local Development

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 18+
- PostgreSQL

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/whyman903/AI-Now.git
   cd AI-Now
   ```

2. **Set up the backend**
   ```bash
   cd walker_app_api
   uv sync

   # Create a .env file with the required variables:
   # DATABASE_URL, AGGREGATION_SERVICE_TOKEN, JWT_SECRET_KEY
   cp .env.example .env
   # Edit .env with your values
   ```

3. **Run database migrations**
   ```bash
   uv run alembic upgrade head
   ```

4. **Start the backend**
   ```bash
   uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **Start the frontend** (in a separate terminal)
   ```bash
   cd AI-Now
   npm install
   npm run dev
   ```

6. **Visit the app**
   - Frontend: http://localhost:5173
   - Backend: http://localhost:8000
   - API Docs: http://localhost:8000/docs

---

## Tech Stack

### Frontend
- **React 18** with TypeScript
- **Vite** for builds
- **TanStack Query** for data fetching
- **Tailwind CSS** + **shadcn/ui** for styling

### Backend
- **FastAPI** for high-performance async API
- **SQLAlchemy** for database ORM
- **Alembic** for migrations
- **httpx** for async HTTP requests
- **Selenium** for dynamic web scraping
- **BeautifulSoup4** for HTML parsing

### Infrastructure
- **Frontend**: Vercel
- **Backend**: Render
- **Database**: Neon PostgreSQL
