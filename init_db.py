"""Скрипт для создания и наполнения базы данных с новой системой расписаний"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import (User, Student, Group, Discipline, Semester, ScheduleTemplate, ScheduleInstance,
                    TeacherDiscipline, StudentRecord, UserRole, LessonType, StudentStatus, WeekType, DayOfWeek)
from passlib.context import CryptContext
from datetime import date, timedelta
import random

# Создаем движок базы данных
SQLALCHEMY_DATABASE_URL = "sqlite:///./university.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

# Создаем все таблицы
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

print("🗑️  Старая база данных удалена")
print("✅ Таблицы созданы с новой структурой")
print("📝 Начинаем наполнение тестовыми данными...\n")

# 1. Создаем пользователей
admin = User(
    username="admin",
    hashed_password=pwd_context.hash("admin123"),
    full_name="Администратор Системы",
    role=UserRole.ADMIN
)

teacher1 = User(
    username="ivanov",
    hashed_password=pwd_context.hash("teacher123"),
    full_name="Иванов Иван Иванович",
    role=UserRole.TEACHER
)

teacher2 = User(
    username="petrova",
    hashed_password=pwd_context.hash("teacher123"),
    full_name="Петрова Мария Сергеевна",
    role=UserRole.TEACHER
)

teacher3 = User(
    username="sidorov",
    hashed_password=pwd_context.hash("teacher123"),
    full_name="Сидоров Петр Александрович",
    role=UserRole.TEACHER
)

db.add_all([admin, teacher1, teacher2, teacher3])
db.commit()
print("👥 Созданы пользователи (admin, ivanov, petrova, sidorov)\n")

# 2. Создаем группы
groups_data = ["ИВТ-301", "ИВТ-302", "ИВТ-401", "ПИ-301"]
groups = []
for group_name in groups_data:
    group = Group(name=group_name)
    groups.append(group)
    db.add(group)
db.commit()
print(f"📚 Созданы группы: {', '.join(groups_data)}\n")

# 3. Создаем студентов
students_data = [
    ("Алексеев Алексей Алексеевич", "ИВТ-301"),
    ("Борисова Анна Владимировна", "ИВТ-301"),
    ("Васильев Дмитрий Игоревич", "ИВТ-301"),
    ("Григорьева Елена Петровна", "ИВТ-301"),
    ("Дмитриев Сергей Николаевич", "ИВТ-301"),
    ("Егоров Максим Андреевич", "ИВТ-302"),
    ("Жукова Ольга Сергеевна", "ИВТ-302"),
    ("Иванова Татьяна Дмитриевна", "ИВТ-302"),
    ("Козлов Андрей Владимирович", "ИВТ-302"),
    ("Лебедева Наталья Игоревна", "ИВТ-302"),
    ("Михайлов Павел Александрович", "ИВТ-401"),
    ("Новикова Светлана Петровна", "ИВТ-401"),
    ("Орлов Виктор Сергеевич", "ИВТ-401"),
    ("Павлова Марина Николаевна", "ИВТ-401"),
    ("Романов Игорь Владимирович", "ПИ-301"),
    ("Семенова Юлия Андреевна", "ПИ-301"),
    ("Тихонов Константин Дмитриевич", "ПИ-301"),
    ("Федорова Анастасия Игоревна", "ПИ-301"),
]

students = []
for student_name, group_name in students_data:
    group = next(g for g in groups if g.name == group_name)
    student = Student(full_name=student_name, group_id=group.id)
    students.append(student)
    db.add(student)
db.commit()
print(f"🎓 Создано {len(students)} студентов\n")

# 4. Создаем дисциплины
disciplines_data = [
    "Математический анализ",
    "Программирование",
    "Базы данных",
    "Алгоритмы и структуры данных",
    "Веб-разработка",
    "Операционные системы"
]
disciplines = []
for discipline_name in disciplines_data:
    discipline = Discipline(name=discipline_name)
    disciplines.append(discipline)
    db.add(discipline)
db.commit()
print(f"📖 Созданы дисциплины: {', '.join(disciplines_data)}\n")

# 5. Связываем преподавателей с дисциплинами
teacher_disciplines_data = [
    (teacher1.id, disciplines[0].id),
    (teacher1.id, disciplines[3].id),
    (teacher2.id, disciplines[1].id),
    (teacher2.id, disciplines[4].id),
    (teacher3.id, disciplines[2].id),
    (teacher3.id, disciplines[5].id),
]

for teacher_id, discipline_id in teacher_disciplines_data:
    td = TeacherDiscipline(teacher_id=teacher_id, discipline_id=discipline_id)
    db.add(td)
db.commit()
print("👨‍🏫 Преподаватели назначены на дисциплины\n")

# 6. Создаем семестр
today = date.today()
# Определяем начало семестра (например, начало сентября или февраля)
if today.month >= 9:  # Осенний семестр
    semester_start = date(today.year, 9, 1)
    semester_end = date(today.year, 12, 31)
    semester_name = f"Осень {today.year}"
else:  # Весенний семестр
    semester_start = date(today.year, 2, 1)
    semester_end = date(today.year, 6, 30)
    semester_name = f"Весна {today.year}"

semester = Semester(
    name=semester_name,
    start_date=semester_start,
    end_date=semester_end,
    is_active=True
)
db.add(semester)
db.commit()
print(f"📆 Создан семестр: {semester_name} ({semester_start} - {semester_end})\n")

# 7. Создаем шаблоны расписания
templates = []

# Программирование для ИВТ-301 (понедельник, лекция, обе недели)
template1 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[1].id,
    classroom="А-201",
    teacher_id=teacher2.id,
    lesson_type=LessonType.LECTURE,
    day_of_week=DayOfWeek.MONDAY.value,
    time_start="09:00",
    time_end="10:30",
    week_type=WeekType.BOTH,
    is_stream=False
)
template1.groups.append(groups[0])
templates.append(template1)
db.add(template1)

# Программирование для ИВТ-301 (среда, лабораторная, только нечетные недели)
template2 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[1].id,
    classroom="Б-401",
    teacher_id=teacher2.id,
    lesson_type=LessonType.LAB,
    day_of_week=DayOfWeek.WEDNESDAY.value,
    time_start="11:00",
    time_end="12:30",
    week_type=WeekType.ODD,
    is_stream=False
)
template2.groups.append(groups[0])
templates.append(template2)
db.add(template2)

# Программирование для ИВТ-301 (пятница, семинар, только четные недели)
template3 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[1].id,
    classroom="В-203",
    teacher_id=teacher2.id,
    lesson_type=LessonType.SEMINAR,
    day_of_week=DayOfWeek.FRIDAY.value,
    time_start="13:00",
    time_end="14:30",
    week_type=WeekType.EVEN,
    is_stream=False
)
template3.groups.append(groups[0])
templates.append(template3)
db.add(template3)

# Базы данных для ИВТ-301 (вторник, лекция, обе недели)
template4 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[2].id,
    classroom="Б-305",
    teacher_id=teacher3.id,
    lesson_type=LessonType.LECTURE,
    day_of_week=DayOfWeek.TUESDAY.value,
    time_start="09:00",
    time_end="10:30",
    week_type=WeekType.BOTH,
    is_stream=False
)
template4.groups.append(groups[0])
templates.append(template4)
db.add(template4)

# Базы данных для ИВТ-301 (четверг, лабораторная, обе недели)
template5 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[2].id,
    classroom="Б-305",
    teacher_id=teacher3.id,
    lesson_type=LessonType.LAB,
    day_of_week=DayOfWeek.THURSDAY.value,
    time_start="15:00",
    time_end="16:30",
    week_type=WeekType.BOTH,
    is_stream=False
)
template5.groups.append(groups[0])
templates.append(template5)
db.add(template5)

# Программирование для ИВТ-301 (среда, другой преподаватель для теста прав)
template6 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[1].id,
    classroom="А-305",
    teacher_id=teacher1.id,  # Другой преподаватель!
    lesson_type=LessonType.LECTURE,
    day_of_week=DayOfWeek.WEDNESDAY.value,
    time_start="15:00",
    time_end="16:30",
    week_type=WeekType.EVEN,
    is_stream=False
)
template6.groups.append(groups[0])
templates.append(template6)
db.add(template6)

# ДЕМОНСТРАЦИЯ: Несколько пар в одно время (вторник 09:00 - подгруппы)
# Подгруппа 1 - Программирование (лабораторная)
template7 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[1].id,
    classroom="Б-401",
    teacher_id=teacher2.id,
    lesson_type=LessonType.LAB,
    day_of_week=DayOfWeek.TUESDAY.value,
    time_start="11:00",
    time_end="12:30",
    week_type=WeekType.BOTH,
    is_stream=False
)
template7.groups.append(groups[0])
templates.append(template7)
db.add(template7)

# Подгруппа 2 - Веб-разработка (лабораторная) в то же время
template8 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[4].id,
    classroom="Б-402",
    teacher_id=teacher2.id,
    lesson_type=LessonType.LAB,
    day_of_week=DayOfWeek.TUESDAY.value,
    time_start="11:00",
    time_end="12:30",
    week_type=WeekType.BOTH,
    is_stream=False
)
template8.groups.append(groups[0])
templates.append(template8)
db.add(template8)

# ДЕМОНСТРАЦИЯ: Три пары в одно время (пятница 13:00)
# Математика - подгруппа 1
template9 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[0].id,
    classroom="А-101",
    teacher_id=teacher1.id,
    lesson_type=LessonType.SEMINAR,
    day_of_week=DayOfWeek.FRIDAY.value,
    time_start="13:00",
    time_end="14:30",
    week_type=WeekType.ODD,
    is_stream=False
)
template9.groups.append(groups[0])
templates.append(template9)
db.add(template9)

# Алгоритмы - подгруппа 2
template10 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[3].id,
    classroom="А-102",
    teacher_id=teacher1.id,
    lesson_type=LessonType.SEMINAR,
    day_of_week=DayOfWeek.FRIDAY.value,
    time_start="13:00",
    time_end="14:30",
    week_type=WeekType.ODD,
    is_stream=False
)
template10.groups.append(groups[0])
templates.append(template10)
db.add(template10)

# Операционные системы - подгруппа 3
template11 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[5].id,
    classroom="А-103",
    teacher_id=teacher3.id,
    lesson_type=LessonType.SEMINAR,
    day_of_week=DayOfWeek.FRIDAY.value,
    time_start="13:00",
    time_end="14:30",
    week_type=WeekType.ODD,
    is_stream=False
)
template11.groups.append(groups[0])
templates.append(template11)
db.add(template11)

# ДЕМОНСТРАЦИЯ: Две пары ПРОГРАММИРОВАНИЯ в один день (понедельник)
# Первая пара - лекция в 09:00 (уже есть как template1)
# Вторая пара - практика в 12:00
template12 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[1].id,
    classroom="Б-403",
    teacher_id=teacher2.id,
    lesson_type=LessonType.SEMINAR,
    day_of_week=DayOfWeek.MONDAY.value,
    time_start="12:00",
    time_end="13:30",
    week_type=WeekType.BOTH,
    is_stream=False
)
template12.groups.append(groups[0])
templates.append(template12)
db.add(template12)

# ДЕМОНСТРАЦИЯ: Еще одна пара БАЗ ДАННЫХ в четверг
# Уже есть одна в 15:00, добавим в 09:00
template13 = ScheduleTemplate(
    semester_id=semester.id,
    discipline_id=disciplines[2].id,
    classroom="Б-306",
    teacher_id=teacher3.id,
    lesson_type=LessonType.SEMINAR,
    day_of_week=DayOfWeek.THURSDAY.value,
    time_start="09:00",
    time_end="10:30",
    week_type=WeekType.BOTH,
    is_stream=False
)
template13.groups.append(groups[0])
templates.append(template13)
db.add(template13)

db.commit()
print(f"📋 Создано {len(templates)} шаблонов расписания\n")

# 8. Генерируем экземпляры занятий на основе шаблонов
print("🔄 Генерация конкретных занятий из шаблонов...")

def get_week_number(d, start):
    """Определяет номер недели с начала семестра (0-based)"""
    days_diff = (d - start).days
    return days_diff // 7

def is_week_type_match(week_num, week_type):
    """Проверяет, подходит ли неделя под тип (четная/нечетная)"""
    if week_type == WeekType.BOTH:
        return True
    elif week_type == WeekType.EVEN:
        return week_num % 2 == 0
    else:  # ODD
        return week_num % 2 == 1

instances_count = 0
current_date = semester_start

# Генерируем занятия только до сегодняшнего дня (и несколько дней вперед для демонстрации)
end_generation_date = min(today + timedelta(days=14), semester_end)

while current_date <= end_generation_date:
    week_num = get_week_number(current_date, semester_start)
    day_of_week = current_date.weekday()

    # Ищем подходящие шаблоны для этого дня
    for template in templates:
        if template.day_of_week == day_of_week and is_week_type_match(week_num, template.week_type):
            instance = ScheduleInstance(
                template_id=template.id,
                semester_id=semester.id,
                date=current_date,
                is_cancelled=False
            )
            db.add(instance)
            instances_count += 1

    current_date += timedelta(days=1)

db.commit()
print(f"✅ Сгенерировано {instances_count} конкретных занятий\n")

# 9. Создаем записи о посещаемости и оценках только для прошедших занятий
print("📊 Создание записей о посещаемости для прошедших занятий...")

past_instances = db.query(ScheduleInstance).filter(
    ScheduleInstance.date < today
).all()

records_count = 0
for instance in past_instances:
    # Получаем шаблон для определения групп
    template = instance.template

    # Для каждой группы в шаблоне
    for group in template.groups:
        # Для каждого студента в группе
        group_students = db.query(Student).filter(Student.group_id == group.id).all()

        for student in group_students:
            # Случайный статус и оценка
            rand = random.random()

            if rand < 0.7:  # 70% - присутствовал с оценкой
                status_choice = StudentStatus.PRESENT
                grade = random.choice([3.0, 3.5, 4.0, 4.5, 5.0])
            elif rand < 0.85:  # 15% - отсутствовал
                status_choice = StudentStatus.ABSENT
                grade = None
            else:  # 15% - уважительная причина
                status_choice = StudentStatus.EXCUSED
                grade = None

            record = StudentRecord(
                student_id=student.id,
                schedule_instance_id=instance.id,
                status=status_choice,
                grade=grade
            )
            db.add(record)
            records_count += 1

db.commit()
print(f"✅ Создано {records_count} записей о посещаемости\n")

print("=" * 60)
print("🎉 База данных успешно создана с новой системой расписаний!")
print("=" * 60)
print("\n📊 Статистика:")
print(f"   Пользователей: {db.query(User).count()}")
print(f"   Студентов: {db.query(Student).count()}")
print(f"   Групп: {db.query(Group).count()}")
print(f"   Дисциплин: {db.query(Discipline).count()}")
print(f"   Семестров: {db.query(Semester).count()}")
print(f"   Шаблонов расписания: {db.query(ScheduleTemplate).count()}")
print(f"   Конкретных занятий: {db.query(ScheduleInstance).count()}")
print(f"   Записей о посещаемости: {db.query(StudentRecord).count()}")
print("\n📝 Особенности новой системы:")
print("   • Расписание составляется для четных/нечетных недель")
print("   • Занятия генерируются автоматически на семестр")
print("   • Оценки можно ставить только за прошедшие занятия")
print("   • Будущие занятия отображаются, но недоступны для редактирования")
print("\n🔐 Учетные данные для входа:")
print("   Администратор: admin / admin123")
print("   Преподаватель: ivanov / teacher123")
print("   Преподаватель: petrova / teacher123")
print("   Преподаватель: sidorov / teacher123")

db.close()

