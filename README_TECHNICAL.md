# Proctor360 Enterprise: Technical Architecture & Feature Guide

Proctor360 is a high-fidelity, enterprise-grade AI examination proctoring system. It uses a distributed microservices architecture to provide real-time behavioral analysis, identity verification, and multi-layered anti-cheating measures.

---

## 🏗️ 1. System Architecture

The application is composed of five specialized services orchestrated via **Docker Compose**:

### 🛰️ Core Services
1.  **API Gateway (Backend)**: Python/FastAPI. The central brain that manages exam logic, student sessions, database persistence, and orchestration of other services.
2.  **AI Engine**: Python/FastAPI + OpenCV + MediaPipe. A low-latency computer vision service that processes video frames and returns structured behavioral signals.
3.  **Student Portal**: React + Vite. The candidate interface for taking exams, providing biometric data, and receiving real-time warnings.
4.  **Admin Dashboard**: React + Vite. The management interface for creating exams, reviewing proctoring reports, and managing student compliance.
5.  **Infrastructure**: PostgreSQL (Main Storage), Redis (Caching/Messaging).

---

## 🧠 2. The AI Proctoring Engine (How Detection Works)

The AI Engine is the core innovation. It uses a **multi-stage neural and geometric pipeline** to analyze student behavior:

### 🎭 Face & Identity Analysis
*   **MediaPipe Face Detection**: Uses a high-performance neural model to detect up to 5 faces simultaneously.
*   **Haar & Histogram Comparison**: When a student starts an exam, their live face is compared against their registered profile using a weighted histogram (65%) and pixel-diff (35%) algorithm to ensure zero-impersonation.
*   **Identity Gatekeeper**: Rejects the student before the exam starts if the biometric match is below 0.45 confidence.

### 👓 Advanced Behavioral Signals (MediaPipe Face Mesh)
*   **3D Head Pose Estimation**: Tracks **Yaw** (side-turn) and **Pitch** (up/down). If a student turns their head significantly (e.g., looking at side-notes), a `gaze_deviation` alert is triggered.
*   **Precise Iris Tracking**: Monitors the position of the iris relative to the eye corners. This detects "shifty eyes" or looking away from the screen even when the head is still.
*   **Liveliness Detection**: Analyzes facial landmarks to ensure a real person is present, not a photo or video loop.

### 📱 Mobile Phone & Object Detection
*   **Hough Parallel Line Transform**: A geometric algorithm that hunts for the specific parallel edges of smartphone bezels.
*   **Rectangle-in-Rectangle Scan**: Detects the unique nested shape of a phone screen inside a phone body.
*   **Multi-Brightness Glow Scan**: Looks for electronic screen luminance peaks at multiple exposure levels (to catch phones even in bright rooms).
*   **Non-Skin Filtering**: Uses HSV color space analysis to distinguish between a device and the student's hand/arm, reducing false alarms.

---

## 🔄 3. End-to-End Data Flow

1.  **Frame Capture**: The Student Portal captures a webcam frame every ~1-2 seconds.
2.  **Base64 Transmission**: The frame is encoded to Base64 and sent to the **API Gateway** via a `/frame` endpoint.
3.  **AI Orchestration**: The API Gateway forwards the frame to the **AI Engine**.
4.  **Signal Generation**: The AI Engine processes the frame and returns a list of events (e.g., `phone_detected`, `no_face`, `gaze_deviation`).
5.  **Violation Engine**: The API Gateway receives these signals and:
    - Calculates a **Risk Delta** (e.g., a phone might add 0.5 to the risk score).
    - Logs a **Violation** in the database with high-resolution details.
    - Updates the session's aggregate **Risk Score**.
6.  **Real-Time Reaction**: If the Risk Score exceeds a critical threshold, the API instructs the frontend to **Auto-Submit** the exam and lock the student out.

---

## 🚀 4. Key Enterprise Features

| Feature | Description |
| :--- | :--- |
| **3-Strike Policy** | Customizable violation thresholds that automatically terminate sessions for repeat offenders. |
| **Dynamic Workflows** | Rules-based engine that decides whether to warn a student, notify an admin, or end the exam. |
| **Rich PDF Reports** | Generates detailed integrity reports for every session, including time-stamped violation logs and risk heatmaps. |
| **Tab Switch Detection** | Browser-level event tracking to catch students opening other windows or searching for answers. |
| **Enterprise Multi-Tenancy** | Support for multiple organizations (slug-based) within the same infrastructure. |
| **Device Fingerprinting** | Tracks the hardware profile to detect if multiple students are sharing the same device. |

---

## 🔒 5. Integrity & Compliance
*   **OTP Security**: Exams are protected by hashed OTP codes.
*   **Anti-Bypass**: The proctoring system runs as a mandatory overlay; any attempt to disable it is logged as a critical violation.
*   **JWT Security**: All API endpoints are secured with OAuth2/JWT Bearer tokens.

> [!NOTE]
> All AI detections are processed locally on your server/Docker network. No biometric data is sent to external cloud providers, ensuring 100% GDPR/Data Privacy compliance.
