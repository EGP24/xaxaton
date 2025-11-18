from sqlalchemy import Column, Integer, String, ForeignKey, Date, Boolean, Float, Table, Enum as SQLEnum, Time
from sqlalchemy.orm import relationship
from database import Base
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    TEACHER = "teacher"


class LessonType(str, enum.Enum):
    LECTURE = "Л"
    SEMINAR = "С"
    LAB = "ЛР"


class StudentStatus(str, enum.Enum):
    PRESENT = "present"  # Присутствовал (не отображается, используется внутренне)
    ABSENT = "absent"    # Отсутствовал
    EXCUSED = "excused"  # Уважительная причина
    AUTO_DETECTED = "auto_detected"  # Автоматически распознан на фото


class WeekType(str, enum.Enum):
    EVEN = "even"  # Четная неделя
    ODD = "odd"    # Нечетная неделя
    BOTH = "both"  # Обе недели


class DayOfWeek(int, enum.Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5


# Таблица для связи многие-ко-многим между шаблонами расписания и группами
template_groups = Table(
    'template_groups',
    Base.metadata,
    Column('schedule_template_id', Integer, ForeignKey('schedule_templates.id')),
    Column('group_id', Integer, ForeignKey('groups.id'))
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    role = Column(SQLEnum(UserRole))

    teacher_disciplines = relationship("TeacherDiscipline", back_populates="teacher")


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, index=True)
    face_encoding = Column(String, nullable=True)  # JSON-строка с эмбеддингом лица
    group_id = Column(Integer, ForeignKey("groups.id"))

    group = relationship("Group", back_populates="students")
    records = relationship("StudentRecord", back_populates="student")


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)

    students = relationship("Student", back_populates="group")
    schedule_templates = relationship("ScheduleTemplate", secondary=template_groups, back_populates="groups")


class Discipline(Base):
    __tablename__ = "disciplines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)

    schedule_templates = relationship("ScheduleTemplate", back_populates="discipline")
    teacher_disciplines = relationship("TeacherDiscipline", back_populates="discipline")


class Semester(Base):
    """Семестр - период обучения"""
    __tablename__ = "semesters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)  # Например: "Осень 2024"
    start_date = Column(Date)
    end_date = Column(Date)
    is_active = Column(Boolean, default=False)  # Активный семестр

    schedule_templates = relationship("ScheduleTemplate", back_populates="semester")
    schedule_instances = relationship("ScheduleInstance", back_populates="semester")


class ScheduleTemplate(Base):
    """Шаблон расписания - повторяющееся занятие в рамках семестра"""
    __tablename__ = "schedule_templates"

    id = Column(Integer, primary_key=True, index=True)
    semester_id = Column(Integer, ForeignKey("semesters.id"))
    discipline_id = Column(Integer, ForeignKey("disciplines.id"))
    classroom = Column(String)  # Номер аудитории
    teacher_id = Column(Integer, ForeignKey("users.id"))
    lesson_type = Column(SQLEnum(LessonType))

    # Расписание по дням недели
    day_of_week = Column(Integer)  # 0-5 (пн-сб)
    time_start = Column(String)  # Формат "HH:MM"
    time_end = Column(String)

    # Тип недели
    week_type = Column(SQLEnum(WeekType), default=WeekType.BOTH)

    is_stream = Column(Boolean, default=False)  # Потоковая пара или нет

    semester = relationship("Semester", back_populates="schedule_templates")
    discipline = relationship("Discipline", back_populates="schedule_templates")
    teacher = relationship("User")
    groups = relationship("Group", secondary=template_groups, back_populates="schedule_templates")
    instances = relationship("ScheduleInstance", back_populates="template")


class ScheduleInstance(Base):
    """Конкретное занятие - экземпляр шаблона на определенную дату"""
    __tablename__ = "schedule_instances"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("schedule_templates.id"))
    semester_id = Column(Integer, ForeignKey("semesters.id"))
    date = Column(Date, index=True)

    # Можно переопределить данные из шаблона при необходимости
    classroom = Column(String, nullable=True)  # Если None - берется из шаблона
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Если None - берется из шаблона
    is_cancelled = Column(Boolean, default=False)  # Отмененное занятие

    template = relationship("ScheduleTemplate", back_populates="instances")
    semester = relationship("Semester", back_populates="schedule_instances")
    teacher = relationship("User", foreign_keys=[teacher_id])
    records = relationship("StudentRecord", back_populates="schedule_instance")


class TeacherDiscipline(Base):
    """Связь преподавателей с дисциплинами"""
    __tablename__ = "teacher_disciplines"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"))
    discipline_id = Column(Integer, ForeignKey("disciplines.id"))

    teacher = relationship("User", back_populates="teacher_disciplines")
    discipline = relationship("Discipline", back_populates="teacher_disciplines")


class StudentRecord(Base):
    """Объединенная таблица для посещаемости и оценок"""
    __tablename__ = "student_records"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    schedule_instance_id = Column(Integer, ForeignKey("schedule_instances.id"))
    status = Column(SQLEnum(StudentStatus), default=StudentStatus.PRESENT)
    grade = Column(Float, nullable=True)  # Оценка может быть пустой

    student = relationship("Student", back_populates="records")
    schedule_instance = relationship("ScheduleInstance", back_populates="records")

