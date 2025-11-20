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
2. Create `.env.local` in the project root and set:
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

1. Push the repo to GitHub (already at https://github.com/Ni2thin/XStream.git).
2. On Vercel, create a project from that repo.
3. Add an Environment Variable `VITE_API_BASE_URL` with your public backend URL.
4. Ensure your backend’s CORS list includes `https://xstream-five.vercel.app` (already configured in `backend/main.py`).
