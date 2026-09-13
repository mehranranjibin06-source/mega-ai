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
