from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Boolean,
    Text,
)
from datetime import date, datetime
import json

Base = declarative_base()


class Student(Base):
    __tablename__ = "students"  # name of the table in SQLite

    # Primary key – unique ID for each student
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Basic identity fields
    first_name = Column(String(80), nullable=False)
    last_name = Column(String(80), nullable=False)
    dob = Column(Date, nullable=False)
    grade_level = Column(String(16), nullable=False)
    contact_email = Column(String(120), nullable=True)

    # Guardian and contact info (can be empty, so nullable=True)
    guardian_name = Column(String(120), nullable=True)
    guardian_phone = Column(String(40), nullable=True)
    guardian_email = Column(String(120), nullable=True)

    # Emergency contact
    emergency_contact_name = Column(String(120), nullable=True)
    emergency_contact_phone = Column(String(40), nullable=True)

    status = Column(String(16), nullable=False, default="Active")

    # Path to profile photo on disk
    photo_path = Column(String(255), nullable=True)

    # Free-form notes about the student (optional)
    notes = Column(Text, nullable=True)

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

    # List of TeacherClassLink objects
    teacher_links = relationship(
        "TeacherClassLink",
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


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Displayed in UI (and potentially in future reports)
    school_name = Column(String(200), nullable=True)
    academic_year = Column(String(50), nullable=True)

    # JSON-encoded list of attendance statuses (e.g. ["Present", "Absent", "Tardy", "Excused"])
    attendance_statuses_json = Column(
        Text,
        nullable=False,
        default='["Present", "Absent", "Tardy", "Excused", "No School"]',
    )

    # Base folder for exports (can be overridden by manual file dialogs)
    export_base_dir = Column(String(255), nullable=True)

    # If true, auto-saves both student + teacher attendance as changes are made
    attendance_auto_save = Column(Boolean, nullable=False, default=False)

    # Grade range for promotion logic (subset of a PreK–12 scale)
    starting_grade = Column(String(20), nullable=True)   # e.g. "K", "1st"
    graduating_grade = Column(String(20), nullable=True) # e.g. "5th", "12th"

    # JSON-encoded list of active school days, e.g. ["Mon", "Tue", "Wed", "Thu", "Fri"]
    school_days_json = Column(Text, nullable=True)

    # Theme (Light / Dark)
    theme = Column(String(16), nullable=False, default="Light")

    # --- Teacher-tracker related options ---

    # If true, the Teacher Tracker tab allows check-in/check-out times
    teacher_check_in_out_enabled = Column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<Settings id={self.id} school_name={self.school_name!r}>"


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Basic identity
    first_name = Column(String(80), nullable=False)
    last_name = Column(String(80), nullable=False)

    # Contact info
    phone = Column(String(40), nullable=True)
    email = Column(String(120), nullable=True)

    # Emergency contact
    emergency_contact_name = Column(String(120), nullable=True)
    emergency_contact_phone = Column(String(40), nullable=True)

    # Extras
    status = Column(String(16), nullable=False, default="Active")  # Active / Inactive
    notes = Column(Text, nullable=True)
    photo_path = Column(String(255), nullable=True)

    # Link rows connecting this teacher to classes they teach
    class_links = relationship(
        "TeacherClassLink",
        back_populates="teacher",
        cascade="all, delete-orphan",
    )

    # Teacher attendance records (per-day, not class-based)
    teacher_attendance = relationship(
        "TeacherAttendance",
        back_populates="teacher",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Teacher id={self.id} "
            f"name={self.first_name} {self.last_name}>"
        )


class TeacherClassLink(Base):
    __tablename__ = "teacher_class_link"

    id = Column(Integer, primary_key=True, autoincrement=True)

    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)

    teacher = relationship("Teacher", back_populates="class_links")
    clazz = relationship("Class", back_populates="teacher_links")

    __table_args__ = (
        UniqueConstraint("teacher_id", "class_id", name="uq_teacher_class"),
    )

    def __repr__(self) -> str:
        return (
            f"<TeacherClassLink id={self.id} "
            f"teacher_id={self.teacher_id} "
            f"class_id={self.class_id}>"
        )


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Short label shown in UI (e.g. "Winter Break")
    title = Column(String(120), nullable=False)

    # Date range (inclusive)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    # "No School", "Teachers Only", or "Custom"
    event_type = Column(String(32), nullable=False, default="Custom")

    # Optional details
    notes = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<CalendarEvent id={self.id} "
            f"title={self.title!r} "
            f"type={self.event_type!r} "
            f"start={self.start_date} end={self.end_date}>"
        )


class TeacherAttendance(Base):
    """
    Per-day attendance for teachers (not tied to classes).

    - One row per (teacher, date) enforced via UniqueConstraint.
    - Status values will mirror the configurable attendance statuses
      (e.g. "Present", "Absent", "No School", etc.).
    - Optional check-in/check-out timestamps are enabled via Settings.
    """
    __tablename__ = "teacher_attendance"

    id = Column(Integer, primary_key=True, autoincrement=True)

    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)

    # Date this attendance record applies to (school day)
    date = Column(Date, nullable=False)

    # e.g. "Present", "Absent", "No School"
    status = Column(String(32), nullable=False, default="")

    # Optional check-in / check-out times (UTC)
    check_in_time = Column(DateTime, nullable=True)
    check_out_time = Column(DateTime, nullable=True)

    # Who marked it (for now, simple text; later could link to AdminUser)
    marked_by = Column(String(120), nullable=True)

    # When this record was last updated/created
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship back to Teacher
    teacher = relationship("Teacher", back_populates="teacher_attendance")

    __table_args__ = (
        UniqueConstraint("teacher_id", "date", name="uq_teacher_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<TeacherAttendance id={self.id} "
            f"teacher_id={self.teacher_id} "
            f"date={self.date} "
            f"status={self.status}>"
        )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Who performed the action (e.g., "Admin", "System")
    actor = Column(String(100), nullable=False)

    # What happened: "create", "update", "delete", etc.
    action = Column(String(50), nullable=False)

    # Which table/entity: "Student", "Teacher", "Class", "Attendance",
    # "CalendarEvent", "TeacherAttendance", etc.
    entity = Column(String(50), nullable=False)

    # Primary key of the record in that entity (can be null for generic actions)
    entity_id = Column(Integer, nullable=True)

    # When the action happened
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    # JSON snapshots of the record before and after the change
    before_json = Column(Text, nullable=True)
    after_json = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} actor={self.actor!r} "
            f"action={self.action!r} entity={self.entity!r} entity_id={self.entity_id}>"
        )


def add_audit_log(
    session,
    actor,
    action,
    entity,
    entity_id,
    before=None,
    after=None,
):
    """
    Convenience helper to create an AuditLog row.

    - session: SQLAlchemy session
    - actor:   "Admin", "System", etc.
    - action:  "create", "update", "delete", ...
    - entity:  model name like "Student", "Teacher", "Class",
               "Attendance", "TeacherAttendance", "CalendarEvent"
    - entity_id: primary key of the affected row (or None)
    - before: dict snapshot of old values (or None)
    - after:  dict snapshot of new values (or None)
    """
    log = AuditLog(
        actor=actor or "System",
        action=action,
        entity=entity,
        entity_id=entity_id,
        timestamp=datetime.utcnow(),
        before_json=json.dumps(before) if before is not None else None,
        after_json=json.dumps(after) if after is not None else None,
    )
    session.add(log)
