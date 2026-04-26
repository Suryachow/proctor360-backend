import cv2
import numpy as np
import logging
from fastapi import FastAPI, HTTPException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.detectors.advanced_behavior import compute_advanced_signals
from app.detectors.face_detector import face_detector, face_similarity_score
from app.schemas.analyze import AnalyzeRequest, VerifyIdentityRequest
from app.services.frame_decode import decode_base64_image

app = FastAPI(title="Proctor360 AI Engine", version="1.0.0")


def _box_iou(a, b) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0

    a_area = max(1, aw * ah)
    b_area = max(1, bw * bh)
    union = a_area + b_area - inter
    return inter / max(1, union)


def _dedupe_face_boxes(boxes: list[tuple[int, int, int, int]], iou_threshold: float = 0.45) -> list[tuple[int, int, int, int]]:
    if not boxes:
        return []

    sorted_boxes = sorted(boxes, key=lambda x: x[2] * x[3], reverse=True)
    kept: list[tuple[int, int, int, int]] = []
    for box in sorted_boxes:
        if all(_box_iou(box, existing) < iou_threshold for existing in kept):
            kept.append(box)
    return kept


def _contains_phone_like_object(frame, pose_proxy: dict | None = None) -> bool:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    frame_area = frame.shape[0] * frame.shape[1]
    profile_ratio = float((pose_proxy or {}).get("profile_ratio") or 1.0)
    side_profile = profile_ratio < 0.78

    # 1. HOUGH LINE DETECTION (Parallel Edges): Catch the phone's metallic/plastic bezel
    edges = cv2.Canny(blurred, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, minLineLength=40, maxLineGap=10)

    parallel_count = 0
    if lines is not None:
        # Check only a small candidate set to keep per-frame cost bounded.
        candidate_lines = lines[:18]
        for i in range(len(candidate_lines)):
            for j in range(i + 1, len(candidate_lines)):
                l1 = candidate_lines[i][0]
                l2 = candidate_lines[j][0]
                # Slopes
                s1 = np.arctan2(l1[3]-l1[1], l1[2]-l1[0])
                s2 = np.arctan2(l2[3]-l2[1], l2[2]-l2[0])
                if abs(s1 - s2) < 0.1: # Parallel
                    dist = np.sqrt((l1[0]-l2[0])**2 + (l1[1]-l2[1])**2)
                    if 30 < dist < 150: # Phone-like width in pixels
                        parallel_count += 1
                        if parallel_count >= 8:
                            break
            if parallel_count >= 8:
                break
    parallel_signal = parallel_count >= 2

    # 2. ENHANCED SCREEN DETECTION: Multi-threshold for various brightness levels
    bright_hits = 0
    for thresh_val in [140, 170, 200, 225]:
        _, bright_thresh = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        bright_thresh = cv2.morphologyEx(bright_thresh, cv2.MORPH_CLOSE, kernel)
        
        bright_contours, _ = cv2.findContours(bright_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for bc in bright_contours:
            area = cv2.contourArea(bc)
            if frame_area * 0.001 < area < frame_area * 0.3: 
                peri = cv2.arcLength(bc, True)
                approx = cv2.approxPolyDP(bc, 0.04 * peri, True)
                if len(approx) >= 4:
                    x, y, w, h = cv2.boundingRect(bc)
                    aspect_ratio = max(w, h) / max(min(w, h), 1)
                    if 1.0 <= aspect_ratio <= 4.0:
                        bright_hits += 1
    # Require more evidence from bright regions to avoid monitor/glare false positives.
    bright_signal = bright_hits >= (5 if side_profile else 4)

    # 3. RECTANGLE-IN-RECTANGLE SCAN (Phone with Screen On)
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    nested_signal = False
    contour_candidates = sorted(contours, key=cv2.contourArea, reverse=True)[:24]
    for i, cnt in enumerate(contour_candidates):
        area = cv2.contourArea(cnt)
        if frame_area * 0.005 < area < frame_area * 0.4:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
            if len(approx) == 4: # Outer Rect
                # Check for inner rects
                child_count = 0
                for j, cnt2 in enumerate(contour_candidates):
                    if i == j: continue
                    if cv2.contourArea(cnt2) > area * 0.5: continue
                    # Simple inclusion check (bounding box)
                    x, y, w, h = cv2.boundingRect(cnt)
                    x2, y2, w2, h2 = cv2.boundingRect(cnt2)
                    if x < x2 and y < y2 and (x+w) > (x2+w2) and (y+h) > (y2+h2):
                        child_count += 1
                if child_count >= 1: # A screen/button inside a frame
                    nested_signal = True
                    break
        if nested_signal:
            break

    # Require at least two independent signals to suppress false positives.
    signal_score = int(parallel_signal) + int(bright_signal) + int(nested_signal)
    if signal_score >= (3 if side_profile else 2):
        return True

    # Allow one strong geometry signal only when reinforced by at least one bright hit.
    if parallel_count >= (6 if side_profile else 5) and bright_hits >= (3 if side_profile else 2):
        return True

    # Bright, persistent rectangular patches are commonly phone screens.
    if bright_hits >= (6 if side_profile else 5):
        return True

    # Nested rectangular layout with any supporting edge evidence is suspicious.
    if nested_signal and (parallel_count >= 1 or bright_hits >= 1):
        return True

    return False


def _contains_id_card_like_object(frame) -> bool:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = frame.shape[0] * frame.shape[1]

    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.04 * peri, True)
        if len(approx) != 4:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < frame_area * 0.04 or area > frame_area * 0.8:
            continue

        ratio = max(w, h) / max(min(w, h), 1)
        if 1.2 <= ratio <= 2.2: # ID cards are ~1.58, but perspective varies
            return True
    return False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(payload: AnalyzeRequest):
    frame = decode_base64_image(payload.image_base64)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image payload")

    face_boxes = _dedupe_face_boxes(face_detector.detect_boxes(frame))
    face_count = len(face_boxes)
    events = []

    primary_face_box = None
    pose_proxy = None
    if face_count > 0:
        x, y, w, h = max(face_boxes, key=lambda b: b[2] * b[3])
        frame_h, frame_w, _ = frame.shape
        center_x = (x + (w / 2)) / max(1, frame_w)
        center_y = (y + (h / 2)) / max(1, frame_h)
        profile_ratio = w / max(h, 1)
        primary_face_box = {
            "x": float(x),
            "y": float(y),
            "w": float(w),
            "h": float(h),
            "center_x": float(center_x),
            "center_y": float(center_y),
            "profile_ratio": float(profile_ratio),
        }
        pose_proxy = {
            "center_x": float(center_x),
            "center_y": float(center_y),
            "profile_ratio": float(profile_ratio),
        }

    if face_count == 0:
        events.append(
            {
                "event_type": "no_face",
                "detail": "No student face detected",
                "confidence": 0.55,
                "rationale": "The face mesh pipeline failed to localize any facial landmarks in the current frame.",
                "explainability": "Face detector confidence below threshold for entire frame",
            }
        )
    elif face_count > 1:
        frame_h, frame_w, _ = frame.shape
        frame_area = max(1, frame_h * frame_w)
        face_areas = [max(1, w * h) for (_, _, w, h) in face_boxes]
        largest_area = max(face_areas) if face_areas else 1
        # Suppress ghost detections: require secondary faces to be at least 60% as large as the primary face
        # and at least 2% of the total frame area.
        significant_faces = [a for a in face_areas if a >= frame_area * 0.02 and a >= largest_area * 0.60]

        if len(significant_faces) >= 2:
            effective_count = len(significant_faces)
            events.append(
                {
                    "event_type": "multiple_faces",
                    "detail": "More than one face detected",
                    "confidence": 0.85,
                    "rationale": f"The neural detector identified {effective_count} distinct facial signatures within the active monitoring zone.",
                    "explainability": f"Detected {effective_count} significant face bounding boxes in single frame",
                }
            )

    if _contains_phone_like_object(frame, pose_proxy):
        events.append(
            {
                "event_type": "phone_detected",
                "detail": "Phone-like object detected in camera frame",
                "confidence": 0.95,
                "rationale": "High-confidence geometric signature of a mobile device (parallel edges + screen-like glow) detected.",
                "explainability": "Detected rectangular object with phone-like aspect ratio and parallel edge alignment.",
            }
        )

    identity_similarity = None
    if payload.reference_face_image_base64 and face_count == 1:
        reference_frame = decode_base64_image(payload.reference_face_image_base64)
        if reference_frame is not None:
            identity_similarity = face_similarity_score(frame, reference_frame)
            if identity_similarity is not None and identity_similarity < 0.55:
                events.append(
                    {
                        "event_type": "unknown_person_detected",
                        "detail": "Detected face does not match registered student",
                        "score": 0.55,
                        "explainability": f"Face similarity score {identity_similarity:.2f} is below threshold 0.55",
                    }
                )

    advanced = []
    if payload.include_advanced:
        advanced = compute_advanced_signals(frame, face_count, face_boxes)
        for item in advanced:
            if item.get("confidence", 0) > 0.3:
                events.append(
                    {
                        "event_type": item["event_type"],
                        "detail": item["detail"],
                        "confidence": item.get("confidence", 0.5),
                        "rationale": item.get("rationale", "Advanced behavioral heuristic triggered."),
                        "explainability": item.get("explainability", "Signal threshold exceeded"),
                    }
                )

    suspicious_score = min(1.0, 0.25 * len(events) + (0.2 if face_count > 1 else 0.0))

    return {
        "events": events,
        "metrics": {
            "face_count": face_count,
            "suspicious_score": suspicious_score,
            "identity_similarity": identity_similarity,
            "advanced_signals": advanced,
            "primary_face_box": primary_face_box,
            "pose_proxy": pose_proxy,
        },
    }


@app.post("/verify-identity")
def verify_identity(payload: VerifyIdentityRequest):
    registered_frame = decode_base64_image(payload.registered_face_image_base64)
    live_frame = decode_base64_image(payload.live_image_base64)
    id_card_frame = decode_base64_image(payload.id_card_image_base64)

    if registered_frame is None or live_frame is None or id_card_frame is None:
        raise HTTPException(status_code=400, detail="Invalid identity image payload")

    similarity = face_similarity_score(live_frame, registered_frame)
    if similarity is None:
        return {
            "face_match": False,
            "similarity": 0.0,
            "id_card_detected": _contains_id_card_like_object(id_card_frame),
            "reason": "Face not clearly detected in live or registered image",
        }

    id_card_detected = _contains_id_card_like_object(id_card_frame)
    face_match = similarity >= 0.55

    return {
        "face_match": face_match,
        "similarity": round(float(similarity), 4),
        "id_card_detected": id_card_detected,
        "reason": "ok" if face_match and id_card_detected else "Identity verification failed",
    }
