from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, func
from datetime import timedelta, date
from typing import Optional, List
import csv
import io
import math

from database import get_db, engine
from models import (Base, User, Student, Group, Discipline, Semester, ScheduleTemplate, ScheduleInstance,
                    StudentRecord, UserRole, LessonType, StudentStatus, WeekType)
from auth import authenticate_user, create_access_token, get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES
from face_recognition_service import FaceRecognitionService
from openpyxl import Workbook
import fingerprint_api

Base.metadata.create_all(bind=engine)

app = FastAPI(title="University Journal System")

app.include_router(fingerprint_api.router)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

face_service = None

def get_face_service():
    global face_service
    if face_service is None:
        from face_recognition_service import FaceRecognitionService
        face_service = FaceRecognitionService(tolerance=0.6)
    return face_service


MAX_PAGE_SIZE = 100
MIN_GRADE = 2
MAX_GRADE_ALLOWED = 5


def normalize_pagination(page: int, page_size: int):
    page = max(1, page or 1)
    page_size = max(1, min(page_size or 20, MAX_PAGE_SIZE))
    return page, page_size


def apply_pagination(query, page: int, page_size: int):
    page, page_size = normalize_pagination(page, page_size)
    total = query.count()
    pages = max(1, math.ceil(total / page_size)) if total else 1
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, {
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages
    }


def restrict_to_teacher_classes(query, current_user: User):
    if current_user.role != UserRole.TEACHER:
        return query
    return query.filter(
        or_(
            ScheduleInstance.teacher_id == current_user.id,
            and_(
                ScheduleInstance.teacher_id.is_(None),
                ScheduleTemplate.teacher_id == current_user.id
            )
        )
    )


STATUS_LABELS = {
    StudentStatus.PRESENT: "Присутствовал",
    StudentStatus.ABSENT: "Отсутствовал",
    StudentStatus.EXCUSED: "Уважительная причина",
    StudentStatus.AUTO_DETECTED: "Присутствовал (авто)",
    StudentStatus.FINGERPRINT_DETECTED: "Присутствовал (отпечаток)"
}

PRESENT_STATUSES = {StudentStatus.PRESENT, StudentStatus.AUTO_DETECTED, StudentStatus.FINGERPRINT_DETECTED}


def validate_grade_value(grade: Optional[float]) -> Optional[int]:
    if grade is None:
        return None
    if not float(grade).is_integer():
        raise HTTPException(status_code=400, detail="Grade must be an integer value")
    grade_int = int(grade)
    if grade_int < MIN_GRADE or grade_int > MAX_GRADE_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=f"Grade must be between {MIN_GRADE} and {MAX_GRADE_ALLOWED}"
        )
    return grade_int

@app.get("/", response_class=HTMLResponse)
async def welcome_page(request: Request):
    return templates.TemplateResponse("welcome.html", {"request": request})


@app.get("/schedule", response_class=HTMLResponse)
async def schedule_page(request: Request):
    return templates.TemplateResponse("schedule.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role
    }


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/journal", response_class=HTMLResponse)
async def journal_page(request: Request):
    return templates.TemplateResponse("journal.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/attendance", response_class=HTMLResponse)
async def attendance_page(request: Request):
    return templates.TemplateResponse("attendance.html", {"request": request})



@app.get("/api/groups")
async def get_groups(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    groups = db.query(Group).all()
    return [{"id": g.id, "name": g.name} for g in groups]


@app.get("/api/groups/{group_id}/students")
async def get_group_students(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    students = db.query(Student).filter(Student.group_id == group_id).all()
    return [{"id": s.id, "full_name": s.full_name, "group_id": s.group_id, "group_name": s.group.name, "has_fingerprint": s.fingerprint_template is not None} for s in students]



@app.get("/api/schedules")
async def get_schedules(
    group_id: Optional[int] = None,
    discipline_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    active_semester = db.query(Semester).filter(Semester.is_active == True).first()
    if not active_semester:
        return []

    query = db.query(ScheduleInstance).filter(ScheduleInstance.semester_id == active_semester.id)
    query = query.join(ScheduleInstance.template)

    query = restrict_to_teacher_classes(query, current_user)

    if group_id:
        query = query.join(ScheduleTemplate.groups).filter(Group.id == group_id)

    if discipline_name:
        query = query.join(ScheduleTemplate.discipline).filter(Discipline.name == discipline_name)

    instances = query.all()
    result = []

    for instance in instances:
        template = instance.template

        teacher = instance.teacher if instance.teacher_id else template.teacher
        classroom = instance.classroom if instance.classroom else template.classroom

        can_edit = True
        if current_user.role == UserRole.TEACHER:
            can_edit = (teacher.id == current_user.id)

        is_past = instance.date < date.today()
        can_edit = can_edit and is_past and not instance.is_cancelled

        result.append({
            "id": instance.id,
            "discipline_id": template.discipline_id,
            "discipline": template.discipline.name,
            "classroom": classroom,
            "teacher": teacher.full_name,
            "teacher_id": teacher.id,
            "lesson_type": template.lesson_type.value,
            "date": str(instance.date),
            "time_start": template.time_start,
            "time_end": template.time_end,
            "is_stream": template.is_stream,
            "is_cancelled": instance.is_cancelled,
            "is_past": is_past,
            "groups": [{"id": g.id, "name": g.name} for g in template.groups],
            "can_edit": can_edit,
            "week_type": template.week_type.value
        })

    return result


@app.get("/api/my-schedule")
async def get_my_schedule(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    teacher_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in (UserRole.TEACHER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Schedule available only for teachers and admins")

    if date_from is None:
        date_from = date.today()
    if date_to is None:
        date_to = date_from + timedelta(days=7)

    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be earlier than date_to")

    query = db.query(ScheduleInstance).options(
        joinedload(ScheduleInstance.template).joinedload(ScheduleTemplate.discipline),
        joinedload(ScheduleInstance.template).joinedload(ScheduleTemplate.groups),
        joinedload(ScheduleInstance.teacher)
    ).join(ScheduleInstance.template).filter(
        ScheduleInstance.date >= date_from,
        ScheduleInstance.date <= date_to
    )

    if current_user.role == UserRole.ADMIN:
        if teacher_id:
            query = query.filter(
                or_(
                    ScheduleInstance.teacher_id == teacher_id,
                    and_(
                        ScheduleInstance.teacher_id.is_(None),
                        ScheduleTemplate.teacher_id == teacher_id
                    )
                )
            )
    else:
        query = restrict_to_teacher_classes(query, current_user)

    instances = query.order_by(ScheduleInstance.date, ScheduleTemplate.time_start).all()

    schedule = []
    today = date.today()
    for instance in instances:
        template = instance.template
        teacher = instance.teacher if instance.teacher_id else template.teacher
        classroom = instance.classroom if instance.classroom else template.classroom
        is_past = instance.date < today
        can_mark = (
            (current_user.role == UserRole.ADMIN or (teacher and teacher.id == current_user.id))
            and is_past
            and not instance.is_cancelled
        )
        schedule.append({
            "id": instance.id,
            "date": str(instance.date),
            "time_start": template.time_start,
            "time_end": template.time_end,
            "discipline": template.discipline.name,
            "lesson_type": template.lesson_type.value,
            "classroom": classroom,
            "groups": [{"id": g.id, "name": g.name} for g in template.groups],
            "is_cancelled": instance.is_cancelled,
            "is_past": is_past,
            "can_mark": can_mark,
            "teacher": teacher.full_name if teacher else None
        })

    return {
        "items": schedule,
        "meta": {
            "date_from": str(date_from),
            "date_to": str(date_to),
            "count": len(schedule)
        }
    }


@app.get("/api/schedules/{schedule_id}")
async def get_schedule_detail(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    instance = db.query(ScheduleInstance).options(
        joinedload(ScheduleInstance.template).joinedload(ScheduleTemplate.discipline),
        joinedload(ScheduleInstance.template).joinedload(ScheduleTemplate.groups),
        joinedload(ScheduleInstance.teacher)
    ).filter(ScheduleInstance.id == schedule_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Schedule not found")

    template = instance.template
    teacher = instance.teacher if instance.teacher_id else template.teacher
    classroom = instance.classroom if instance.classroom else template.classroom
    is_past = instance.date < date.today()
    can_mark = (
        (current_user.role == UserRole.ADMIN or (teacher and teacher.id == current_user.id))
        and is_past
        and not instance.is_cancelled
    )

    if current_user.role == UserRole.TEACHER and (not teacher or teacher.id != current_user.id):
        raise HTTPException(status_code=403, detail="You can only view your own classes")

    return {
        "id": instance.id,
        "date": str(instance.date),
        "time_start": template.time_start,
        "time_end": template.time_end,
        "discipline": template.discipline.name,
        "discipline_id": template.discipline_id,
        "lesson_type": template.lesson_type.value,
        "classroom": classroom,
        "groups": [{"id": g.id, "name": g.name} for g in template.groups],
        "teacher": teacher.full_name if teacher else None,
        "is_cancelled": instance.is_cancelled,
        "is_past": is_past,
        "can_mark": can_mark
    }


@app.get("/api/schedules/{schedule_id}/records")
async def get_schedule_records(schedule_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    instance = db.query(ScheduleInstance).filter(ScheduleInstance.id == schedule_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Schedule not found")

    template = instance.template

    if current_user.role == UserRole.TEACHER:
        assigned_teacher = instance.teacher if instance.teacher_id else template.teacher
        if not assigned_teacher or assigned_teacher.id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only view records for your own classes")

    students = []
    for group in template.groups:
        students.extend(db.query(Student).filter(Student.group_id == group.id).all())

    existing_records = db.query(StudentRecord).filter(StudentRecord.schedule_instance_id == schedule_id).all()
    records_dict = {r.student_id: r for r in existing_records}

    result = []
    for student in students:
        record = records_dict.get(student.id)
        result.append({
            "student_id": student.id,
            "student_name": student.full_name,
            "group_name": student.group.name,
            "status": record.status.value if record else StudentStatus.PRESENT.value,
            "grade": record.grade if record else None,
            "record_id": record.id if record else None
        })

    return result


@app.post("/api/records")
async def create_or_update_record(
    student_id: int = Form(...),
    schedule_id: int = Form(...),
    status: str = Form(...),
    grade: Optional[float] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    instance = db.query(ScheduleInstance).filter(ScheduleInstance.id == schedule_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if instance.date >= date.today():
        raise HTTPException(status_code=403, detail="Cannot edit future classes")

    if instance.is_cancelled:
        raise HTTPException(status_code=403, detail="Cannot edit cancelled classes")

    template = instance.template
    teacher = instance.teacher if instance.teacher_id else template.teacher

    if current_user.role == UserRole.TEACHER:
        if teacher.id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only edit records for your own classes")

    record = db.query(StudentRecord).filter(
        StudentRecord.student_id == student_id,
        StudentRecord.schedule_instance_id == schedule_id
    ).first()

    grade_value = validate_grade_value(grade)

    if record:
        record.status = StudentStatus(status)
        record.grade = grade_value
    else:
        record = StudentRecord(
            student_id=student_id,
            schedule_instance_id=schedule_id,
            status=StudentStatus(status),
            grade=grade_value
        )
        db.add(record)

    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "student_id": record.student_id,
        "schedule_instance_id": record.schedule_instance_id,
        "status": record.status.value,
        "grade": record.grade
    }


@app.get("/api/disciplines")
async def get_disciplines(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    disciplines = db.query(Discipline).all()
    return [{"id": d.id, "name": d.name} for d in disciplines]


@app.get("/api/students")
async def get_students(
    search: Optional[str] = None,
    group_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Student).options(joinedload(Student.group))

    if search:
        like_pattern = f"%{search.strip()}%"
        query = query.filter(Student.full_name.ilike(like_pattern))

    if group_id:
        query = query.filter(Student.group_id == group_id)

    query = query.order_by(Student.full_name)
    students, meta = apply_pagination(query, page, page_size)

    return {
        "items": [
            {
                "id": s.id,
                "full_name": s.full_name,
                "group_id": s.group_id,
                "group_name": s.group.name if s.group else None,
                "has_fingerprint": s.fingerprint_template is not None
            }
            for s in students
        ],
        "meta": meta
    }


@app.get("/api/semesters")
async def get_semesters(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    semesters = db.query(Semester).all()
    return [{
        "id": s.id,
        "name": s.name,
        "start_date": str(s.start_date),
        "end_date": str(s.end_date),
        "is_active": s.is_active
    } for s in semesters]



def check_admin(current_user: User):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")


@app.post("/api/admin/students")
async def create_student(
    full_name: str = Form(...),
    group_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    student = Student(full_name=full_name, group_id=group_id)
    db.add(student)
    db.commit()
    db.refresh(student)

    return {"id": student.id, "full_name": student.full_name, "group_id": student.group_id}


@app.delete("/api/admin/students/{student_id}")
async def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    db.delete(student)
    db.commit()

    return {"success": True}


@app.post("/api/admin/groups")
async def create_group(
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Group name cannot be empty")

    existing = db.query(Group).filter(func.lower(Group.name) == clean_name.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Group with this name already exists")

    group = Group(name=clean_name)
    db.add(group)
    db.commit()
    db.refresh(group)

    return {"id": group.id, "name": group.name}


@app.delete("/api/admin/groups/{group_id}")
async def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    has_students = db.query(Student.id).filter(Student.group_id == group_id).first()
    if has_students:
        raise HTTPException(status_code=400, detail="Cannot delete group with assigned students")

    is_used_in_templates = db.query(ScheduleTemplate).join(ScheduleTemplate.groups).filter(Group.id == group_id).first()
    if is_used_in_templates:
        raise HTTPException(status_code=400, detail="Group is used in schedule templates")

    db.delete(group)
    db.commit()

    return {"success": True}


@app.post("/api/admin/disciplines")
async def create_discipline(
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Discipline name cannot be empty")

    existing = db.query(Discipline).filter(func.lower(Discipline.name) == clean_name.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Discipline with this name already exists")

    discipline = Discipline(name=clean_name)
    db.add(discipline)
    db.commit()
    db.refresh(discipline)

    return {"id": discipline.id, "name": discipline.name}


@app.delete("/api/admin/disciplines/{discipline_id}")
async def delete_discipline(
    discipline_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    discipline = db.query(Discipline).filter(Discipline.id == discipline_id).first()
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")

    is_used_in_templates = db.query(ScheduleTemplate).filter(ScheduleTemplate.discipline_id == discipline_id).first()
    if is_used_in_templates:
        raise HTTPException(status_code=400, detail="Discipline is used in schedule templates")

    db.delete(discipline)
    db.commit()

    return {"success": True}


@app.post("/api/admin/semesters")
async def create_semester(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    data = await request.json()

    try:
        start_date = date.fromisoformat(data['start_date']) if isinstance(data['start_date'], str) else data['start_date']
        end_date = date.fromisoformat(data['end_date']) if isinstance(data['end_date'], str) else data['end_date']
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")

    if start_date >= end_date:
        raise HTTPException(status_code=400, detail="Start date must be earlier than end date")

    if data.get('is_active', False):
        db.query(Semester).update({Semester.is_active: False})

    semester = Semester(
        name=data['name'],
        start_date=start_date,
        end_date=end_date,
        is_active=data.get('is_active', False)
    )
    db.add(semester)
    db.commit()
    db.refresh(semester)

    return {"id": semester.id, "name": semester.name, "success": True}


@app.post("/api/admin/semesters/{semester_id}/activate")
async def activate_semester(
    semester_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")

    db.query(Semester).update({Semester.is_active: False})

    semester.is_active = True
    db.commit()

    return {"success": True}


@app.delete("/api/admin/semesters/{semester_id}")
async def delete_semester(
    semester_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")

    db.delete(semester)
    db.commit()

    return {"success": True}


@app.get("/api/admin/teachers")
async def get_teachers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    teachers = db.query(User).filter(User.role == UserRole.TEACHER).all()
    return [{"id": t.id, "full_name": t.full_name} for t in teachers]


@app.get("/api/admin/schedule-templates")
async def get_schedule_templates(
    discipline_id: Optional[int] = None,
    teacher_id: Optional[int] = None,
    group_id: Optional[int] = None,
    week_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    active_semester = db.query(Semester).filter(Semester.is_active == True).first()
    if not active_semester:
        return {"items": [], "meta": {"page": 1, "page_size": page_size, "total": 0, "pages": 1}}

    query = db.query(ScheduleTemplate).options(
        joinedload(ScheduleTemplate.groups),
        joinedload(ScheduleTemplate.discipline),
        joinedload(ScheduleTemplate.teacher)
    ).filter(ScheduleTemplate.semester_id == active_semester.id)

    if discipline_id:
        query = query.filter(ScheduleTemplate.discipline_id == discipline_id)

    if teacher_id:
        query = query.filter(ScheduleTemplate.teacher_id == teacher_id)

    if group_id:
        query = query.join(ScheduleTemplate.groups).filter(Group.id == group_id)

    if week_type:
        try:
            week_type_enum = WeekType(week_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid week type")
        else:
            if week_type_enum == WeekType.BOTH:
                pass
            else:
                query = query.filter(
                    or_(
                        ScheduleTemplate.week_type == week_type_enum,
                        ScheduleTemplate.week_type == WeekType.BOTH
                    )
                )

    query = query.order_by(ScheduleTemplate.day_of_week, ScheduleTemplate.time_start)

    templates, meta = apply_pagination(query, page, page_size)

    return {
        "items": [{
            "id": t.id,
            "discipline": t.discipline.name,
            "discipline_id": t.discipline_id,
            "teacher": t.teacher.full_name,
            "teacher_id": t.teacher_id,
            "lesson_type": t.lesson_type.value,
            "classroom": t.classroom,
            "day_of_week": t.day_of_week,
            "time_start": t.time_start,
            "time_end": t.time_end,
            "week_type": t.week_type.value,
            "groups": [{"id": g.id, "name": g.name} for g in t.groups]
        } for t in templates],
        "meta": meta
    }


@app.post("/api/admin/schedule-templates")
async def create_schedule_template(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    data = await request.json()

    active_semester = db.query(Semester).filter(Semester.is_active == True).first()
    if not active_semester:
        raise HTTPException(status_code=400, detail="No active semester")

    template = ScheduleTemplate(
        semester_id=active_semester.id,
        discipline_id=data['discipline_id'],
        teacher_id=data['teacher_id'],
        lesson_type=LessonType(data['lesson_type']),
        classroom=data['classroom'],
        day_of_week=data['day_of_week'],
        time_start=data['time_start'],
        time_end=data['time_end'],
        week_type=WeekType(data['week_type']),
        is_stream=False
    )

    for group_id in data['group_ids']:
        group = db.query(Group).filter(Group.id == group_id).first()
        if group:
            template.groups.append(group)

    db.add(template)
    db.commit()
    db.refresh(template)

    return {"id": template.id, "success": True}


@app.delete("/api/admin/schedule-templates/{template_id}")
async def delete_schedule_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    template = db.query(ScheduleTemplate).filter(ScheduleTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    db.delete(template)
    db.commit()

    return {"success": True}


@app.post("/api/admin/generate-instances")
async def generate_schedule_instances(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    active_semester = db.query(Semester).filter(Semester.is_active == True).first()
    if not active_semester:
        raise HTTPException(status_code=400, detail="No active semester")

    db.query(ScheduleInstance).filter(
        ScheduleInstance.semester_id == active_semester.id,
        ScheduleInstance.date >= date.today()
    ).delete()

    templates = db.query(ScheduleTemplate).filter(
        ScheduleTemplate.semester_id == active_semester.id
    ).all()

    def get_week_number(d, start):
        days_diff = (d - start).days
        return days_diff // 7

    def is_week_type_match(week_num, week_type):
        if week_type == WeekType.BOTH:
            return True
        elif week_type == WeekType.EVEN:
            return week_num % 2 == 0
        else:
            return week_num % 2 == 1

    instances_count = 0
    current_date = date.today()

    while current_date <= active_semester.end_date:
        week_num = get_week_number(current_date, active_semester.start_date)
        day_of_week = current_date.weekday()

        for template in templates:
            if template.day_of_week == day_of_week and is_week_type_match(week_num, template.week_type):
                existing = db.query(ScheduleInstance).filter(
                    ScheduleInstance.template_id == template.id,
                    ScheduleInstance.date == current_date
                ).first()

                if not existing:
                    instance = ScheduleInstance(
                        template_id=template.id,
                        semester_id=active_semester.id,
                        date=current_date,
                        is_cancelled=False
                    )
                    db.add(instance)
                    instances_count += 1

        current_date += timedelta(days=1)

    db.commit()

    return {"success": True, "count": instances_count}




def ensure_report_access(current_user: User):
    if current_user.role not in (UserRole.ADMIN, UserRole.TEACHER):
        raise HTTPException(status_code=403, detail="Reports available for teachers and admins only")


def build_report_rows(instances, students, records_map):
    rows = []
    for instance in instances:
        template = instance.template
        discipline_name = template.discipline.name
        for student in students:
            record = records_map.get((instance.id, student.id))
            status = record.status if record else None
            status_label = STATUS_LABELS.get(status, "Не отмечено")
            grade = record.grade if record else None

            rows.append({
                "date": str(instance.date),
                "lesson_type": template.lesson_type.value,
                "discipline": discipline_name,
                "student": student.full_name,
                "status": status_label,
                "status_code": status.value if status else None,
                "grade": grade
            })
    return rows


@app.get("/api/reports/journal")
async def get_journal_report(
    group_id: int,
    date_from: date,
    date_to: date,
    discipline_id: Optional[int] = None,
    format: str = "csv",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_report_access(current_user)

    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be earlier than date_to")

    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    students = db.query(Student).filter(Student.group_id == group_id).order_by(Student.full_name).all()
    if not students:
        raise HTTPException(status_code=404, detail="Group has no students")

    instances_query = db.query(ScheduleInstance).options(
        joinedload(ScheduleInstance.template).joinedload(ScheduleTemplate.discipline),
        joinedload(ScheduleInstance.template).joinedload(ScheduleTemplate.groups),
        joinedload(ScheduleInstance.teacher)
    ).join(ScheduleInstance.template).join(ScheduleTemplate.groups).filter(
        Group.id == group_id,
        ScheduleInstance.date >= date_from,
        ScheduleInstance.date <= date_to
    )

    if discipline_id:
        instances_query = instances_query.filter(ScheduleTemplate.discipline_id == discipline_id)

    instances_query = restrict_to_teacher_classes(instances_query, current_user)

    instances = instances_query.order_by(ScheduleInstance.date, ScheduleInstance.id).distinct().all()

    if not instances:
        raise HTTPException(status_code=404, detail="No lessons found for selected filters")

    instance_ids = [inst.id for inst in instances]
    student_ids = [student.id for student in students]

    records = db.query(StudentRecord).options(joinedload(StudentRecord.student)).filter(
        StudentRecord.schedule_instance_id.in_(instance_ids),
        StudentRecord.student_id.in_(student_ids)
    ).all()
    records_map = {(r.schedule_instance_id, r.student_id): r for r in records}

    rows = build_report_rows(instances, students, records_map)

    filename_base = f"journal_{group.name}_{date_from}_{date_to}"

    if format == "json":
        return {
            "group": {"id": group.id, "name": group.name},
            "period": {"from": str(date_from), "to": str(date_to)},
            "rows": rows
        }

    if format == "xlsx":
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Журнал"
        worksheet.append(["Дата", "Дисциплина", "Тип занятия", "Студент", "Статус", "Оценка"])
        for row in rows:
            worksheet.append([
                row["date"],
                row["discipline"],
                row["lesson_type"],
                row["student"],
                row["status"],
                row["grade"] if row["grade"] is not None else ""
            ])
        stream = io.BytesIO()
        workbook.save(stream)
        stream.seek(0)
        headers = {
            "Content-Disposition": f"attachment; filename={filename_base}.xlsx"
        }
        return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["Дата", "Дисциплина", "Тип занятия", "Студент", "Статус", "Оценка"])
    for row in rows:
        writer.writerow([
            row["date"],
            row["discipline"],
            row["lesson_type"],
            row["student"],
            row["status"],
            row["grade"] if row["grade"] is not None else ""
        ])

    headers = {
        "Content-Disposition": f"attachment; filename={filename_base}.csv"
    }
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)


@app.get("/api/reports/summary")
async def get_summary_report(
    group_id: int,
    date_from: date,
    date_to: date,
    discipline_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_report_access(current_user)

    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be earlier than date_to")

    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    students = db.query(Student).filter(Student.group_id == group_id).order_by(Student.full_name).all()
    if not students:
        raise HTTPException(status_code=404, detail="Group has no students")

    instances_query = db.query(ScheduleInstance).options(
        joinedload(ScheduleInstance.template).joinedload(ScheduleTemplate.discipline),
        joinedload(ScheduleInstance.template).joinedload(ScheduleTemplate.groups)
    ).join(ScheduleInstance.template).join(ScheduleTemplate.groups).filter(
        Group.id == group_id,
        ScheduleInstance.date >= date_from,
        ScheduleInstance.date <= date_to
    )

    if discipline_id:
        instances_query = instances_query.filter(ScheduleTemplate.discipline_id == discipline_id)

    instances_query = restrict_to_teacher_classes(instances_query, current_user)
    instances = instances_query.order_by(ScheduleInstance.date, ScheduleInstance.id).distinct().all()

    instance_ids = [inst.id for inst in instances]
    student_ids = [student.id for student in students]

    if not instance_ids:
        return {
            "group": {"id": group.id, "name": group.name},
            "period": {"from": str(date_from), "to": str(date_to)},
            "attendance": {"total_lessons": 0, "by_status": {}, "attendance_rate": 0},
            "grades": {"overall_average": None, "student_averages": []}
        }

    records = db.query(StudentRecord).filter(
        StudentRecord.schedule_instance_id.in_(instance_ids),
        StudentRecord.student_id.in_(student_ids)
    ).all()

    attendance_stats = {
        StudentStatus.PRESENT.value: 0,
        StudentStatus.ABSENT.value: 0,
        StudentStatus.EXCUSED.value: 0,
        StudentStatus.AUTO_DETECTED.value: 0,
        StudentStatus.FINGERPRINT_DETECTED.value: 0,
        "missing": 0
    }

    grade_map = {student.id: [] for student in students}
    total_possible_records = len(instance_ids) * len(students)

    for record in records:
        attendance_stats[record.status.value] += 1
        if record.grade is not None:
            grade_map[record.student_id].append(record.grade)

    attendance_stats["missing"] = max(0, total_possible_records - len(records))

    present_total = (
        attendance_stats[StudentStatus.PRESENT.value] +
        attendance_stats[StudentStatus.AUTO_DETECTED.value] +
        attendance_stats[StudentStatus.FINGERPRINT_DETECTED.value]
    )
    attendance_rate = present_total / total_possible_records if total_possible_records else 0

    student_averages = []
    overall_grades = []
    for student in students:
        grades = grade_map[student.id]
        if grades:
            avg = sum(grades) / len(grades)
            student_averages.append({
                "student_id": student.id,
                "student_name": student.full_name,
                "average_grade": round(avg, 2),
                "grades_count": len(grades)
            })
            overall_grades.extend(grades)
        else:
            student_averages.append({
                "student_id": student.id,
                "student_name": student.full_name,
                "average_grade": None,
                "grades_count": 0
            })

    overall_average = round(sum(overall_grades) / len(overall_grades), 2) if overall_grades else None

    return {
        "group": {"id": group.id, "name": group.name},
        "period": {"from": str(date_from), "to": str(date_to)},
        "filters": {
            "discipline_id": discipline_id
        },
        "lessons_found": len(instance_ids),
        "attendance": {
            "total_possible": total_possible_records,
            "by_status": attendance_stats,
            "attendance_rate": round(attendance_rate, 3)
        },
        "grades": {
            "overall_average": overall_average,
            "student_averages": student_averages
        }
    }



@app.post("/api/students/{student_id}/upload-face")
async def upload_student_face(
    student_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)

    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    image_bytes = await file.read()
    success = get_face_service().save_student_face(student_id, image_bytes, db)

    if not success:
        raise HTTPException(status_code=400, detail="Не удалось распознать лицо на фото")

    return {"success": True, "message": f"Фото студента {student.full_name} успешно сохранено"}


@app.post("/api/schedules/{schedule_id}/recognize-attendance")
async def recognize_attendance(
    schedule_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    schedule = db.query(ScheduleInstance).filter(ScheduleInstance.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Занятие не найдено")

    template = schedule.template
    teacher_id = schedule.teacher_id if schedule.teacher_id else template.teacher_id

    if current_user.role != UserRole.ADMIN and current_user.id != teacher_id:
        raise HTTPException(status_code=403, detail="Нет прав для редактирования этого занятия")

    group_ids = [g.id for g in template.groups]
    students = db.query(Student).filter(Student.group_id.in_(group_ids)).all()

    if not students:
        raise HTTPException(status_code=404, detail="Студенты не найдены")

    image_bytes = await file.read()
    recognized_ids, total_faces = get_face_service().recognize_students(image_bytes, students)

    updated_count = 0
    for student in students:
        record = db.query(StudentRecord).filter(
            StudentRecord.student_id == student.id,
            StudentRecord.schedule_instance_id == schedule_id
        ).first()

        if student.id in recognized_ids:
            if record:
                record.status = StudentStatus.AUTO_DETECTED
            else:
                record = StudentRecord(
                    student_id=student.id,
                    schedule_instance_id=schedule_id,
                    status=StudentStatus.AUTO_DETECTED
                )
                db.add(record)
            updated_count += 1
        else:
            if not record:
                record = StudentRecord(
                    student_id=student.id,
                    schedule_instance_id=schedule_id,
                    status=StudentStatus.ABSENT
                )
                db.add(record)

    db.commit()

    stats = get_face_service().get_recognition_stats(recognized_ids, total_faces, len(students))

    return {
        "success": True,
        "recognized_count": len(recognized_ids),
        "total_students": len(students),
        "total_faces": total_faces,
        "recognition_rate": f"{stats['recognition_rate'] * 100:.1f}%",
        "updated_count": updated_count,
        "stats": stats
    }


@app.get("/api/students/{student_id}/has-face")
async def check_student_face(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    return {
        "student_id": student_id,
        "has_face": student.face_encoding is not None
    }


@app.get("/api/groups/{group_id}/face-stats")
async def get_group_face_stats(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    students = db.query(Student).filter(Student.group_id == group_id).all()

    total = len(students)
    with_face = sum(1 for s in students if s.face_encoding is not None)

    return {
        "group_id": group_id,
        "total_students": total,
        "students_with_face": with_face,
        "students_without_face": total - with_face,
        "percentage": (with_face / total * 100) if total > 0 else 0
    }



@app.get("/api/dashboard/stats")
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from datetime import datetime, timedelta

    total_students = db.query(Student).count()
    total_groups = db.query(Group).count()
    total_disciplines = db.query(Discipline).count()

    students_with_face = db.query(Student).filter(Student.face_encoding.isnot(None)).count()
    face_coverage = (students_with_face / total_students * 100) if total_students > 0 else 0

    date_30_days_ago = date.today() - timedelta(days=30)
    recent_instances = db.query(ScheduleInstance).filter(
        ScheduleInstance.date >= date_30_days_ago,
        ScheduleInstance.date <= date.today()
    ).all()

    total_lessons_30d = len(recent_instances)

    if total_lessons_30d > 0:
        instance_ids = [inst.id for inst in recent_instances]
        records = db.query(StudentRecord).filter(
            StudentRecord.schedule_instance_id.in_(instance_ids)
        ).all()

        total_records = len(records)
        present_records = len([r for r in records if r.status in [StudentStatus.PRESENT, StudentStatus.AUTO_DETECTED, StudentStatus.FINGERPRINT_DETECTED]])
        attendance_rate_30d = (present_records / total_records * 100) if total_records > 0 else 0

        auto_detected = len([r for r in records if r.status == StudentStatus.AUTO_DETECTED])
        fingerprint_detected = len([r for r in records if r.status == StudentStatus.FINGERPRINT_DETECTED])
        auto_detection_rate = ((auto_detected + fingerprint_detected) / total_records * 100) if total_records > 0 else 0
    else:
        attendance_rate_30d = 0
        auto_detection_rate = 0
        total_records = 0

    groups = db.query(Group).all()
    group_stats = []

    for group in groups[:10]:
        group_students = db.query(Student).filter(Student.group_id == group.id).all()
        if not group_students:
            continue

        student_ids = [s.id for s in group_students]

        group_records = db.query(StudentRecord).filter(
            StudentRecord.student_id.in_(student_ids),
            StudentRecord.schedule_instance_id.in_(instance_ids) if total_lessons_30d > 0 else False
        ).all()

        if group_records:
            group_total = len(group_records)
            group_present = len([r for r in group_records if r.status in [StudentStatus.PRESENT, StudentStatus.AUTO_DETECTED, StudentStatus.FINGERPRINT_DETECTED]])
            group_rate = (group_present / group_total * 100) if group_total > 0 else 0

            group_stats.append({
                "id": group.id,
                "name": group.name,
                "attendance_rate": round(group_rate, 1),
                "total_records": group_total
            })

    group_stats.sort(key=lambda x: x['attendance_rate'], reverse=True)
    top_groups = group_stats[:3]
    bottom_groups = sorted(group_stats, key=lambda x: x['attendance_rate'])[:3]

    active_semester = db.query(Semester).filter(Semester.is_active == True).first()

    return {
        "overview": {
            "total_students": total_students,
            "total_groups": total_groups,
            "total_disciplines": total_disciplines,
            "students_with_face": students_with_face,
            "face_coverage_percentage": round(face_coverage, 1)
        },
        "attendance_30d": {
            "total_lessons": total_lessons_30d,
            "total_records": total_records,
            "attendance_rate": round(attendance_rate_30d, 1),
            "auto_detection_rate": round(auto_detection_rate, 1)
        },
        "top_groups": top_groups,
        "bottom_groups": bottom_groups,
        "active_semester": {
            "id": active_semester.id,
            "name": active_semester.name,
            "start_date": str(active_semester.start_date),
            "end_date": str(active_semester.end_date)
        } if active_semester else None
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)

