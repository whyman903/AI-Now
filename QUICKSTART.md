# 🚀 AI-Now Deployment Guide

Deploy your AI-Now app online in **under 30 minutes**!

**Stack**: FastAPI backend on **Render** + React frontend on **Vercel**

---

## 📋 Before You Start

### 1. Generate Secure Keys
Run this in your terminal:
```bash
python3 generate-keys.py
```

**Save the output!** You'll need:
- `SECRET_KEY`
- `AGGREGATION_SERVICE_TOKEN`

### 2. Push to GitHub
```bash
git add .
git commit -m "Ready for deployment"
git push
```

---

## 🔧 Step 1: Deploy Backend (Render)

### A. Create Database
1. Go to https://dashboard.render.com
2. Click **New +** → **PostgreSQL**
3. Settings:
   - Name: `walker-app-db`
   - Plan: **Free**
4. Click **Create Database**
5. **📋 Copy the "Internal Database URL"**

### B. Create Web Service
1. Click **New +** → **Web Service**
2. Connect your GitHub repository
3. Configure:
   - **Name**: `walker-app-api` (or your choice)
   - **Root Directory**: `walker_app_api`
   - **Environment**: `Python 3`
   - **Build Command**:
     ```
     pip install --upgrade pip && pip install -r requirements.txt
     ```
   - **Start Command**:
     ```
     alembic upgrade head && gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
     ```
   - **Plan**: Free

### C. Add Environment Variables
Click **"Advanced"** → Add these:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Paste Internal Database URL from step A |
| `SECRET_KEY` | From generate-keys.py output |
| `AGGREGATION_SERVICE_TOKEN` | From generate-keys.py output |
| `CORS_ORIGINS` | `http://localhost:5173` *(update after Vercel deploy)* |
| `LOG_LEVEL` | `INFO` |
| `LOG_FORMAT` | `json` |
| `PYTHON_VERSION` | `3.11.9` |

### D. Deploy
Click **"Create Web Service"**

⏳ Wait for deployment (~5 minutes)

📋 **Copy your backend URL**: `https://walker-app-api.onrender.com`

---

## 🎨 Step 2: Deploy Frontend (Vercel)

### A. Deploy to Vercel
1. Go to https://vercel.com/dashboard
2. Click **Add New...** → **Project**
3. Import your GitHub repository
4. Configure:
   - **Root Directory**: `AI-Now`
   - **Framework Preset**: Vite
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist/public`

### B. Add Environment Variable
1. Click **"Environment Variables"**
2. Add:
   - **Name**: `VITE_PYTHON_API_URL`
   - **Value**: `https://walker-app-api.onrender.com` *(your backend URL)*

### C. Deploy
Click **"Deploy"**

⏳ Wait for deployment (~3 minutes)

📋 **Copy your frontend URL**: `https://your-app.vercel.app`

---

## 🔗 Step 3: Connect Frontend & Backend

### Update CORS
1. Go back to **Render** dashboard
2. Open your `walker-app-api` service
3. Go to **"Environment"**
4. Update `CORS_ORIGINS` to:
   ```
   https://your-app.vercel.app,http://localhost:5173
   ```
   *(Use your actual Vercel URL)*
5. Click **"Save Changes"**

Backend will automatically redeploy (~2 minutes)

---

## ✅ Step 4: Verify Deployment

### Test Backend
Visit: `https://your-backend.onrender.com/health`

✅ Should see:
```json
{
  "status": "healthy",
  "services": {
    "api": "up",
    "database": "up"
  }
}
```

### Test Frontend
Visit: `https://your-app.vercel.app`

✅ Your app should load!

---

## 🎯 Step 5: Load Initial Content

Trigger your first content aggregation:

```bash
curl -X POST https://your-backend.onrender.com/api/v1/aggregation/trigger \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: YOUR_AGGREGATION_SERVICE_TOKEN"
```

*(Replace with your actual backend URL and token)*

---

## 🔄 Optional: Automated Content Updates

Set up scheduled aggregation with **cron-job.org**:

1. Create account: https://cron-job.org
2. Create cron job:
   - **URL**: `https://your-backend.onrender.com/api/v1/aggregation/trigger`
   - **Schedule**: Every 6 hours
   - **Method**: POST
   - **Headers**:
     - `Content-Type: application/json`
     - `X-Service-Token: YOUR_AGGREGATION_SERVICE_TOKEN`

---

## 🐛 Common Issues

### "CORS Error" in browser
→ Make sure your Vercel URL is in `CORS_ORIGINS` on Render

### "Database connection failed"
→ Verify `DATABASE_URL` is the Internal Database URL (starts with `postgresql://`)

### "502 Bad Gateway" on backend
→ Check Render logs for errors. Backend may be starting up (takes ~30s from sleep)

### Selenium errors in logs
→ Render's free tier may not support Chrome/Selenium. Options:
  - Use paid Render plan
  - Try Railway.app instead
  - Disable Selenium scrapers temporarily

### Frontend build fails
→ Check Vercel logs. Try building locally: `cd AI-Now && npm run build`

---

## 💰 Costs

**Both platforms have generous free tiers:**

- **Render**: Free (PostgreSQL expires after 90 days, then $7/month)
- **Vercel**: Free for personal projects

⚠️ **Important**: Render free databases expire in 90 days. Plan to upgrade for production.

---

## 🔄 Making Updates

After deployment, updates are automatic:

```bash
git add .
git commit -m "Update app"
git push
```

✅ Render and Vercel will auto-deploy changes from GitHub

---

## 📚 Need More Help?

- **Render Docs**: https://render.com/docs
- **Vercel Docs**: https://vercel.com/docs
- **Issues?** Check logs in each platform's dashboard

---

**🎉 Congratulations! Your app is live!**
