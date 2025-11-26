from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, UniqueConstraint
from datetime import date, datetime

Base = declarative_base()


class Student(Base):
    __tablename__ = "students"  # name of the table in SQLite

    # Primary key – unique ID for each student
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Basic identity fields
    first_name = Column(String(80), nullable=False)
    last_name = Column(String(80), nullable=False)

    # Date of birth – uses SQL DATE type
    dob = Column(Date, nullable=False)

    # e.g. "5th", "8th", "12th", "K", etc.
    grade_level = Column(String(16), nullable=False)

    # e.g. "Active", "Inactive", "Graduated"
    status = Column(String(16), nullable=False, default="Active")

    # Guardian and contact info (can be empty, so nullable=True)
    guardian_name = Column(String(120), nullable=True)
    guardian_phone = Column(String(40), nullable=True)

    contact_email = Column(String(120), nullable=True)

    # List of Enrollment objects for this student (one per class)
    enrollments = relationship(
        "Enrollment",
        back_populates="student",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Student id={self.id} "
            f"name={self.first_name} {self.last_name} "
            f"grade={self.grade_level}>"
        )

class Class(Base):
    __tablename__ = "classes"  # name of the table in SQLite

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Human-readable name, like "Algebra I - Period 3"
    name = Column(String(120), nullable=False)

    # Subject area, like "Math", "English", "Science"
    subject = Column(String(120), nullable=True)

    # Name of the primary teacher
    teacher_name = Column(String(120), nullable=True)

    # Term or semester, like "Fall 2025", "2025-2026", etc.
    term = Column(String(40), nullable=True)

    # Room number (or online code)
    room = Column(String(40), nullable=True)
    
    # List of Enrollment objects for this class (one per student)
    enrollments = relationship(
        "Enrollment",
        back_populates="clazz",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Class id={self.id} "
            f"name={self.name} "
            f"teacher={self.teacher_name} "
            f"term={self.term}>"
        )

class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys linking to Student and Class tables
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)

    # Optional: dates for when the student was in the class
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    # Relationships back to the Python objects
    student = relationship("Student", back_populates="enrollments")
    clazz = relationship("Class", back_populates="enrollments")

    # Optional: prevent duplicate enrollments for the same (student, class)
    __table_args__ = (
        UniqueConstraint("student_id", "class_id", name="uq_student_class"),
    )

    def __repr__(self) -> str:
        return (
            f"<Enrollment id={self.id} "
            f"student_id={self.student_id} "
            f"class_id={self.class_id}>"
        )

class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys linking to Student and Class
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)

    # Date this attendance record applies to (school day)
    date = Column(Date, nullable=False)

    # Present / Absent / Tardy / Excused
    status = Column(String(16), nullable=False, default="Present")

    # Who marked it (for now, simple text; later: link to User)
    marked_by = Column(String(120), nullable=True)

    # When it was marked
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Optional: link back to Student and Class (nice for queries)
    student = relationship("Student")
    clazz = relationship("Class")

    def __repr__(self) -> str:
        return (
            f"<Attendance id={self.id} "
            f"student_id={self.student_id} "
            f"class_id={self.class_id} "
            f"date={self.date} "
            f"status={self.status}>"
        )

class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AdminUser id={self.id} username={self.username}>"
