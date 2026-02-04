# AI-Now

**AI News Aggregator** - Stay up-to-date with the latest AI research, news, and developments from leading labs and organizations.

---

## Live Deployment

- **Frontend**: [https://ai-now.vercel.app](https://ai-now.vercel.app)
- **Backend API**: [https://ai-now.onrender.com](https://ai-now.onrender.com)
- **API Health Check**: [https://ai-now.onrender.com/health](https://ai-now.onrender.com/health)

---

## Features

- **Multi-source Aggregation**: Automatically collects content from:
  - RSS feeds from leading AI labs
  - YouTube channels for video content
  - Custom web scrapers for Anthropic, OpenAI, xAI, Qwen, Moonshot, Hugging Face, and more
  
- **Modern UI**: Beautiful, responsive interface built with React + TypeScript
  - Dark/light theme support
  - Mosaic feed layout
  - Real-time content updates
  
- **Robust Backend**: FastAPI-powered API with:
  - PostgreSQL database
  - Automatic deduplication
  - Thumbnail extraction
  - Token-based security

---

## Project Structure

```
main_folder/
├── AI-Now/                    # React frontend (Vite + TypeScript)
│   ├── src/
│   │   ├── components/        # UI components
│   │   ├── pages/            # Page components
│   │   └── hooks/            # React hooks
│   └── package.json
│
└── walker_app_api/           # FastAPI backend
    ├── app/
    │   ├── api/              # API endpoints
    │   ├── services/         # Content aggregation services
    │   │   └── aggregation_sources/  # Individual scrapers
    │   ├── db/               # Database models
    │   └── core/             # Configuration
    ├── alembic/              # Database migrations
    ├── pyproject.toml
    └── uv.lock
```

---

## 🛠️ Local Development

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL

### Quick Start

1. **Clone the repository**
   ```bash
   git clone 
   cd main_folder
   ```

2. **Set up environment**
   ```bash
   # Generate security keys
   python3 generate-keys.py
   
   # Create .env file in walker_app_api/
   # Add DATABASE_URL, AGGREGATION_SERVICE_TOKEN
   ```
   > The backend uses `uv` with a project-local virtual environment stored in `.venv/`. If you previously created a `venv/` directory, remove it to avoid environment conflicts.

3. **Start services**
   ```bash
   ./start-services.sh
   ```

4. **Visit the app**
   - Frontend: http://localhost:5173
   - Backend: http://localhost:8000
   - API Docs: http://localhost:8000/docs

See [QUICKSTART.md](QUICKSTART.md) for detailed deployment instructions.

---

## Tech Stack

### Frontend
- **React 18** with TypeScript
- **Vite** for blazing-fast builds
- **TanStack Query** for data fetching
- **Tailwind CSS** + **shadcn/ui** for styling
- **Lucide React** for icons

### Backend
- **FastAPI** for high-performance API
- **SQLAlchemy** for database ORM
- **Alembic** for migrations
- **httpx** for async HTTP requests
- **Selenium** for dynamic web scraping
- **BeautifulSoup4** for HTML parsing

### Infrastructure
- **Frontend**: Vercel (CDN + auto-deploy)
- **Backend**: Render (containerized Python)
- **Database**: PostgreSQL on Render
