# Proctor360 Enterprise Proctoring Suite

Production-style online proctoring platform with student exam portal, live admin dashboard, rule-based violation engine, and AI-backed detections.

## Features by maturity level

### Level 1 (MVP)
- Webcam stream checks and snapshots
- Tab-switch detection
- Fullscreen enforcement
- Copy/paste restrictions
- Auto-submit on severe or repeated violation

### Level 2 (Intelligent)
- Face presence and multi-face detection
- Person/phone object detection (YOLO-ready)
- Audio anomaly spike detection

### Level 3 (Advanced AI)
- Eye gaze estimation (placeholder hook)
- Head pose trend analysis (placeholder hook)
- Suspicious behavior scoring and auto-flagging

## Monorepo layout
- `frontend/student-portal`: React + Vite student exam interface
- `frontend/admin-dashboard`: React + Vite live invigilator console
- `backend/api`: FastAPI orchestration, auth, violations, websockets
- `backend/ai-engine`: FastAPI AI service with OpenCV/MediaPipe stubs
- `infra`: deployment assets

## Quick start
1. Copy env template:
   - `copy .env.example .env`
2. Run full stack:
   - `docker compose up --build`
3. Open apps:
   - Student: `http://localhost:5173`
   - Admin: `http://localhost:5174`
   - API docs: `http://localhost:8000/docs`

## Security and privacy controls
- Consent gate before exam starts
- Event-only minimal logging by default
- Device fingerprint binding at login
- Risk-scored violation engine
- Configurable retention for snapshots/recordings

## Notes
- Browser lock-down can deter but cannot fully prevent cheating.
- For regulated environments, add explicit legal consent text and policy links.
