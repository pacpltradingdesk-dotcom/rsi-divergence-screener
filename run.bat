@echo off
title RSI Divergence Screener
start "" "http://127.0.0.1:5000"
python "%~dp0app.py"
pause
