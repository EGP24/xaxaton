from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from models import UserRole, LessonType


class Token(BaseModel):
    access_token: str
    token_type: str


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: UserRole


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: UserRole

    class Config:
        from_attributes = True


class StudentCreate(BaseModel):
    full_name: str
    group_id: int


class StudentResponse(BaseModel):
    id: int
    full_name: str
    group_id: int

    class Config:
        from_attributes = True


class GroupCreate(BaseModel):
    name: str


class GroupResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class DisciplineCreate(BaseModel):
    name: str


class DisciplineResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class ClassroomCreate(BaseModel):
    name: str
    capacity: int


class ClassroomResponse(BaseModel):
    id: int
    name: str
    capacity: int

    class Config:
        from_attributes = True


class ScheduleCreate(BaseModel):
    discipline_id: int
    classroom_id: int
    teacher_id: int
    lesson_type: LessonType
    date: date
    time_start: str
    time_end: str
    is_stream: bool = False
    group_ids: List[int]


class ScheduleResponse(BaseModel):
    id: int
    discipline_id: int
    classroom_id: int
    teacher_id: int
    lesson_type: LessonType
    date: date
    time_start: str
    time_end: str
    is_stream: bool

    class Config:
        from_attributes = True


class AttendanceUpdate(BaseModel):
    student_id: int
    schedule_id: int
    is_present: bool


class GradeUpdate(BaseModel):
    student_id: int
    schedule_id: int
    grade: Optional[float]


class JournalCell(BaseModel):
    schedule_id: int
    attendance: Optional[bool]
    grade: Optional[float]


class JournalStudent(BaseModel):
    student_id: int
    student_name: str
    cells: List[JournalCell]


class JournalColumn(BaseModel):
    date: date
    lesson_type: LessonType
    schedule_id: int


class JournalResponse(BaseModel):
    columns: List[JournalColumn]
    students: List[JournalStudent]

