#!/bin/bash

# Proctor360 - Linux/Ubuntu Development Launcher
# This script is the Linux equivalent of start.bat

# Color codes for better visibility
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${GREEN}  PROCTOR360 ENTERPRISE AI - Linux Launcher${NC}"
echo -e "${BLUE}======================================================${NC}"

# Get absolute path of the script directory
ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check for python3
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Warning: python3 not found. Trying 'python'...${NC}"
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

# Setup Virtual Environment if it doesn't exist
if [ ! -d "$ROOT/venv" ]; then
    echo -e "${BLUE}Setting up Python virtual environment...${NC}"
    $PYTHON_CMD -m venv "$ROOT/venv"
fi

# Use the virtual environment's python
PYTHON_CMD="$ROOT/venv/bin/python"

# Install requirements
echo -e "${BLUE}Installing Python dependencies...${NC}"
source "$ROOT/venv/bin/activate"
pip install -r "$ROOT/requirements.txt"

# 1. API Server (FastAPI) on port 8000
echo -e "${BLUE}[1/4] Starting API Server on port 8000...${NC}"
cd "$ROOT/backend/api" && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > "$ROOT/api_server.log" 2>&1 &
API_PID=$!
sleep 2

# 2. AI Engine on port 8100
echo -e "${BLUE}[2/4] Starting AI Engine on port 8100...${NC}"
cd "$ROOT/backend/ai-engine" && uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload > "$ROOT/ai_engine.log" 2>&1 &
AI_PID=$!
sleep 2

# 3. Student Portal (Vite) on port 5173
echo -e "${BLUE}[3/4] Starting Student Portal on port 5173...${NC}"
cd "$ROOT/frontend/student-portal" && npm run dev > "$ROOT/student_portal.log" 2>&1 &
STUDENT_PID=$!
sleep 2

# 4. Admin Dashboard (Vite) on port 5174
echo -e "${BLUE}[4/4] Starting Admin Dashboard on port 5174...${NC}"
cd "$ROOT/frontend/admin-dashboard" && npm run dev > "$ROOT/admin_dashboard.log" 2>&1 &
ADMIN_PID=$!

echo -e "\n${GREEN}======================================================${NC}"
echo -e "  All services launched in background!"
echo -e "${GREEN}======================================================${NC}"
echo -e "  API Server:        http://localhost:8000"
echo -e "  AI Engine:         http://localhost:8100"
echo -e "  Student Portal:    http://localhost:5173"
echo -e "  Admin Dashboard:   http://localhost:5174"
echo -e "\n${BLUE}All output is now being saved to log files!${NC}"
echo -e "To view API errors:  ${YELLOW}cat api_server.log${NC}"
echo -e "To view Frontend:    ${YELLOW}cat admin_dashboard.log${NC}"
echo -e "\n  ${YELLOW}Press Ctrl+C to stop all services...${NC}"

# Cleanup function to kill all background processes on exit
cleanup() {
    echo -e "\n${YELLOW}Stopping all services...${NC}"
    kill $API_PID $AI_PID $STUDENT_PID $ADMIN_PID 2>/dev/null
    exit
}

# Trap SIGINT (Ctrl+C)
trap cleanup SIGINT

# Keep the script running to monitor background processes
wait
