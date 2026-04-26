import cv2
import numpy as np
try:
    import mediapipe as mp
    _HAS_MEDIAPIPE = True
except Exception:
    mp = None
    _HAS_MEDIAPIPE = False

if _HAS_MEDIAPIPE:
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.4
    )
else:
    face_mesh = None

def compute_advanced_signals(frame, face_count: int, face_boxes: list[tuple[int, int, int, int]] | None = None) -> list[dict]:
    events: list[dict] = []

    if face_count == 0:
        return events

    # Fallback behavior signal when mesh landmarks are unavailable or noisy.
    if face_count == 1 and face_boxes:
        x, y, w, h = max(face_boxes, key=lambda b: b[2] * b[3])
        img_h, img_w, _ = frame.shape
        face_cx = (x + (w / 2)) / max(1, img_w)
        face_cy = (y + (h / 2)) / max(1, img_h)
        dx = abs(face_cx - 0.5)
        dy = abs(face_cy - 0.5)
        profile_ratio = w / max(h, 1)

        # Side profile detection: a strongly narrow face box usually means the
        # candidate is turning away from the camera.
        if profile_ratio < 0.65:
            conf = min(0.96, 0.58 + (0.65 - profile_ratio) * 1.6)
            events.append({
                "event_type": "looking_away",
                "detail": "Side-profile head pose detected",
                "confidence": conf,
                "rationale": "Face bounding geometry indicates pronounced side turn away from screen center.",
                "explainability": f"Face aspect ratio {profile_ratio:.2f} below frontal threshold 0.65",
            })

        if dx > 0.22 or dy > 0.18:
            conf = min(0.92, 0.52 + (dx * 1.2) + (dy * 1.2))
            events.append({
                "event_type": "looking_away",
                "detail": "Face moved significantly off-center (possible look-away)",
                "confidence": conf,
                "rationale": "Face bounding box center moved beyond on-screen attention zone.",
                "explainability": f"Face center deviation dx={dx:.2f}, dy={dy:.2f} exceeds attention bounds",
            })

    if not _HAS_MEDIAPIPE or face_mesh is None:
        return events

    # Convert the BGR image to RGB before processing.
    results = face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    if not results.multi_face_landmarks:
        return events

    for face_landmarks in results.multi_face_landmarks:
        landmarks = face_landmarks.landmark
        img_h, img_w, _ = frame.shape
        
        # 1. Head Pose Estimation (Simple heuristic)
        # Using Nose Tip (1), Chin (152), Left Eye Left Corner (33), Right Eye Right Corner (263)
        nose_tip = landmarks[1]
        right_eye = landmarks[33]
        left_eye = landmarks[263]
        
        # Calculate horizontal deviation (Yaw)
        face_center_x = (right_eye.x + left_eye.x) / 2
        yaw_deviation = abs(nose_tip.x - face_center_x) / (abs(right_eye.x - left_eye.x) + 1e-6)
        
        # Calculate vertical deviation (Pitch)
        # Using forehead (10) and chin (152)
        forehead = landmarks[10]
        chin = landmarks[152]
        face_center_y = (forehead.y + chin.y) / 2
        pitch_deviation = abs(nose_tip.y - face_center_y) / (abs(forehead.y - chin.y) + 1e-6)

        # Thresholds for looking away
        if yaw_deviation > 0.08: # Relaxed side turn threshold (was 0.05)
            events.append({
                "event_type": "gaze_deviation",
                "detail": "Head turned sideways (Looking away)",
                "confidence": min(1.0, 0.52 + yaw_deviation * 2),
                "rationale": f"Candidate's head rotated {yaw_deviation:.2f} normalized units horizontally, deviating from screen center.",
                "explainability": f"Yaw deviation {yaw_deviation:.2f} exceeds threshold 0.08"
            })
        elif pitch_deviation > 0.18: # Relaxed vertical threshold (was 0.12)
             events.append({
                "event_type": "gaze_deviation",
                "detail": "Head tilted significantly (Looking up/down)",
                "confidence": min(1.0, 0.52 + pitch_deviation * 2),
                "rationale": "Candidate's head posture shows vertical tilt away from the monitoring area.",
                "explainability": f"Pitch deviation {pitch_deviation:.2f} exceeds threshold 0.18"
            })

        # 2. Iris Tracking (Precise Eye Gaze)
        l_iris = landmarks[468]
        l_inner = landmarks[133]
        l_outer = landmarks[33]
        
        if abs(l_outer.x - l_inner.x) > 0:
            iris_pos = (l_iris.x - l_inner.x) / (l_outer.x - l_inner.x)
            if iris_pos < 0.38 or iris_pos > 0.62: # Relaxed margin (was 0.44-0.56)
                events.append({
                    "event_type": "looking_away",
                    "detail": "Eyes looking away from screen center",
                    "confidence": 0.92,
                    "rationale": f"Ocular tracking indicates the iris is positioned at the extreme edge ({iris_pos:.2f}) of the eye socket.",
                    "explainability": f"Iris centered position {iris_pos:.2f} indicates off-center gaze"
                })

    return events
