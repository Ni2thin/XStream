<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/drive/1_tftd9ekPDgwNfycI_w_kSuG2nXgomXm

## Run Locally

**Prerequisites** Node.js 24, Python 3.13, FFmpeg and FFprobe on your PATH.


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
   python -m pip install --require-hashes -r requirements.txt
   PORT=8000 HOST=127.0.0.1 sh start.sh
   ```
4. Run the Vite dev server  
   `npm run dev`

## Regression tests

From the repository root, install the test dependencies and run both suites:

```sh
python -m pip install --require-hashes -r backend/requirements.txt
python -m unittest discover -s backend
npm ci
npx playwright install chromium webkit
npm test
```

The browser suite uses desktop Chromium and Android and iPhone device profiles. Test downloads on physical devices before publishing mobile compatibility claims. On iOS Safari and Android Chrome, open a post with several clips, save a specific clip as MP4 and MP3, and confirm that each file opens from the browser’s downloads or the device’s file app.

## Deploying

See [DEPLOYMENT.md](./DEPLOYMENT.md) for the Render Docker setup, Vercel configuration, and release checks.
