import cv2
import numpy as np

haar_face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
haar_face_alt2_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml")
haar_face_alt_tree_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt_tree.xml")
haar_profile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh

    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0

    union = (aw * ah) + (bw * bh) - inter
    if union <= 0:
        return 0.0
    return inter / union


def _center_distance(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    acx = ax + (aw / 2)
    acy = ay + (ah / 2)
    bcx = bx + (bw / 2)
    bcy = by + (bh / 2)
    return float(((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5)


def _boxes_refer_to_same_face(a, b) -> bool:
    if _iou(a, b) >= 0.22:
        return True

    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    avg_w = max(1.0, (aw + bw) / 2)
    avg_h = max(1.0, (ah + bh) / 2)
    distance = _center_distance(a, b)
    if distance <= max(avg_w, avg_h) * 0.45:
        return True

    size_ratio = max(aw * ah, bw * bh) / max(1, min(aw * ah, bw * bh))
    if size_ratio <= 2.8 and abs(ax - bx) <= avg_w * 0.5 and abs(ay - by) <= avg_h * 0.5:
        return True

    return False


def _merge_boxes(primary: list[tuple[int, int, int, int]], secondary: list[tuple[int, int, int, int]], iou_threshold: float = 0.35):
    merged = list(primary)
    for candidate in secondary:
        if any(_iou(candidate, existing) >= iou_threshold or _boxes_refer_to_same_face(candidate, existing) for existing in merged):
            continue
        merged.append(candidate)
    return merged


def _detect_haar_boxes(frame) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    frontal, frontal_alt2, frontal_tree, profile = _run_haar_passes(gray)

    flipped = cv2.flip(gray, 1)
    profile_flipped = haar_profile_cascade.detectMultiScale(flipped, scaleFactor=1.06, minNeighbors=2, minSize=(20, 20))
    fw = frame.shape[1]
    mirrored = [(int(fw - (x + w)), int(y), int(w), int(h)) for (x, y, w, h) in profile_flipped]

    detected_boxes = [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in frontal]
    detected_boxes.extend((int(x), int(y), int(w), int(h)) for (x, y, w, h) in frontal_alt2)
    detected_boxes.extend((int(x), int(y), int(w), int(h)) for (x, y, w, h) in frontal_tree)
    detected_boxes.extend((int(x), int(y), int(w), int(h)) for (x, y, w, h) in profile)
    detected_boxes.extend(mirrored)

    return _merge_boxes([], detected_boxes, iou_threshold=0.30)


def _run_haar_passes(gray):
    # Increased minNeighbors (from 2/3 to 5/6) to suppress false positives from background patterns (curtains, etc.)
    frontal_default = haar_face_cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(40, 40))
    frontal_alt2 = haar_face_alt2_cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=6, minSize=(45, 45))
    frontal_tree = haar_face_alt_tree_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(50, 50))
    profile = haar_profile_cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=6, minSize=(45, 45))
    return frontal_default, frontal_alt2, frontal_tree, profile


def _scale_up_frame(frame, min_width: int = 960):
    height, width = frame.shape[:2]
    if width >= min_width:
      return frame, 1.0

    scale = min_width / max(width, 1)
    resized = cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_CUBIC)
    return resized, scale


def _remap_boxes(boxes, scale: float):
    if scale == 1.0:
        return boxes
    remapped = []
    inv = 1.0 / scale
    for x, y, w, h in boxes:
        remapped.append((int(x * inv), int(y * inv), max(1, int(w * inv)), max(1, int(h * inv))))
    return remapped

class FaceDetector:
    def detect(self, frame):
        return len(self.detect_boxes(frame))

    def detect_boxes(self, frame):
        boxes: list[tuple[int, int, int, int]] = []
        
        # ── AUTO-ENHANCE: Boost visibility for low-light registration ──
        # Convert to LAB to normalize luminance without shifting colors
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        enhanced_frame = cv2.merge((cl, a, b))
        enhanced_frame = cv2.cvtColor(enhanced_frame, cv2.COLOR_LAB2BGR)
        
        scaled_frame, scale = _scale_up_frame(enhanced_frame)
        detected_boxes = _detect_haar_boxes(scaled_frame)
        for (x, y, w, h) in _remap_boxes(detected_boxes, scale):
            boxes.append((int(x), int(y), int(w), int(h)))
        return boxes

    def largest_face_crop(self, frame):
        faces = self.detect_boxes(frame)
        if not faces:
            return None

        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        return frame[y:y + h, x:x + w]


def face_similarity_score(frame_a, frame_b) -> float | None:
    face_a = face_detector.largest_face_crop(frame_a)
    face_b = face_detector.largest_face_crop(frame_b)
    if face_a is None or face_b is None:
        return None

    gray_a = cv2.cvtColor(face_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(face_b, cv2.COLOR_BGR2GRAY)
    gray_a = cv2.resize(gray_a, (128, 128))
    gray_b = cv2.resize(gray_b, (128, 128))

    hist_a = cv2.calcHist([gray_a], [0], None, [64], [0, 256])
    hist_b = cv2.calcHist([gray_b], [0], None, [64], [0, 256])
    cv2.normalize(hist_a, hist_a)
    cv2.normalize(hist_b, hist_b)

    corr = float(cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL))
    corr_norm = max(0.0, min(1.0, (corr + 1.0) / 2.0))

    diff = np.mean(np.abs(gray_a.astype(np.float32) - gray_b.astype(np.float32))) / 255.0
    diff_score = max(0.0, min(1.0, 1.0 - float(diff)))

    return round((0.65 * corr_norm) + (0.35 * diff_score), 4)


face_detector = FaceDetector()
