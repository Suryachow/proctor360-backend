from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_current_admin, get_current_student
from app.db.session import get_db
from app.models.entities import SupportTicket, Student

router = APIRouter(prefix="/support", tags=["support"])

@router.post("/tickets")
def create_ticket(
    payload: dict,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    session_id = payload.get("session_id")
    subject = payload.get("subject")
    message = payload.get("message")
    
    if not subject or not message:
        raise HTTPException(status_code=400, detail="Subject and message are required")
        
    ticket = SupportTicket(
        session_id=session_id,
        student_email=student.email,
        subject=subject,
        message=message,
        status="open"
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket

@router.get("/tickets/my")
def get_my_tickets(
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    return db.query(SupportTicket).filter(SupportTicket.student_email == student.email).order_by(SupportTicket.created_at.desc()).all()

@router.get("/tickets/admin")
def get_admin_tickets(
    _: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
    status: str = "open"
):
    query = db.query(SupportTicket)
    if status != "all":
        query = query.filter(SupportTicket.status == status)
    return query.order_by(SupportTicket.created_at.desc()).all()

@router.post("/tickets/{ticket_id}/respond")
def respond_to_ticket(
    ticket_id: int,
    payload: dict,
    _: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    response = payload.get("response")
    status = payload.get("status", "resolved")
    
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    ticket.admin_response = response
    ticket.status = status
    if status == "resolved":
        ticket.resolved_at = datetime.utcnow()
        
    db.commit()
    return ticket
