# 🚀 TrendCurate - AI-Powered Content Aggregation Platform

An elegant, modern content curation platform that aggregates trending articles, research papers, YouTube videos, and more from across the internet using AI-powered recommendations.

## ✨ Key Features

- **🔄 Real-Time Content Aggregation** - Automatically fetches content from multiple sources
- **🎯 Personalized Feed** - AI-curated content based on user interests  
- **📱 Responsive Design** - Beautiful mosaic layout that works on all devices
- **🔖 Smart Bookmarking** - Save and organize content with folders
- **🤖 AI Summaries** - Generated summaries for quick content overview
- **⚡ High Performance** - Optimized for speed with modern tech stack

## 🏗️ Architecture

```
React Frontend ←→ Node.js API ←→ PostgreSQL ←→ Python Content Service
     ↓                ↓              ↓              ↓
  User Interface   Auth & API    Shared Database   Content Sources
   Bookmarks       User Data      Unified Schema    (HN, RSS, etc.)
```

## 🛠️ Tech Stack

### Frontend
- **React 18** + TypeScript
- **Tailwind CSS** + Shadcn/UI
- **Wouter** for routing
- **TanStack Query** for state management

### Backend (Node.js)
- **Express.js** + TypeScript
- **Drizzle ORM** + PostgreSQL
- **JWT Authentication**
- **OpenAI Integration**

### Content Service (Python)
- **FastAPI** + SQLAlchemy
- **AsyncIO** for concurrency
- **Firecrawl** for reliable web scraping
- **Multiple content sources**
- **ML-ready architecture**

## 🚀 Quick Start

### One-Command Launch
```bash
./start-services.sh
```

### Manual Setup

1. **Environment Setup**
   ```bash
   # Copy environment files
   cp TrendCurate/.env.example TrendCurate/.env
   cp walker_app_api/.env.example walker_app_api/.env
   # Edit with your database credentials
   ```

2. **Start Python Backend**
   ```bash
   cd walker_app_api
   pip install -r requirements.txt
   python main.py
   ```

3. **Start Node.js Backend**
   ```bash
   cd TrendCurate
   npm run setup
   npm run dev
   ```

4. **Access Application**
   - Frontend: http://localhost:5000
   - API Docs: http://localhost:8000/docs

## 📊 Content Sources

### Currently Active
- **Hacker News** - Tech discussions and trending stories
- **RSS Feeds** - TechCrunch, AWS Blog, Google Tech, O'Reilly
- **Sample Content** - YouTube videos and research papers

### Coming Soon
- **YouTube Data API** - Tech tutorials and talks
- **arXiv** - Latest research papers
- **Twitter/X** - Tech industry posts
- **Podcasts** - Developer and tech podcasts

## 🔧 API Endpoints

### Content
- `GET /api/content` - Get personalized content feed
- `POST /api/admin/aggregate-content` - Trigger content refresh

### User Management  
- `POST /api/auth/signup` - Create new account
- `POST /api/auth/login` - User authentication
- `PATCH /api/user/interests` - Update user preferences

### Bookmarks
- `POST /api/bookmarks` - Save content
- `GET /api/bookmarks` - Get saved content
- `POST /api/bookmark-folders` - Create folder

## 🎯 How It Works

1. **Content Aggregation**: Python service fetches content from multiple sources
2. **AI Processing**: OpenAI generates summaries and categorizes content  
3. **Storage**: Unified PostgreSQL schema stores all content
4. **Personalization**: Node.js API serves content based on user interests
5. **Display**: React frontend presents content in beautiful mosaic layout

## 🔐 Environment Variables

### Required
```bash
DATABASE_URL=postgresql://...    # Shared PostgreSQL database
FIRECRAWL_API_KEY=fc-...        # For web scraping (get from firecrawl.dev)
```

### Optional  
```bash
OPENAI_API_KEY=sk-...           # For AI summaries (not currently used)
```

## 📈 Monitoring

### Health Checks
```bash
curl http://localhost:5000/api/content        # Node.js API
curl http://localhost:8000/health             # Python API
curl http://localhost:8000/api/v1/aggregation/status  # Content stats
```

### Integration Test
```bash
cd TrendCurate
npm run test:integration
```

## 🚀 Deployment

### Development
```bash
./start-services.sh
```

### Production
- Deploy Node.js backend to your platform of choice
- Deploy Python backend as microservice
- Use managed PostgreSQL (recommended: Neon)
- Set up reverse proxy (nginx/Cloudflare)

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **OpenAI** for AI capabilities
- **Shadcn** for beautiful UI components  
- **TailwindCSS** for styling system
- **FastAPI** for Python backend framework
- **Drizzle** for type-safe database operations

---

**Made with ❤️ for the developer community**

Ready to curate the internet? Get started with `./start-services.sh`! 🚀