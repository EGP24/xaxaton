from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_
from datetime import datetime, date, timedelta, time as dt_time
from typing import List, Optional

from database import get_db
from models import Student, ScheduleInstance, ScheduleTemplate, StudentRecord, StudentStatus, WeekType
from schemas import (
    FingerprintEnrollRequest,
    FingerprintScanRequest,
    FingerprintIdentifyResponse,
    StudentWithFingerprintResponse
)

router = APIRouter(prefix="/api/fingerprint", tags=["fingerprint"])


def is_even_week(check_date: date) -> bool:
    start_date = date(2024, 1, 1)
    days_diff = (check_date - start_date).days
    week_number = days_diff // 7
    return week_number % 2 == 0


def get_current_or_next_lesson(classroom: str, current_datetime: datetime, db: Session):
    today = current_datetime.date()
    current_time = current_datetime.time()
    day_of_week = today.weekday()

    if day_of_week == 6:
        return None

    even_week = is_even_week(today)
    week_type = WeekType.EVEN if even_week else WeekType.ODD

    instance = db.query(ScheduleInstance).join(
        ScheduleTemplate
    ).filter(
        ScheduleInstance.date == today,
        ScheduleInstance.is_cancelled == False,
        or_(
            ScheduleInstance.classroom == classroom,
            and_(
                ScheduleInstance.classroom.is_(None),
                ScheduleTemplate.classroom == classroom
            )
        )
    ).order_by(ScheduleTemplate.time_start).first()

    if instance:
        template = instance.template
        start_time = datetime.strptime(template.time_start, "%H:%M").time()
        end_time = datetime.strptime(template.time_end, "%H:%M").time()

        time_before = (datetime.combine(today, start_time) - timedelta(minutes=15)).time()

        if time_before <= current_time <= end_time:
            return instance

    templates = db.query(ScheduleTemplate).filter(
        ScheduleTemplate.classroom == classroom,
        ScheduleTemplate.day_of_week == day_of_week,
        or_(
            ScheduleTemplate.week_type == WeekType.BOTH,
            ScheduleTemplate.week_type == week_type
        )
    ).order_by(ScheduleTemplate.time_start).all()

    for template in templates:
        start_time = datetime.strptime(template.time_start, "%H:%M").time()
        time_before = (datetime.combine(today, start_time) - timedelta(minutes=15)).time()

        if current_time <= time_before:
            existing_instance = db.query(ScheduleInstance).filter(
                ScheduleInstance.template_id == template.id,
                ScheduleInstance.date == today
            ).first()

            if existing_instance and not existing_instance.is_cancelled:
                return existing_instance

    return None


@router.get("/students/templates", response_model=List[StudentWithFingerprintResponse])
def get_students_with_fingerprints(
    classroom: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Student).filter(
        Student.fingerprint_template.isnot(None)
    )

    if classroom:
        current_datetime = datetime.now()
        lesson = get_current_or_next_lesson(classroom, current_datetime, db)

        if lesson:
            template = lesson.template
            group_ids = [g.id for g in template.groups]
            query = query.filter(Student.group_id.in_(group_ids))

    students = query.all()

    return [
        StudentWithFingerprintResponse(
            id=s.id,
            full_name=s.full_name,
            group_id=s.group_id,
            fingerprint_template=s.fingerprint_template
        )
        for s in students
    ]


@router.post("/enroll")
def enroll_fingerprint(
    request: FingerprintEnrollRequest,
    db: Session = Depends(get_db)
):
    student = db.query(Student).filter(Student.id == request.student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )

    student.fingerprint_template = request.fingerprint_template

    db.commit()
    db.refresh(student)

    return {
        "success": True,
        "message": f"Fingerprint enrolled for {student.full_name}",
        "student_id": student.id
    }


@router.post("/identify", response_model=FingerprintIdentifyResponse)
def identify_fingerprint(
    request: FingerprintScanRequest,
    db: Session = Depends(get_db)
):
    student = db.query(Student).filter(Student.id == request.student_id).first()
    if not student:
        return FingerprintIdentifyResponse(
            success=False,
            message=f"Student with ID {request.student_id} not found"
        )

    current_datetime = datetime.now()
    lesson = get_current_or_next_lesson(request.classroom, current_datetime, db)

    if not lesson:
        return FingerprintIdentifyResponse(
            success=False,
            student_id=student.id,
            student_name=student.full_name,
            message=f"No active lesson in classroom {request.classroom}"
        )

    template = lesson.template
    group_ids = [g.id for g in template.groups]

    if student.group_id not in group_ids:
        return FingerprintIdentifyResponse(
            success=False,
            student_id=student.id,
            student_name=student.full_name,
            schedule_instance_id=lesson.id,
            message=f"Student {student.full_name} is not in the group for this lesson"
        )

    existing_record = db.query(StudentRecord).filter(
        StudentRecord.student_id == student.id,
        StudentRecord.schedule_instance_id == lesson.id
    ).first()

    if existing_record:
        if existing_record.status != StudentStatus.PRESENT:
            existing_record.status = StudentStatus.FINGERPRINT_DETECTED
            db.commit()
            message = f"Attendance updated for {student.full_name}"
        else:
            message = f"Attendance already marked for {student.full_name}"
    else:
        record = StudentRecord(
            student_id=student.id,
            schedule_instance_id=lesson.id,
            status=StudentStatus.FINGERPRINT_DETECTED
        )
        db.add(record)
        db.commit()
        message = f"Attendance marked for {student.full_name}"

    return FingerprintIdentifyResponse(
        success=True,
        student_id=student.id,
        student_name=student.full_name,
        schedule_instance_id=lesson.id,
        message=message
    )


@router.delete("/students/{student_id}/fingerprint")
def delete_fingerprint(student_id: int, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )

    student.fingerprint_template = None

    db.commit()

    return {
        "success": True,
        "message": f"Fingerprint deleted for {student.full_name}"
    }


@router.get("/test/classroom/{classroom}")
def test_current_lesson(classroom: str, db: Session = Depends(get_db)):
    current_datetime = datetime.now()
    lesson = get_current_or_next_lesson(classroom, current_datetime, db)

    if not lesson:
        return {
            "found": False,
            "message": f"No lesson found in classroom {classroom}",
            "current_time": current_datetime.isoformat()
        }

    template = lesson.template
    return {
        "found": True,
        "schedule_instance_id": lesson.id,
        "discipline": template.discipline.name,
        "classroom": lesson.classroom or template.classroom,
        "date": lesson.date.isoformat(),
        "time_start": template.time_start,
        "time_end": template.time_end,
        "groups": [g.name for g in template.groups],
        "current_time": current_datetime.isoformat()
    }

