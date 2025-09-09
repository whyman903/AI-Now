# 🔥 Firecrawl Setup Guide

## Where to Put Your Firecrawl API Key

### 1. Get Your API Key
- Go to [firecrawl.dev](https://firecrawl.dev)
- Sign up for an account
- Get your API key (starts with `fc-`)

### 2. Add It to Your Environment File

**Option A: Edit the .env file directly**
```bash
cd walker_app_api
nano .env  # or use any text editor
```

Add your API key:
```bash
FIRECRAWL_API_KEY=fc-your-actual-api-key-here
```

**Option B: Use the terminal**
```bash
cd walker_app_api
echo "FIRECRAWL_API_KEY=fc-your-actual-api-key-here" >> .env
```

### 3. Verify It Works
```bash
python -c "import os; from dotenv import load_dotenv; load_dotenv(); key=os.getenv('FIRECRAWL_API_KEY'); print('✅ Real API Key found!' if key and key.startswith('fc-') and key != 'fc-test-key' else '⚠️ Placeholder key - web scraping disabled')"
```

### 4. Test the Integration
```bash
python run_unified_aggregation.py
```

## 🧹 Cleaned Up Environment Variables

I removed all the unused API keys:
- ❌ `YOUTUBE_API_KEY` (not used - we get YouTube via RSS)
- ❌ `SPOTIFY_CLIENT_ID` (not used at all)
- ❌ `SPOTIFY_CLIENT_SECRET` (not used at all)
- ❌ `SESSION_SECRET` (not used)

Only kept what's actually needed:
- ✅ `DATABASE_URL` (required)
- ✅ `SECRET_KEY` (required) 
- ✅ `FIRECRAWL_API_KEY` (required for web scraping)
- ✅ `OPENAI_API_KEY` (optional, not currently used)

## 🚀 Ready to Go!

Your `.env` file should look like this:
```bash
# Database Configuration (REQUIRED)
DATABASE_URL=postgresql://your-db-url-here

# Security (REQUIRED)
SECRET_KEY=your-super-secret-key-here-change-this-in-production

# Firecrawl API Key (REQUIRED for web scraping)
FIRECRAWL_API_KEY=fc-your-firecrawl-api-key-here

# Optional API Keys
OPENAI_API_KEY=sk-your-openai-key-if-you-have-one
```
