<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/drive/1_tftd9ekPDgwNfycI_w_kSuG2nXgomXm

## Run Locally

**Prerequisites:**  Node.js, Python 3.10+


1. Install dependencies  
   `npm install`
2. (Recommended) Create `.env.local` in the project root and set:
   ```bash
   VITE_API_BASE_URL=http://localhost:8000
   ```
   Point this to your deployed backend URL in production (e.g. Vercel/Render).
3. Start the FastAPI backend
   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8000
   ```
4. Run the Vite dev server  
   `npm run dev`

## Deploying

### Quick Setup

1. **Deploy Backend to Render:**
   - Go to https://dashboard.render.com
   - Create new Web Service from your GitHub repo
   - **Choose ONE option:**
     - **Option A (Recommended):** Set Root Directory to `backend`, then:
       - Build Command: `pip install -r requirements.txt`
       - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
     - **Option B:** Leave Root Directory empty, then:
       - Build Command: `pip install -r backend/requirements.txt`
       - Start Command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Copy your Render backend URL (e.g., `https://xstream-backend.onrender.com`)

2. **Configure Vercel:**
   - Go to your Vercel project settings
   - Add Environment Variable: `VITE_API_BASE_URL` = your Render backend URL
   - Redeploy your Vercel app

3. **Verify:**
   - Backend: Visit `https://your-backend.onrender.com/docs`
   - Frontend: Visit your Vercel URL and test video download

See [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed instructions.
