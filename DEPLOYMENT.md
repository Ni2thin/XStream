# Deployment Guide

This guide will help you deploy XStream to production.

## Architecture

- **Frontend**: Deployed on Vercel (https://xstream-v1.vercel.app)
- **Backend**: Deploy to Render (or similar service)

## Step 1: Deploy Backend to Render

### Prerequisites
- GitHub account
- Render account (free tier available)

### Steps:

1. **Push your code to GitHub** (if not already done)
   ```bash
   git add .
   git commit -m "Prepare for deployment"
   git push origin main
   ```

2. **Create a new Web Service on Render**
   - Go to https://dashboard.render.com
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Select the repository: `Ni2thin/XStream` (or your repo)

3. **Configure the service:**
   - **Name**: `xstream-backend` (or any name you prefer)
   - **Environment**: `Python 3`
   
   **IMPORTANT: Choose ONE of these options:**
   
   **Option A (Recommended): Set Root Directory**
   - **Root Directory**: `backend`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   
   **Option B: Leave Root Directory Empty**
   - **Root Directory**: (leave empty)
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`

4. **Environment Variables** (optional):
   - `PYTHON_VERSION`: `3.10.0` (or latest 3.10.x)

5. **Click "Create Web Service"**

6. **Wait for deployment** - Render will:
   - Install dependencies
   - Build your app
   - Start the server
   - Give you a URL like: `https://xstream-backend.onrender.com`

7. **Copy your backend URL** - You'll need this for the next step!

## Step 2: Configure Vercel Environment Variables

1. **Go to your Vercel project**
   - Visit https://vercel.com/dashboard
   - Select your `xstream-downloader` project

2. **Go to Settings → Environment Variables**

3. **Add a new variable:**
   - **Name**: `VITE_API_BASE_URL`
   - **Value**: Your Render backend URL (e.g., `https://xstream-backend.onrender.com`)
   - **Environment**: Production, Preview, Development (select all)

4. **Redeploy your Vercel app**
   - Go to Deployments tab
   - Click the three dots on the latest deployment
   - Select "Redeploy"

## Step 3: Verify CORS Configuration

The backend already includes your Vercel domain in CORS:
- `https://xstream-v1.vercel.app`
- `https://xstream-five.vercel.app`

If you have a different domain, update `backend/main.py`:
```python
origins = [
    # ... existing origins ...
    "https://your-domain.vercel.app",  # Add your domain
]
```

## Step 4: Test Your Deployment

1. **Test the backend:**
   - Visit: `https://your-backend-url.onrender.com/docs`
   - You should see the FastAPI Swagger UI

2. **Test the frontend:**
   - Visit: https://xstream-v1.vercel.app
   - Open browser console (F12)
   - Try downloading a video
   - Check that API calls go to your Render backend (not localhost)

## Troubleshooting

### Backend not responding
- Check Render logs: Dashboard → Your Service → Logs
- Verify `yt-dlp` is installed (it's in requirements.txt)
- Check that the start command is correct

### CORS errors
- Verify your Vercel domain is in the `origins` list in `backend/main.py`
- Make sure `VITE_API_BASE_URL` is set correctly in Vercel
- Check browser console for specific CORS error messages

### Frontend still using localhost
- Verify `VITE_API_BASE_URL` is set in Vercel
- Redeploy after setting the environment variable
- Clear browser cache

## Alternative: Deploy Backend to Other Services

### Railway
- Similar to Render
- Use the same `Procfile` or configure in Railway dashboard

### Fly.io
- Create `fly.toml` configuration
- Use: `flyctl deploy`

### Heroku
- Use the `Procfile` provided
- Set `VITE_API_BASE_URL` in Heroku config vars

## Notes

- **Free tier limitations**: Render free tier spins down after 15 minutes of inactivity. First request may be slow (30-60 seconds cold start).
- **yt-dlp**: Already included in `requirements.txt` as a Python package, so it will be installed automatically.
- **Port**: Render provides `$PORT` environment variable automatically.

## Render Free Tier Spin-Down (Normal Behavior)

**This is expected!** Render's free tier automatically shuts down services after 15 minutes of inactivity to save resources. You'll see logs like:
```
INFO: Shutting down
INFO: Waiting for application shutdown.
INFO: Application shutdown complete.
```

### Solutions:

**Option 1: Use a Free Keep-Alive Service (Recommended for Free Tier)**
- Sign up for a free service like [UptimeRobot](https://uptimerobot.com) or [cron-job.org](https://cron-job.org)
- Set up a monitor/HTTP request to ping your backend every 10-14 minutes
- Use your health check endpoint: `https://your-backend.onrender.com/health`
- This keeps your service alive without upgrading

**Option 2: Upgrade to Paid Plan**
- Render paid plans ($7/month+) keep services running 24/7
- No spin-down, instant responses

**Option 3: Accept the Cold Start**
- Service automatically restarts on first request
- Takes 30-60 seconds for first request after spin-down
- Subsequent requests are fast until next spin-down

### Health Check Endpoint

Your backend now includes a health check endpoint at `/health` that returns:
```json
{"status": "ok", "service": "xstream-backend"}
```

You can use this for:
- Render health checks (already configured in `render.yaml`)
- External monitoring services
- Keep-alive pings

