from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, date
from typing import Optional

from database import get_db, engine
from models import (Base, User, Student, Group, Discipline, Semester, ScheduleTemplate, ScheduleInstance,
                    StudentRecord, UserRole, LessonType, StudentStatus, WeekType)
from auth import authenticate_user, create_access_token, get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES

Base.metadata.create_all(bind=engine)

app = FastAPI(title="University Journal System")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse(url="/login")


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


# ============ API для работы с группами ============

@app.get("/api/groups")
async def get_groups(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    groups = db.query(Group).all()
    return [{"id": g.id, "name": g.name} for g in groups]


@app.get("/api/groups/{group_id}/students")
async def get_group_students(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    students = db.query(Student).filter(Student.group_id == group_id).all()
    return [{"id": s.id, "full_name": s.full_name, "group_id": s.group_id, "group_name": s.group.name} for s in students]


# ============ API для работы с расписанием ============

@app.get("/api/schedules")
async def get_schedules(
    group_id: Optional[int] = None,
    discipline_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Получить расписание (конкретные занятия) с фильтрами"""
    # Получаем активный семестр
    active_semester = db.query(Semester).filter(Semester.is_active == True).first()
    if not active_semester:
        return []

    query = db.query(ScheduleInstance).filter(ScheduleInstance.semester_id == active_semester.id)

    # Фильтр по группе через шаблон
    if group_id:
        query = query.join(ScheduleInstance.template).join(ScheduleTemplate.groups).filter(Group.id == group_id)

    # Фильтр по дисциплине
    if discipline_name:
        query = query.join(ScheduleInstance.template).join(ScheduleTemplate.discipline).filter(Discipline.name == discipline_name)

    instances = query.all()
    result = []

    for instance in instances:
        template = instance.template

        # Определяем преподавателя (из instance или template)
        teacher = instance.teacher if instance.teacher_id else template.teacher
        classroom = instance.classroom if instance.classroom else template.classroom

        # Проверяем права на редактирование
        can_edit = True
        if current_user.role == UserRole.TEACHER:
            can_edit = (teacher.id == current_user.id)

        # Проверяем, что занятие в прошлом (для возможности ставить оценки)
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


@app.get("/api/schedules/{schedule_id}/records")
async def get_schedule_records(schedule_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Получить записи студентов по занятию"""
    instance = db.query(ScheduleInstance).filter(ScheduleInstance.id == schedule_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Schedule not found")

    template = instance.template

    # Получаем всех студентов из групп этого занятия
    students = []
    for group in template.groups:
        students.extend(db.query(Student).filter(Student.group_id == group.id).all())

    # Получаем существующие записи
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
    """Создать или обновить запись студента"""
    # Проверяем существование занятия
    instance = db.query(ScheduleInstance).filter(ScheduleInstance.id == schedule_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Проверка: занятие должно быть в прошлом
    if instance.date >= date.today():
        raise HTTPException(status_code=403, detail="Cannot edit future classes")

    # Проверка: занятие не отменено
    if instance.is_cancelled:
        raise HTTPException(status_code=403, detail="Cannot edit cancelled classes")

    template = instance.template
    teacher = instance.teacher if instance.teacher_id else template.teacher

    # Проверяем права доступа
    if current_user.role == UserRole.TEACHER:
        if teacher.id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only edit records for your own classes")

    # Проверяем существующую запись
    record = db.query(StudentRecord).filter(
        StudentRecord.student_id == student_id,
        StudentRecord.schedule_instance_id == schedule_id
    ).first()

    if record:
        record.status = StudentStatus(status)
        record.grade = grade
    else:
        record = StudentRecord(
            student_id=student_id,
            schedule_instance_id=schedule_id,
            status=StudentStatus(status),
            grade=grade
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
async def get_students(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    students = db.query(Student).all()
    return [{"id": s.id, "full_name": s.full_name, "group_id": s.group_id, "group_name": s.group.name} for s in students]


@app.get("/api/semesters")
async def get_semesters(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Получить список семестров"""
    semesters = db.query(Semester).all()
    return [{
        "id": s.id,
        "name": s.name,
        "start_date": str(s.start_date),
        "end_date": str(s.end_date),
        "is_active": s.is_active
    } for s in semesters]


# ============ АДМИНИСТРАТИВНЫЕ API ============

def check_admin(current_user: User):
    """Проверка прав администратора"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")


@app.post("/api/admin/students")
async def create_student(
    full_name: str = Form(...),
    group_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Создать студента"""
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
    """Удалить студента"""
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
    """Создать группу"""
    check_admin(current_user)

    group = Group(name=name)
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
    """Удалить группу"""
    check_admin(current_user)

    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    db.delete(group)
    db.commit()

    return {"success": True}


@app.post("/api/admin/disciplines")
async def create_discipline(
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Создать дисциплину"""
    check_admin(current_user)

    discipline = Discipline(name=name)
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
    """Удалить дисциплину"""
    check_admin(current_user)

    discipline = db.query(Discipline).filter(Discipline.id == discipline_id).first()
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")

    db.delete(discipline)
    db.commit()

    return {"success": True}


@app.post("/api/admin/semesters")
async def create_semester(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Создать семестр"""
    check_admin(current_user)

    data = await request.json()

    # Если новый семестр активный, деактивируем все остальные
    if data.get('is_active', False):
        db.query(Semester).update({Semester.is_active: False})

    semester = Semester(
        name=data['name'],
        start_date=data['start_date'],
        end_date=data['end_date'],
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
    """Активировать семестр"""
    check_admin(current_user)

    semester = db.query(Semester).filter(Semester.id == semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")

    # Деактивируем все семестры
    db.query(Semester).update({Semester.is_active: False})

    # Активируем выбранный
    semester.is_active = True
    db.commit()

    return {"success": True}


@app.delete("/api/admin/semesters/{semester_id}")
async def delete_semester(
    semester_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Удалить семестр"""
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
    """Получить список преподавателей"""
    check_admin(current_user)

    teachers = db.query(User).filter(User.role == UserRole.TEACHER).all()
    return [{"id": t.id, "full_name": t.full_name} for t in teachers]


@app.get("/api/admin/schedule-templates")
async def get_schedule_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Получить шаблоны расписания"""
    check_admin(current_user)

    active_semester = db.query(Semester).filter(Semester.is_active == True).first()
    if not active_semester:
        return []

    templates = db.query(ScheduleTemplate).filter(
        ScheduleTemplate.semester_id == active_semester.id
    ).all()

    return [{
        "id": t.id,
        "discipline": t.discipline.name,
        "teacher": t.teacher.full_name,
        "lesson_type": t.lesson_type.value,
        "classroom": t.classroom,
        "day_of_week": t.day_of_week,
        "time_start": t.time_start,
        "time_end": t.time_end,
        "week_type": t.week_type.value,
        "groups": [{"id": g.id, "name": g.name} for g in t.groups]
    } for t in templates]


@app.post("/api/admin/schedule-templates")
async def create_schedule_template(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Создать шаблон расписания"""
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

    # Добавляем группы
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
    """Удалить шаблон расписания"""
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
    """Генерировать конкретные занятия из шаблонов"""
    check_admin(current_user)

    active_semester = db.query(Semester).filter(Semester.is_active == True).first()
    if not active_semester:
        raise HTTPException(status_code=400, detail="No active semester")

    # Удаляем старые будущие занятия
    db.query(ScheduleInstance).filter(
        ScheduleInstance.semester_id == active_semester.id,
        ScheduleInstance.date >= date.today()
    ).delete()

    # Получаем все шаблоны
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
                # Проверяем, не существует ли уже такое занятие
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)

