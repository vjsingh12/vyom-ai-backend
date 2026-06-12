# Vyom AI — Backend Deployment Guide
## Deploy your Swiss Ephemeris engine on Replit (Free, 10 minutes)

---

### STEP 1 — Create a free Replit account
1. Go to **replit.com**
2. Click "Sign Up" — use Google or email
3. It's completely free

---

### STEP 2 — Create a new Repl
1. Click the **"+ Create Repl"** button
2. Select **"Python"** as the template
3. Name it: **vyom-ai-backend**
4. Click **"Create Repl"**

---

### STEP 3 — Upload the files
You need to upload two files into Replit:

**File 1: main.py**
- In Replit, click the Files panel on the left
- Delete the existing `main.py` content
- Copy and paste the entire contents of `main.py` from this folder

**File 2: requirements.txt**
- Click the "+" icon in the Files panel
- Create a new file called `requirements.txt`
- Copy and paste the contents of `requirements.txt` from this folder

---

### STEP 4 — Install dependencies
In the Replit Shell (bottom panel), type:
```
pip install -r requirements.txt
```
Wait for everything to install (about 2 minutes).

---

### STEP 5 — Run the server
Click the big green **"Run"** button at the top.

You should see:
```
* Running on http://0.0.0.0:8080
Vyom AI engine is running
```

---

### STEP 6 — Get your API URL
Replit gives you a public URL that looks like:
```
https://vyom-ai-backend.YOURNAME.repl.co
```

Copy this URL and send it to Claude.
Claude will connect your demo page to this live engine.

---

### STEP 7 — Test it works
In your browser, visit:
```
https://vyom-ai-backend.YOURNAME.repl.co/health
```

You should see:
```json
{
  "status": "Vyom AI engine is running",
  "engine": "Swiss Ephemeris + Lahiri Ayanamsa"
}
```

If you see this — your engine is live. Send the URL to Claude!

---

### Troubleshooting

**"Module not found" error:**
Run `pip install -r requirements.txt` again in the Shell.

**"Port already in use" error:**
Stop the Repl and click Run again.

**Geocoding not working:**
The engine will fall back to Bhawanigarh coordinates automatically.

---

### What this engine does
- Takes birth date, time, and place
- Calculates exact lat/lng of birth place
- Converts to UTC with proper timezone
- Computes Julian Day Number
- Applies Lahiri Ayanamsa correction (~24°)
- Uses Swiss Ephemeris for planetary positions
- Returns: Lagna, Moon Rashi, Nakshatra, Mahadasha, Antardasha, all 9 planet positions
