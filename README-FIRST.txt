MehranAiShabestar  -  READ ME FIRST
===================================

HOW TO RUN (Windows)  -  3 steps
--------------------------------
1. Extract this folder to  C:\   so you get   C:\mega-ai
2. Open the folder  C:\mega-ai
3. Double-click   start_vps.bat

   It will ask for a password  ->  type one and press Enter.
   (Nothing appears while you type - that is normal.)
   First run takes 3-7 minutes (it installs everything by itself).

   At the end it prints an address like:
        http://YOUR-SERVER-IP:8000
   Open that on your phone.  Username: 1   Password: the one you typed.


IF start_vps.bat DOES NOT WORK
------------------------------
Open the folder, click the address bar at the top of the window,
type   cmd   and press Enter. Then type this one line and press Enter:

        python start_vps.py

(If "python" is not found, use:   py start_vps.py   )

This does exactly the same thing without using any .bat file.


WHAT IT INSTALLS BY ITSELF
--------------------------
- 17 Python libraries + their dependencies
- a private virtual environment (.venv) - your trading bot is NOT touched
- ffmpeg (for video/audio) if missing
- opens the firewall port for you


PORT 8000 BUSY?
---------------
It automatically picks the next free port (8001, 8002, ...) and prints it.
Use the port it prints in the address, not 8000.

FIREWALL (manual, if needed) - run in CMD as Administrator:
    netsh advfirewall firewall add rule name="MehranAi" dir=in action=allow protocol=TCP localport=8000


REAL AI (optional)
------------------
Without a key it runs in demo mode. For real answers:
   open the panel -> Settings -> paste an API key -> Test.

Stop the program: close the black window (or Ctrl+C).
Run it again: double-click start_vps.bat again.

CHANGE THE PASSWORD LATER (2 steps):
  1) open the file  .env  in this folder with Notepad
  2) edit the line  MEGA_PASSWORD=...  and save. Restart the app.

FORGOT THE PASSWORD? Just delete the .env file and run start_vps.bat again.

FREE MODE (no API key needed):
  The app automatically tries free keyless services (text + image generation).
  Text answers from free services can be slow or rate-limited on busy hours.
  For fast, stable answers: open the panel -> Keys -> paste a free API key
  (Iranian gateways like AvalAI / GapGPT give free credit in ~2 minutes).

--- LOCAL AI (the brain runs on YOUR server, no API key) ---
  1) python local_ai_setup.py      installs Ollama + downloads a small model
                                   (first time only; re-run if the net drops - it resumes)
  2) python start_vps.py           the app finds the local brain automatically
  Needs ~2 GB free disk and ~1 GB RAM for the model.

--- FREE AI (no credit card, no money) ---
  Cloudflare Workers AI  -> free daily quota (Llama 70B, GPT-OSS); no card, no phone.
    1) sign up:  https://dash.cloudflare.com/sign-up            (email only)
    2) token:    https://dash.cloudflare.com/profile/api-tokens
                 Create Token -> template "Workers AI" -> Continue -> Create Token
    3) open the app terminal page and paste the token into the key box:
                 http://<YOUR-SERVER-IP>:8000/terminal     (box at the top)
                 The app saves it, finds your Account ID by itself and tests it.
  Also supported the same way: Groq (gsk_...), OpenRouter (sk-or-...), Mistral,
  AvalAI (aa-...), GapGPT (sk-...). Paste any of them in the same box.
  Paste the token and the Account ID separated by a space if you want both at once.

THREE WAYS TO GET / UPDATE THIS APP
-----------------------------------
A) ONE FILE, NO INTERNET  (best when GitHub is blocked)
   - Take the file   mega_ai_installer.bat   (about 5.8 MB)
   - Put it anywhere on the server and DOUBLE-CLICK it.
   - It contains the WHOLE app inside itself, so it needs no download at all.
   - It finds your folder by itself, keeps .env / data / workspace, and
     starts the server at the end.  About 1-2 minutes.

B) SMALL FILE, USES THE INTERNET  (27 KB)
   - Double-click   install_mehran.bat
   - It downloads the updater from 3 mirrors and installs the latest version.

C) MANUAL  (if you already have mega-ai.zip)
   - Put mega-ai.zip inside the app folder, then run:

        python update_self.py --zip mega-ai.zip --restart

RUNNING THE SERVER
------------------
   Double-click   run_server.bat    (keeps the window open and pauses on error)
   or type:       python start_vps.py

   The window MUST stay open. Closing it stops the app on your phone too.

NEVER SENT / NEVER UPLOADED
---------------------------
   .env   (your API keys)   |   data/   (your history)   |   .venv/   |   workspace/
