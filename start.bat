@echo off
title VISI v2 Dashboard
cd /d C:\Users\varun\OneDrive\Desktop\trading\visi_bot
call venv\Scripts\activate
echo VISI v2 Dashboard starting...
start "" http://localhost:5001/
python dashboard\app.py
pause
