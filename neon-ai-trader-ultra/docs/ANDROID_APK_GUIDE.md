# Android APK Build Guide — NEON AI TRADER ULTRA

Because the trading engine runs on your backend server (`backend/`), this Android APK wraps the responsive Neon Command Center UI using **Capacitor** and connects securely to your backend server over HTTPS.

## Option A: Build APK Automatically in the Cloud (No Android Studio Needed)
1. Unzip `neon-ai-trader-ultra-mobile-ready.zip` and push the folder to a private GitHub repository.
2. Open the **Actions** tab on GitHub and run **Build Android APK (NEON AI TRADER ULTRA)** (it also runs automatically on push to `main`).
3. Wait ~3 minutes, then download the **`neon-ai-trader-ultra-debug-apk`** artifact (`app-debug.apk`).
4. Transfer `app-debug.apk` to your Android phone and install it.

## Option B: Build APK Locally on Windows / macOS / Linux
Requirements: Node.js 20+, Java 17, and Android Studio (Android SDK).

```bash
cd frontend
npm install
npm run android:init
cd android
./gradlew assembleDebug
```
Your APK will be created at:
`frontend/android/app/build/outputs/apk/debug/app-debug.apk`

## Connecting the APK to Your Backend Server
1. Start the backend on your server/PC (`uvicorn app.main:app --host 0.0.0.0 --port 8000` or `docker compose up -d`).
2. Add Capacitor origins to `.env`:
   `NEON_CORS_ORIGINS=http://localhost:5173,http://localhost:3000,capacitor://localhost,https://localhost,http://localhost`
3. Open the installed **NEON AI TRADER** app on your phone, tap **SERVER URL**, enter your backend URL (e.g. `https://your-vps-domain.com` or `http://192.168.1.10:8000` on local Wi-Fi), and save.
