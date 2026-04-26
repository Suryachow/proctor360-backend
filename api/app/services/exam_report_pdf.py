import math
import base64
import io
from collections import Counter
from datetime import datetime
from typing import Any

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.models.entities import Exam, ExamAnswer, EvidenceFrame, ExamQuestion, ExamSession, Question, Violation
from app.services.exam_report import build_exam_report

# ─── Indigo & Teal Design System ──────────────────────────────────────────────
# Primary (Indigo family)
C_PRIMARY       = (30,  41,  82)   # Deep Indigo — main text, headers
C_PRIMARY_MID   = (71,  85, 132)   # Mid Indigo  — sub-labels
C_PRIMARY_LIGHT = (226, 230, 245)  # Pale Indigo  — borders, rules

# Accent (Teal family)
C_ACCENT        = (13, 148, 136)   # Teal-600 — active, scores, accents
C_ACCENT_LIGHT  = (234, 246, 245)  # Teal-50  — soft bg highlight
C_ACCENT_DARK   = (15, 118, 110)   # Teal-700 — dark text on light teal

# Neutral
C_WHITE         = (255, 255, 255)
C_BG            = (251, 252, 254)  # Warm white page tint
C_BG_ALT        = (246, 248, 252)  # Light grey alternating row

# Semantic
C_OK            = (20, 150, 120)   # Success teal
C_WARN          = (130, 100, 30)   # Muted amber
C_FAIL          = (160, 40, 40)    # Soft red

PAGE_W, PAGE_H = 210, 297
MARGIN = 14
BODY_W = PAGE_W - MARGIN * 2

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _safe(v: Any) -> str:
    """Ensure text is latin-1 compatible for FPDF."""
    return str(v or "").encode("latin-1", "replace").decode("latin-1")

def _pdf_bytes(pdf: FPDF) -> bytes:
    """Return PDF as raw bytes."""
    raw = pdf.output(dest="S")
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else raw.encode("latin-1")

def _write(pdf: FPDF, text: Any, h: float = 4.5) -> None:
    pdf.set_x(MARGIN)
    pdf.multi_cell(BODY_W, h, _safe(text), new_x="LMARGIN", new_y="NEXT")

def _gap(pdf: FPDF, n: float = 3.5) -> None:
    pdf.ln(n)

def _space_check(pdf: FPDF, needed: float) -> None:
    """Add a new page if current space is insufficient."""
    if pdf.get_y() + needed > (pdf.h - 18):
        pdf.add_page()
        pdf.set_fill_color(*C_BG)
        pdf.rect(0, 0, PAGE_W, PAGE_H, style="F")
        _gap(pdf, 2)

# ─── Sections ─────────────────────────────────────────────────────────────────
def _section(pdf: FPDF, title: str) -> None:
    _space_check(pdf, 15)
    y = pdf.get_y()
    # Left accent bar
    pdf.set_fill_color(*C_ACCENT)
    pdf.rect(MARGIN, y, 2.5, 6.5, style="F")
    # Title
    pdf.set_xy(MARGIN + 5, y + 1.2)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*C_PRIMARY)
    pdf.cell(0, 4, _safe(title.upper()), new_x="LMARGIN", new_y="NEXT")
    # Thin rule
    pdf.set_draw_color(*C_PRIMARY_LIGHT)
    pdf.set_line_width(0.2)
    pdf.line(MARGIN, pdf.get_y() + 1, MARGIN + BODY_W, pdf.get_y() + 1)
    _gap(pdf, 4.5)

def _kv(pdf: FPDF, rows: list[tuple[str, str]], col_w: float = 88) -> None:
    _space_check(pdf, (len(rows) // 2 + 1) * 7.5)
    x0, y0, row_h = MARGIN, pdf.get_y(), 7.5
    for idx, (label, value) in enumerate(rows):
        r, c = idx // 2, idx % 2
        x, y = x0 + c * (col_w + 6), y0 + r * row_h
        if r % 2 == 0:
            pdf.set_fill_color(*C_BG_ALT)
            pdf.rect(x, y, col_w, row_h, style="F")
        pdf.set_xy(x + 3, y + 1.8)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*C_PRIMARY_MID)
        pdf.cell(35, 4, _safe(label))
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*C_PRIMARY)
        pdf.cell(col_w - 38, 4, _safe(value))
    pdf.set_y(y0 + ((len(rows) + 1) // 2) * row_h + 4)

# ─── Data Viz ────────────────────────────────────────────────────────────────
def _bar_chart(pdf: FPDF, title: str, items: list[tuple[str, float]]) -> None:
    _space_check(pdf, 65)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*C_PRIMARY_MID)
    _write(pdf, title, 5)
    _gap(pdf, 1.5)
    label_w, bar_w, bar_h, x = 50, 108, 4.5, MARGIN + 2
    for name, value in items[:7]:
        v = max(0.0, min(100.0, float(value)))
        y = pdf.get_y()
        pdf.set_xy(x, y)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*C_PRIMARY)
        pdf.cell(label_w, bar_h + 2, _safe(name)[:28])
        # Track
        pdf.set_fill_color(*C_PRIMARY_LIGHT)
        pdf.rect(x + label_w, y + 1.5, bar_w, bar_h, style="F")
        # Fill
        fill_color = C_ACCENT if v >= 70 else (C_PRIMARY_MID if v >= 45 else C_FAIL)
        pdf.set_fill_color(*fill_color)
        pdf.rect(x + label_w, y + 1.5, bar_w * (v / 100.0), bar_h, style="F")
        # % text
        pdf.set_xy(x + label_w + bar_w + 3, y)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*C_PRIMARY_MID)
        pdf.cell(14, bar_h + 2, f"{v:.0f}%")
        pdf.ln(bar_h + 4)
    _gap(pdf, 2)

def _pie_sector(pdf, cx, cy, r, s, e):
    if e <= s: return
    pts = [(cx, cy)]
    a = s
    while a <= e:
        rad = math.radians(a)
        pts.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))
        a += 5
    rad = math.radians(e)
    pts.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))
    pdf.polygon(pts, style="F")

def _pie_chart(pdf: FPDF, title: str, correct: int, wrong: int, unanswered: int) -> None:
    _space_check(pdf, 55)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*C_PRIMARY_MID)
    _write(pdf, title, 5)
    _gap(pdf, 1.5)
    total = max(1, correct + wrong + unanswered)
    cx, cy, r = 46, pdf.get_y() + 18, 16
    slices = [(correct, C_ACCENT, "Correct"), (wrong, C_FAIL, "Wrong"), (unanswered, C_PRIMARY_MID, "Unanswered")]
    start = -90.0
    for amt, color, _ in slices:
        pdf.set_fill_color(*color)
        _pie_sector(pdf, cx, cy, r, start, start + 360.0 * (amt / total))
        start += 360.0 * (amt / total)
    lx, ly = 80, cy - 12
    for amt, color, label in slices:
        pdf.set_fill_color(*color)
        pdf.rect(lx, ly, 4.5, 4.5, style="F")
        pdf.set_xy(lx + 7, ly - 0.5)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*C_PRIMARY)
        pdf.cell(0, 6, f"{label}: {amt} ({(amt/total)*100:.1f}%)")
        ly += 9
    pdf.set_y(cy + 22)
    _gap(pdf, 3)

def _radar(pdf: FPDF, title: str, skills: dict[str, float]) -> None:
    _space_check(pdf, 65)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*C_PRIMARY_MID)
    _write(pdf, title, 5)
    _gap(pdf, 1.5)
    labels, cx, cy, r = list(skills.keys()), 100, pdf.get_y() + 22, 19
    values, n = [max(0.0, min(100.0, float(skills[k]))) for k in labels], len(labels)
    # Grid
    pdf.set_draw_color(*C_PRIMARY_LIGHT)
    for lv in [0.25, 0.5, 0.75, 1.0]:
        ring = [(cx + r*lv*math.cos(-math.pi/2+2*math.pi*i/n), cy+r*lv*math.sin(-math.pi/2+2*math.pi*i/n)) for i in range(n)]
        pdf.polygon(ring, style="D")
    # Axis & Labels
    for i, label in enumerate(labels):
        ang = -math.pi/2 + 2*math.pi*i/n
        pdf.line(cx, cy, cx+r*math.cos(ang), cy+r*math.sin(ang))
        pdf.set_xy(cx+(r+8)*math.cos(ang)-14, cy+(r+8)*math.sin(ang)-2)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*C_PRIMARY_MID)
        pdf.cell(28, 4, _safe(label), align="C")
    # Shape
    poly = [(cx+r*(values[i]/100)*math.cos(-math.pi/2+2*math.pi*i/n), cy+r*(values[i]/100)*math.sin(-math.pi/2+2*math.pi*i/n)) for i in range(n)]
    pdf.set_fill_color(*C_ACCENT_LIGHT)
    pdf.set_draw_color(*C_ACCENT)
    pdf.set_line_width(0.6)
    pdf.polygon(poly, style="DF")
    pdf.set_line_width(0.2)
    pdf.set_y(cy + 28)
    _gap(pdf, 3)

def _learning_diagram(pdf: FPDF, title: str, nodes: list[str]) -> None:
    _space_check(pdf, 38)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*C_PRIMARY_MID)
    _write(pdf, title, 5)
    x, y, w, h, gap = MARGIN + 2, pdf.get_y() + 1, 40, 9, 6
    for idx, node in enumerate(nodes):
        nx = x + idx * (w + gap)
        # Node card
        pdf.set_fill_color(*C_BG_ALT)
        pdf.set_draw_color(*C_PRIMARY_LIGHT)
        pdf.rect(nx, y, w, h, style="DF")
        # Badge
        pdf.set_fill_color(*C_ACCENT)
        pdf.circle(nx + 4.5, y + h/2, 2.8, style="F")
        pdf.set_xy(nx + 2, y + h/2 - 2)
        pdf.set_font("Helvetica", "B", 6.5)
        pdf.set_text_color(*C_WHITE)
        pdf.cell(5, 4, str(idx + 1), align="C")
        # Text
        pdf.set_xy(nx + 9, y + 2.5)
        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(*C_PRIMARY)
        pdf.cell(w - 11, 4, _safe(node)[:22])
        # Arrow
        if idx < len(nodes) - 1:
            pdf.set_draw_color(*C_ACCENT)
            pdf.set_line_width(0.4)
            pdf.line(nx+w, y+h/2, nx+w+gap-1, y+h/2)
            pdf.set_line_width(0.2)
    pdf.set_y(y + h + 4)
    _gap(pdf, 3)

# ─── Scoring Helpers ──────────────────────────────────────────────────────────
def _strength(score: float) -> str:
    if score >= 75: return "Strong"
    if score >= 55: return "Moderate"
    return "Weak"

def _strength_color(s: str):
    return C_OK if s == "Strong" else (C_PRIMARY_MID if s == "Moderate" else C_FAIL)

def _insight(topic: str, score: float, unanswered: int) -> str:
    if score >= 75:    return f"Confident in {topic}; maintain with variation drills."
    if unanswered > 0: return f"Gaps in {topic} from skipped items; improve time allocation."
    return f"Weak in {topic}; revise core rules then practice timed sets."

def _score_pill(pdf: FPDF, score: float, x: float, y: float, w: float = 38, h: float = 12) -> None:
    color = C_ACCENT if score >= 70 else (C_PRIMARY_MID if score >= 45 else C_FAIL)
    pdf.set_fill_color(*color)
    pdf.rect(x, y, w, h, style="F")
    pdf.set_xy(x, y + 2.5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*C_WHITE)
    pdf.cell(w, 6, f"{score:.1f}%", align="C")

def _page_header(pdf, exam_title, email, sid, code, dur, status, score):
    # Indigo Top
    pdf.set_fill_color(*C_PRIMARY); pdf.rect(0, 0, PAGE_W, 18, style="F")
    pdf.set_fill_color(*C_ACCENT); pdf.rect(0, 18, PAGE_W, 1.2, style="F")
    # Title
    pdf.set_xy(MARGIN, 4.5); pdf.set_font("Helvetica", "B", 11); pdf.set_text_color(*C_WHITE); pdf.cell(110, 6, "Student Exam Analytics Report")
    pdf.set_xy(MARGIN, 11.5); pdf.set_font("Helvetica", "", 7); pdf.set_text_color(*C_PRIMARY_LIGHT); pdf.cell(110, 4, _safe(exam_title)[:60])
    # Pill
    _score_pill(pdf, score, PAGE_W - MARGIN - 38, 3, 38, 13)
    # Info Bar
    pdf.set_fill_color(*C_BG_ALT); pdf.rect(0, 19.2, PAGE_W, 7, style="F")
    pdf.set_xy(MARGIN, 20.5); pdf.set_font("Helvetica", "", 7); pdf.set_text_color(*C_PRIMARY_MID)
    pdf.cell(60, 3.5, f"Candidate: {_safe(email)}")
    pdf.cell(58, 3.5, f"Session: {sid} | Code: {_safe(code)}")
    pdf.cell(0, 3.5, f"Dur: {dur}m | Status: {_safe(status)}")
    pdf.set_text_color(*C_PRIMARY); pdf.set_y(30)

def _page_footer(pdf: FPDF, sid: int) -> None:
    pdf.set_y(-11)
    pdf.set_draw_color(*C_PRIMARY_LIGHT)
    pdf.line(MARGIN, pdf.get_y(), MARGIN + BODY_W, pdf.get_y())
    pdf.ln(1.5)
    pdf.set_font("Helvetica", "I", 6)
    pdf.set_text_color(*C_PRIMARY_MID)
    pdf.cell(0, 3.5, f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | Session {sid} | Analytics Platform", align="C")

# ─── Main Builder ─────────────────────────────────────────────────────────────
def build_exam_report_pdf(db: Session, session: ExamSession, student_email: str) -> bytes:
    exam = db.query(Exam).filter(Exam.code == session.exam_code).first()
    report = build_exam_report(db, session, student_email)
    
    # Data aggregation
    links = db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).all() if exam else []
    q_ids = [lk.question_id for lk in links]
    answers = db.query(ExamAnswer).filter(ExamAnswer.session_id == session.id).all()
    violations = db.query(Violation).filter(Violation.session_id == session.id).order_by(Violation.created_at.desc()).all()
    ev_counts = Counter(v.event_type for v in violations)
    
    total_q, att, corr = len(q_ids), len(answers), sum(1 for a in answers if a.is_correct)
    wrong, unans, score_pct = max(0, att-corr), max(0, total_q-att), float(report.get("score_percent", 0.0))
    acc = round((corr/att)*100, 2) if att else 0.0
    dur = max(0.0, round(((session.ended_at or datetime.utcnow()) - session.started_at).total_seconds()/60, 2))
    
    topic_bd = report.get("topic_breakdown", [])
    weakest = min(topic_bd, key=lambda x: float(x.get("mastery_percent", 0.0))).get("topic", "general") if topic_bd else "general"
    
    att_r, un_r = (att/max(1, total_q))*100, (unans/max(1, total_q))*100
    conc, ana, appl = max(0, min(100, score_pct)), max(0, min(100, score_pct-0.35*un_r-0.18*wrong)), max(0, min(100, score_pct-0.12*wrong+0.06*att_r))
    f_score = max(0, min(100, 100-session.risk_score*0.9-min(25, len(violations)*1.4)))
    rk_lvl = "High" if session.risk_score >= 75 else ("Moderate" if session.risk_score >= 40 else "Low")
    rk_clr = C_FAIL if rk_lvl == "High" else (C_WARN if rk_lvl == "Moderate" else C_OK)
    top_abn = ", ".join(f"{n}({c})" for n, c in ev_counts.most_common(3)) or "None"
    
    # Recommendation logic
    recs = report.get("recommended_actions", [])
    if weakest and weakest != "general":
        recs += [f"Focus sprint on {weakest.replace('_',' ').title()}: concept recap and timed sets."]
    
    # PDF Setup
    pdf = FPDF(orientation="P")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_fill_color(*C_BG)
    pdf.rect(0, 0, PAGE_W, PAGE_H, style="F")
    
    _page_header(pdf, exam.title if exam else session.exam_code, student_email, session.id, session.exam_code, dur, session.status, score_pct)
    
    _section(pdf, "Session Information")
    _kv(pdf, [
        ("Exam Title", exam.title if exam else session.exam_code),
        ("Candidate", student_email),
        ("Session ID", str(session.id)),
        ("Exam Code", session.exam_code),
        ("Started", str(session.started_at)),
        ("Ended", str(session.ended_at or "In progress")),
        ("Duration", f"{dur} minutes"),
        ("Status", session.status)
    ])
    
    _section(pdf, "Performance Overview")
    y0, card_w, card_h = pdf.get_y(), 29, 16; gap = (BODY_W - 6*card_w)/5
    cards = [
        ("Score", f"{score_pct:.1f}%", C_ACCENT),
        ("Accuracy", f"{acc:.1f}%", C_ACCENT if acc>=70 else C_PRIMARY_MID),
        ("Attempted", f"{att}/{total_q}", C_PRIMARY),
        ("Correct", str(corr), C_OK),
        ("Wrong", str(wrong), C_FAIL if wrong else C_PRIMARY_MID),
        ("Unanswered", str(unans), C_PRIMARY_MID if unans else C_OK)
    ]
    for i, (lab, val, clr) in enumerate(cards):
        x = MARGIN + i*(card_w+gap)
        pdf.set_fill_color(*C_WHITE); pdf.set_draw_color(*C_PRIMARY_LIGHT); pdf.rect(x, y0, card_w, card_h, style="DF")
        pdf.set_fill_color(*clr); pdf.rect(x, y0, card_w, 2, style="F") # Top accent
        pdf.set_xy(x, y0+4.5); pdf.set_font("Helvetica", "B", 10.5); pdf.set_text_color(*clr); pdf.cell(card_w, 5, _safe(val), align="C")
        pdf.set_xy(x, y0+10.5); pdf.set_font("Helvetica", "", 6.5); pdf.set_text_color(*C_PRIMARY_MID); pdf.cell(card_w, 3.5, _safe(lab), align="C")
    
    pdf.set_y(y0+card_h+5); _space_check(pdf, 12); y_ins = pdf.get_y()
    pdf.set_fill_color(*C_ACCENT_LIGHT); pdf.set_draw_color(*C_ACCENT); pdf.rect(MARGIN, y_ins, BODY_W, 9, style="DF")
    pdf.set_fill_color(*C_ACCENT); pdf.rect(MARGIN, y_ins, 2.5, 9, style="F")
    pdf.set_xy(MARGIN+5, y_ins+1.5); pdf.set_font("Helvetica", "B", 7.5); pdf.set_text_color(*C_ACCENT_DARK); pdf.cell(18, 4, "AI Insight  ")
    pdf.set_font("Helvetica", "", 7.5); pdf.set_text_color(*C_PRIMARY)
    pdf.multi_cell(BODY_W-24, 4, _safe(f"{report.get('overall_summary','')} Accuracy balance indicates {'strong retention' if acc>=75 else 'potential conceptual leakage'}.")[:200])
    
    pdf.set_y(y_ins+13); _section(pdf, "Visual Analytics")
    _bar_chart(pdf, "Topic Performance (%)", [(item.get("topic","general"), float(item.get("mastery_percent",0.0))) for item in topic_bd])
    _pie_chart(pdf, "Answer Distribution", corr, wrong, unans)
    _radar(pdf, "Cognitive Skill Profile", {"Conceptual": conc, "Analytical": ana, "Application": appl})
    
    _section(pdf, "Topic-wise Analysis"); _space_check(pdf, 14+max(1, len(topic_bd[:8]))*6); h_y = pdf.get_y()
    pdf.set_fill_color(*C_PRIMARY); pdf.rect(MARGIN, h_y, BODY_W, 6, style="F")
    pdf.set_xy(MARGIN+3, h_y+1.2); pdf.set_font("Helvetica", "B", 7); pdf.set_text_color(*C_WHITE); pdf.cell(52, 4, "Topic"); pdf.cell(22, 4, "Score"); pdf.cell(22, 4, "Strength"); pdf.cell(0, 4, "Insight"); pdf.ln(7)
    for idx, item in enumerate(topic_bd[:8]):
        top, mas, u_t = str(item.get("topic","general")), float(item.get("mastery_percent",0.0)), int(item.get("unanswered",0))
        st, ins = _strength(mas), _insight(top, mas, u_t)
        row_y = pdf.get_y(); _space_check(pdf, 6)
        if idx%2==0: pdf.set_fill_color(*C_BG_ALT); pdf.rect(MARGIN, row_y, BODY_W, 5.5, style="F")
        pdf.set_xy(MARGIN+3, row_y+0.8); pdf.set_font("Helvetica", "", 7.5); pdf.set_text_color(*C_PRIMARY); pdf.cell(52, 4, _safe(top)[:24]); pdf.cell(22, 4, f"{mas:.1f}%")
        pdf.set_fill_color(*_strength_color(st)); p_x = pdf.get_x(); pdf.rect(p_x, row_y+1, 18, 3.5, style="F")
        pdf.set_text_color(*C_WHITE); pdf.set_font("Helvetica", "B", 6.5); pdf.cell(18, 3.5, st, align="C")
        pdf.set_font("Helvetica", "", 7); pdf.set_text_color(*C_PRIMARY_MID); pdf.multi_cell(0, 4, _safe(ins))
        
    _section(pdf, "Cognitive Skill Analysis"); _kv(pdf, [("Conceptual Understanding", f"{conc:.1f}%"), ("Analytical Thinking", f"{ana:.1f}%"), ("Application Ability", f"{appl:.1f}%")], col_w=90)
    
    _section(pdf, "Proctoring Analysis"); _space_check(pdf, 14); rk_y = pdf.get_y()
    pdf.set_fill_color(*C_WHITE); pdf.set_draw_color(*C_PRIMARY_LIGHT); pdf.rect(MARGIN, rk_y, BODY_W, 11, style="DF")
    pdf.set_fill_color(*rk_clr); pdf.rect(MARGIN, rk_y, 2.5, 11, style="F")
    pdf.set_xy(MARGIN+6, rk_y+1.8); pdf.set_font("Helvetica", "B", 8); pdf.set_text_color(*C_PRIMARY_MID); pdf.cell(28, 4, "Risk Level:")
    pdf.set_text_color(*rk_clr); pdf.set_font("Helvetica", "B", 9); pdf.cell(24, 4, rk_lvl)
    pdf.set_xy(MARGIN+78, rk_y+1.8); pdf.set_font("Helvetica", "B", 8); pdf.set_text_color(*C_PRIMARY_MID); pdf.cell(22, 4, "Risk Score:")
    pdf.set_text_color(*C_PRIMARY); pdf.cell(20, 4, f"{session.risk_score:.1f}")
    pdf.set_xy(MARGIN+138, rk_y+1.8); pdf.set_font("Helvetica", "B", 8); pdf.set_text_color(*C_PRIMARY_MID); pdf.cell(18, 4, "Focus Score:")
    pdf.set_text_color(*C_PRIMARY); pdf.cell(20, 4, f"{f_score:.1f}/100")
    pdf.set_xy(MARGIN+6, rk_y+6.5); pdf.set_font("Helvetica", "", 7); pdf.set_text_color(*C_PRIMARY_MID); pdf.cell(0, 3.5, f"Total events: {len(violations)} | Primary patterns: {_safe(top_abn)}")
    
    _section(pdf, "Strengths & Weaknesses"); _space_check(pdf, 32); sw_y, col_w2 = pdf.get_y(), 90
    pdf.set_fill_color(*C_BG_ALT); pdf.set_draw_color(*C_PRIMARY_LIGHT); pdf.rect(MARGIN, sw_y, col_w2, 6, style="DF")
    pdf.set_fill_color(*C_ACCENT); pdf.rect(MARGIN, sw_y, 2.5, 6, style="F")
    pdf.set_xy(MARGIN+5, sw_y+1.5); pdf.set_font("Helvetica", "B", 8); pdf.set_text_color(*C_ACCENT_DARK); pdf.cell(0, 3.5, "Strengths")
    pdf.set_y(sw_y+7); pdf.set_font("Helvetica", "", 7.5); pdf.set_text_color(*C_PRIMARY)
    for s in (report.get("strengths",[])[:3] or ["Revision cadence maintenance."]):
        pdf.set_xy(MARGIN+3, pdf.get_y()); pdf.set_fill_color(*C_ACCENT); pdf.circle(MARGIN+5, pdf.get_y()+2.2, 1.2, style="F")
        pdf.set_xy(MARGIN+8, pdf.get_y()); pdf.multi_cell(col_w2-9, 4.5, _safe(s))
    rx, cw2r = MARGIN+col_w2+6, BODY_W-col_w2-6
    pdf.set_xy(rx, sw_y); pdf.set_fill_color(*C_BG_ALT); pdf.set_draw_color(*C_PRIMARY_LIGHT); pdf.rect(rx, sw_y, cw2r, 6, style="DF")
    pdf.set_fill_color(*C_FAIL); pdf.rect(rx, sw_y, 2.5, 6, style="F")
    pdf.set_xy(rx+5, sw_y+1.5); pdf.set_font("Helvetica", "B", 8); pdf.set_text_color(*C_FAIL); pdf.cell(0, 3.5, "Improvement Areas")
    pdf.set_y(sw_y+7); pdf.set_font("Helvetica", "", 7.5); pdf.set_text_color(*C_PRIMARY)
    for w in (report.get("improvement_areas",[])[:3] or ["Answer speed refinement."]):
        pdf.set_xy(rx+3, pdf.get_y()); pdf.set_fill_color(*C_FAIL); pdf.circle(rx+5, pdf.get_y()+2.2, 1.2, style="F")
        pdf.set_xy(rx+8, pdf.get_y()); pdf.multi_cell(cw2r-9, 4.5, _safe(w))
        
    _gap(pdf, 4); _section(pdf, "Personalized Recommendations"); pdf.set_font("Helvetica", "", 7.8); pdf.set_text_color(*C_PRIMARY)
    for i, rec in enumerate(recs[:6]):
        _space_check(pdf, 9); ry = pdf.get_y(); pdf.set_fill_color(*C_PRIMARY); pdf.circle(MARGIN+3.5, ry+3, 2.8, style="F")
        pdf.set_xy(MARGIN+1, ry+0.8); pdf.set_font("Helvetica", "B", 7); pdf.set_text_color(*C_WHITE); pdf.cell(5.5, 4.5, str(i+1), align="C")
        pdf.set_xy(MARGIN+9, ry+0.5); pdf.multi_cell(BODY_W-9, 5, _safe(rec)); _gap(pdf, 1)
        
    _section(pdf, "Learning Enhancement"); _learning_diagram(pdf, f"Concept Flow — {weakest.replace('_',' ').title()}", [f"{weakest[:14]} basics", "Core rule", "Worked example", "Common pitfall"])
    _learning_diagram(pdf, "Revision Loop", ["Read concept", "Solve timed", "Analyse errors", "Re-attempt"])
    
    # Evidence Gallery
    ev_frames = db.query(EvidenceFrame).filter(EvidenceFrame.session_id == session.id).order_by(EvidenceFrame.timestamp.asc()).all()
    c_met = report.get("client_proctor_metrics",{})
    cred = c_met.get("credibilityScore")
    if ev_frames or cred is not None:
        pdf.add_page(); pdf.set_fill_color(*C_BG); pdf.rect(0, 0, PAGE_W, PAGE_H, style="F"); _section(pdf, "Incident Evidence Gallery")
        if cred is not None:
            _space_check(pdf, 14); c_y = pdf.get_y()
            pdf.set_fill_color(*C_WHITE); pdf.set_draw_color(*C_PRIMARY_LIGHT); pdf.rect(MARGIN, c_y, BODY_W, 12, style="DF")
            c_clr = C_OK if cred > 80 else (C_PRIMARY_MID if cred > 50 else C_FAIL)
            pdf.set_fill_color(*c_clr); pdf.rect(MARGIN, c_y, 2.5, 12, style="F")
            pdf.set_xy(MARGIN + 6, c_y + 2); pdf.set_font("Helvetica", "B", 8); pdf.set_text_color(*C_PRIMARY_MID); pdf.cell(32, 4, "Credibility Score")
            pdf.set_font("Helvetica", "B", 12); pdf.set_text_color(*c_clr); pdf.cell(24, 4, f"{cred}%")
            p_x, p_p = MARGIN+80, [("Face Missing", f"{c_met.get('noFaceSeconds',0)}s"), ("Phone Detected", f"{c_met.get('mobileSeconds',0)}s"), ("Focus Lost", f"{c_met.get('focusLostSeconds',0)}s"), ("Tab Switches", str(c_met.get('tabSwitchCount',0)))]
            for lab, val in p_p:
                pdf.set_xy(p_x, c_y+2); pdf.set_font("Helvetica", "B", 6.5); pdf.set_text_color(*C_PRIMARY_MID); pdf.cell(24, 3.5, lab)
                pdf.set_xy(p_x, c_y + 6.5); pdf.set_font("Helvetica", "B", 8); pdf.set_text_color(*C_PRIMARY); pdf.cell(24, 3.5, val); p_x += 28
            pdf.set_y(c_y + 15)
        if not ev_frames:
            pdf.set_font("Helvetica", "I", 8); pdf.set_text_color(*C_PRIMARY_MID); _write(pdf, "No visual incident evidence captured by the proctoring engine.")
        else:
            pdf.set_font("Helvetica", "", 7.5); pdf.set_text_color(*C_PRIMARY_MID); _write(pdf, f"{len(ev_frames)} incident frame(s) analyzed.")
            _gap(pdf, 2)
            COLS, IMG_W, IMG_H = 3, 56, 42; C_G = (BODY_W - COLS*IMG_W)/(COLS-1); C_H = IMG_H + 13
            c_idx, r_y = 0, pdf.get_y()
            for ef in ev_frames:
                rsn = (ef.ai_analysis or {}).get("reason", "unknown")
                t_s = ef.timestamp.strftime("%H:%M:%S") if ef.timestamp else "N/A"
                f_d, x_p = ef.frame_base64 or "", MARGIN + c_idx*(IMG_W + C_G)
                if c_idx == 0: _space_check(pdf, C_H + 4); r_y = pdf.get_y()
                rd = False
                if f_d and len(f_d) > 200:
                    try:
                        data = f_d.split(",", 1)[1] if "," in f_d else f_d
                        raw = base64.b64decode(data); buf = io.BytesIO(raw); buf.name = f"ev_{ef.id}.jpg"
                        pdf.image(buf, x=x_p, y=r_y, w=IMG_W, h=IMG_H); rd = True
                    except: pass
                if not rd:
                    pdf.set_fill_color(*C_BG_ALT); pdf.set_draw_color(*C_PRIMARY_LIGHT); pdf.rect(x_p, r_y, IMG_W, IMG_H, style="DF")
                    pdf.set_xy(x_p+2, r_y+IMG_H/2-3); pdf.set_font("Helvetica", "I", 7); pdf.set_text_color(*C_PRIMARY_MID); pdf.cell(IMG_W-4, 5, "[Frame unavailable]", align="C")
                pdf.set_draw_color(*C_PRIMARY_LIGHT); pdf.rect(x_p, r_y, IMG_W, IMG_H, style="D")
                pdf.set_xy(x_p, r_y+IMG_H+1.5); pdf.set_font("Helvetica", "B", 7); pdf.set_text_color(*C_FAIL); pdf.cell(IMG_W, 4, _safe(rsn)[:30])
                pdf.set_xy(x_p, r_y+IMG_H+6); pdf.set_font("Helvetica", "", 6.5); pdf.set_text_color(*C_PRIMARY_MID); pdf.cell(IMG_W, 4, t_s)
                c_idx += 1
                if c_idx == COLS: c_idx = 0; pdf.set_y(r_y + C_H + 3)
            if c_idx != 0: pdf.set_y(r_y + C_H + 3)
            
    _page_footer(pdf, session.id); return _pdf_bytes(pdf)