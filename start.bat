@echo off
title Proctor360 - Local Development Stack
color 0A

echo.
echo  ======================================================
echo   PROCTOR360 ENTERPRISE AI - Local Development Launcher
echo  ======================================================
echo.

:: Set the project root to where this bat file is
set "ROOT=%~dp0"

:: ─── 1. API Server (FastAPI) on port 8000 ───
echo  [1/4] Starting API Server on port 8000...
start "Proctor360 API" cmd /k "cd /d %ROOT%backend\api && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 2 /nobreak >nul

:: ─── 2. AI Engine on port 8100 ───
echo  [2/4] Starting AI Engine on port 8100...
start "Proctor360 AI Engine" cmd /k "cd /d %ROOT%backend\ai-engine && python -m uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload"
timeout /t 2 /nobreak >nul

:: ─── 3. Student Portal (Vite) on port 5173 ───
echo  [3/4] Starting Student Portal on port 5173...
start "Proctor360 Student Portal" cmd /k "cd /d %ROOT%frontend\student-portal && npm run dev"
timeout /t 2 /nobreak >nul

:: ─── 4. Admin Dashboard (Vite) on port 5174 ───
echo  [4/4] Starting Admin Dashboard on port 5174...
start "Proctor360 Admin Dashboard" cmd /k "cd /d %ROOT%frontend\admin-dashboard && npm run dev"

echo.
echo  ======================================================
echo   All services launched!
echo  ======================================================
echo.
echo   API Server:        http://localhost:8000
echo   AI Engine:         http://localhost:8100
echo   Student Portal:    http://localhost:5173
echo   Admin Dashboard:   http://localhost:5174
echo.
echo   Press any key to close this launcher window...
echo   (Service windows will keep running)
echo.
pause >nul
