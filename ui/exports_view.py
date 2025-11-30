from datetime import date, datetime, timedelta
from pathlib import Path
import csv
import json
import shutil
import os
import sys
import subprocess

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QDateEdit,
    QMessageBox,
    QFileDialog,
    QGroupBox,
    QInputDialog,
)
from PySide6.QtCore import QDate
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from data.models import (
    Student,
    Class,
    Enrollment,
    Attendance,
    AdminUser,
    Teacher,
    TeacherClassLink,
    CalendarEvent,
    TeacherAttendance,
)
from data.security import hash_password, verify_password
from ui.auth_dialogs import ChangePasswordDialog
from data.paths import DB_PATH, EXPORTS_DIR, PHOTOS_DIR

# For backward compatibility with older references in this file
DB_FILE = DB_PATH


class ExportsView(QWidget):
    """
    Exports tab:
    - Roster exports (students/teachers/classes/enrollments, JSON).
    - Printable student/teacher summary PDFs.
    - Attendance exports (single-day CSV + daily bundle).
    - Attendance reports (student/class histories, monthly summary, absence list,
      teacher attendance log).
    - Database backup/restore + full RegisTree backup + change admin password.
    """

    def __init__(self, session, settings=None):
        super().__init__()
        self.session = session
        self.settings = settings

        main_layout = QVBoxLayout()

        # --------------------------------------------------------------
        # Roster Exports
        # --------------------------------------------------------------
        roster_group = QGroupBox("Roster Exports")
        roster_layout = QHBoxLayout()

        self.export_students_button = QPushButton("Export Students CSV")
        self.export_students_button.clicked.connect(self.export_students_csv)
        roster_layout.addWidget(self.export_students_button)

        self.export_students_json_button = QPushButton("Export Students JSON")
        self.export_students_json_button.clicked.connect(self.export_students_json)
        roster_layout.addWidget(self.export_students_json_button)

        self.export_teachers_button = QPushButton("Export Teachers CSV")
        self.export_teachers_button.clicked.connect(self.export_teachers_csv)
        roster_layout.addWidget(self.export_teachers_button)

        self.export_teacher_class_links_button = QPushButton(
            "Export Teacher-Class CSV"
        )
        self.export_teacher_class_links_button.clicked.connect(
            self.export_teacher_class_links_csv
        )
        roster_layout.addWidget(self.export_teacher_class_links_button)

        self.export_classes_button = QPushButton("Export Classes CSV")
        self.export_classes_button.clicked.connect(self.export_classes_csv)
        roster_layout.addWidget(self.export_classes_button)

        self.export_enrollments_button = QPushButton("Export Enrollments CSV")
        self.export_enrollments_button.clicked.connect(self.export_enrollments_csv)
        roster_layout.addWidget(self.export_enrollments_button)

        # Calendar Events CSV
        self.export_calendar_events_button = QPushButton("Export Calendar Events CSV")
        self.export_calendar_events_button.clicked.connect(
            self.export_calendar_events_csv
        )
        roster_layout.addWidget(self.export_calendar_events_button)

        # Printable summaries
        self.student_summary_pdf_button = QPushButton("Student Summary PDF…")
        self.student_summary_pdf_button.clicked.connect(
            self.export_student_summary_pdf
        )
        roster_layout.addWidget(self.student_summary_pdf_button)

        self.teacher_summary_pdf_button = QPushButton("Teacher Summary PDF…")
        self.teacher_summary_pdf_button.clicked.connect(
            self.export_teacher_summary_pdf
        )
        roster_layout.addWidget(self.teacher_summary_pdf_button)

        roster_layout.addStretch()
        roster_group.setLayout(roster_layout)
        main_layout.addWidget(roster_group)

        # --------------------------------------------------------------
        # Attendance & Daily Bundle
        # --------------------------------------------------------------
        attendance_group = QGroupBox("Attendance & Daily Bundle")
        attendance_layout = QHBoxLayout()

        attendance_layout.addWidget(QLabel("Date:"))

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        attendance_layout.addWidget(self.date_edit)

        self.export_attendance_button = QPushButton("Export Attendance CSV")
        self.export_attendance_button.clicked.connect(self.export_attendance_csv)
        attendance_layout.addWidget(self.export_attendance_button)

        self.bundle_button = QPushButton("Generate Daily Bundle")
        self.bundle_button.clicked.connect(self.generate_daily_bundle)
        attendance_layout.addWidget(self.bundle_button)

        attendance_layout.addStretch()
        attendance_group.setLayout(attendance_layout)
        main_layout.addWidget(attendance_group)

        # --------------------------------------------------------------
        # Attendance Reports (range-based)
        # --------------------------------------------------------------
        reports_group = QGroupBox("Attendance Reports")
        reports_layout = QVBoxLayout()

        # Date range row
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("From:"))
        self.range_start_edit = QDateEdit()
        self.range_start_edit.setCalendarPopup(True)
        self.range_start_edit.setDate(QDate.currentDate())
        range_layout.addWidget(self.range_start_edit)

        range_layout.addWidget(QLabel("To:"))
        self.range_end_edit = QDateEdit()
        self.range_end_edit.setCalendarPopup(True)
        self.range_end_edit.setDate(QDate.currentDate())
        range_layout.addWidget(self.range_end_edit)

        range_layout.addStretch()
        reports_layout.addLayout(range_layout)

        # Student attendance reports
        stud_row = QHBoxLayout()
        stud_row.addWidget(QLabel("Student Attendance:"))
        self.student_att_csv_button = QPushButton("CSV…")
        self.student_att_csv_button.clicked.connect(
            self.export_student_attendance_csv
        )
        stud_row.addWidget(self.student_att_csv_button)

        self.student_att_pdf_button = QPushButton("PDF…")
        self.student_att_pdf_button.clicked.connect(
            self.export_student_attendance_pdf
        )
        stud_row.addWidget(self.student_att_pdf_button)
        stud_row.addStretch()
        reports_layout.addLayout(stud_row)

        # Class attendance reports
        class_row = QHBoxLayout()
        class_row.addWidget(QLabel("Class Attendance:"))
        self.class_att_csv_button = QPushButton("CSV…")
        self.class_att_csv_button.clicked.connect(self.export_class_attendance_csv)
        class_row.addWidget(self.class_att_csv_button)

        self.class_att_pdf_button = QPushButton("PDF…")
        self.class_att_pdf_button.clicked.connect(self.export_class_attendance_pdf)
        class_row.addWidget(self.class_att_pdf_button)
        class_row.addStretch()
        reports_layout.addLayout(class_row)

        # Teacher attendance reports (per teacher, range-based)
        teacher_row = QHBoxLayout()
        teacher_row.addWidget(QLabel("Teacher Attendance:"))

        self.teacher_att_range_csv_button = QPushButton("CSV…")
        self.teacher_att_range_csv_button.clicked.connect(
            self.export_teacher_attendance_range_csv
        )
        teacher_row.addWidget(self.teacher_att_range_csv_button)

        self.teacher_att_range_pdf_button = QPushButton("PDF…")
        self.teacher_att_range_pdf_button.clicked.connect(
            self.export_teacher_attendance_range_pdf
        )
        teacher_row.addWidget(self.teacher_att_range_pdf_button)

        teacher_row.addStretch()
        reports_layout.addLayout(teacher_row)

        # Monthly summary (for month of "From" date)
        month_row = QHBoxLayout()
        month_row.addWidget(QLabel("Monthly Summary (PDF):"))
        self.monthly_summary_button = QPushButton("Generate PDF")
        self.monthly_summary_button.clicked.connect(self.export_monthly_summary_pdf)
        month_row.addWidget(self.monthly_summary_button)
        month_row.addStretch()
        reports_layout.addLayout(month_row)

        # Absence list
        absence_row = QHBoxLayout()
        absence_row.addWidget(QLabel("Absence List (CSV):"))
        self.absence_list_button = QPushButton("Generate CSV")
        self.absence_list_button.clicked.connect(self.export_absence_list_csv)
        absence_row.addWidget(self.absence_list_button)
        absence_row.addStretch()
        reports_layout.addLayout(absence_row)

        # Teacher attendance log (all teachers, all dates)
        teacher_att_row = QHBoxLayout()
        teacher_att_row.addWidget(QLabel("Teacher Attendance Log (CSV):"))
        self.teacher_att_log_button = QPushButton("Export CSV")
        self.teacher_att_log_button.clicked.connect(
            self.export_teacher_attendance_log_csv
        )
        teacher_att_row.addWidget(self.teacher_att_log_button)
        teacher_att_row.addStretch()
        reports_layout.addLayout(teacher_att_row)

        reports_group.setLayout(reports_layout)
        main_layout.addWidget(reports_group)

        # --------------------------------------------------------------
        # Database backup/restore
        # --------------------------------------------------------------
        db_group = QGroupBox("Database Backup / Restore")
        db_layout = QHBoxLayout()

        self.backup_button = QPushButton("Backup Database…")
        self.backup_button.clicked.connect(self.backup_database)
        db_layout.addWidget(self.backup_button)

        self.full_backup_button = QPushButton("Full RegisTree Backup…")
        self.full_backup_button.clicked.connect(self.full_registree_backup)
        db_layout.addWidget(self.full_backup_button)

        self.restore_button = QPushButton("Restore Database…")
        self.restore_button.clicked.connect(self.restore_database)
        db_layout.addWidget(self.restore_button)

        self.change_pw_button = QPushButton("Change Admin Password…")
        self.change_pw_button.clicked.connect(self.change_admin_password)
        db_layout.addWidget(self.change_pw_button)

        # NEW: Open Exports Folder button
        self.open_exports_button = QPushButton("Open Exports Folder")
        self.open_exports_button.clicked.connect(self.open_exports_folder)
        db_layout.addWidget(self.open_exports_button)

        db_layout.addStretch()
        db_group.setLayout(db_layout)
        main_layout.addWidget(db_group)

        self.setLayout(main_layout)

    # ------------------------------------------------------------------
    # Helpers for paths
    # ------------------------------------------------------------------
    def _get_exports_dir(self) -> Path:
        """
        Base exports folder.

        Priority:
        1) settings.export_base_dir (if set)
        2) EXPORTS_DIR from data.paths (DATA_ROOT/exports)
        """
        if self.settings is not None and getattr(
            self.settings, "export_base_dir", None
        ):
            base = Path(self.settings.export_base_dir)
        else:
            base = EXPORTS_DIR

        base.mkdir(parents=True, exist_ok=True)
        return base

    def _subdir(self, *parts: str) -> Path:
        """
        Create (if needed) and return a subdirectory inside the base exports dir.
        Example: _subdir("rosters", "students") -> <exports>/rosters/students/
        """
        d = self._get_exports_dir()
        for p in parts:
            d = d / p
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _get_date_dir(self, att_date: date) -> Path:
        """
        Folder for a specific date bundle:
        e.g. <base>/daily_bundles/2025-11-25/
        """
        out_dir = self._subdir("daily_bundles", att_date.isoformat())
        return out_dir

    def _get_range(self):
        """Return (start_date, end_date) from the range pickers, or None if invalid."""
        qs = self.range_start_edit.date()
        qe = self.range_end_edit.date()
        start = date(qs.year(), qs.month(), qs.day())
        end = date(qe.year(), qe.month(), qe.day())
        if start > end:
            QMessageBox.warning(
                self,
                "Date Range",
                "The 'From' date must be on or before the 'To' date.",
            )
            return None, None
        return start, end

    # ------------------------------------------------------------------
    # STUDENTS: CSV
    # ------------------------------------------------------------------
    def export_students_csv(self):
        out_dir = self._subdir("rosters", "students")
        file_path = out_dir / "students.csv"

        students = (
            self.session.query(Student)
            .order_by(Student.last_name, Student.first_name)
            .all()
        )

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "first_name",
                    "last_name",
                    "dob",
                    "grade_level",
                    "contact_email",
                    "guardian_name",
                    "guardian_phone",
                    "guardian_email",
                    "emergency_contact_name",
                    "emergency_contact_phone",
                    "status",
                    "notes",
                ]
            )

            for s in students:
                writer.writerow(
                    [
                        s.id,
                        s.first_name or "",
                        s.last_name or "",
                        s.dob.isoformat() if s.dob else "",
                        s.grade_level or "",
                        s.contact_email or "",
                        s.guardian_name or "",
                        s.guardian_phone or "",
                        getattr(s, "guardian_email", "") or "",
                        getattr(s, "emergency_contact_name", "") or "",
                        getattr(s, "emergency_contact_phone", "") or "",
                        s.status or "",
                        (s.notes or "").replace("\n", " "),
                    ]
                )

        QMessageBox.information(
            self,
            "Export Students CSV",
            f"Exported {len(students)} students to:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # STUDENTS: JSON snapshot
    # ------------------------------------------------------------------
    def _export_students_json_to(self, out_dir: Path) -> int:
        """Helper: write students.json to a given folder, return count."""
        file_path = out_dir / "students.json"

        students = (
            self.session.query(Student)
            .order_by(Student.last_name, Student.first_name)
            .all()
        )

        data = []
        for s in students:
            data.append(
                {
                    "id": s.id,
                    "first_name": s.first_name,
                    "last_name": s.last_name,
                    "dob": s.dob.isoformat() if s.dob else None,
                    "grade_level": s.grade_level,
                    "contact_email": s.contact_email,
                    "guardian_name": s.guardian_name,
                    "guardian_phone": s.guardian_phone,
                    "guardian_email": getattr(s, "guardian_email", None),
                    "emergency_contact_name": getattr(
                        s, "emergency_contact_name", None
                    ),
                    "emergency_contact_phone": getattr(
                        s, "emergency_contact_phone", None
                    ),
                    "status": s.status,
                    "notes": s.notes,
                }
            )

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return len(students)

    def export_students_json(self):
        out_dir = self._subdir("rosters", "students")
        count = self._export_students_json_to(out_dir)
        file_path = out_dir / "students.json"

        QMessageBox.information(
            self,
            "Export Students JSON",
            f"Exported {count} students to JSON:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # TEACHERS: CSV
    # ------------------------------------------------------------------
    def export_teachers_csv(self):
        out_dir = self._subdir("rosters", "teachers")
        file_path = out_dir / "teachers.csv"

        teachers = (
            self.session.query(Teacher)
            .order_by(Teacher.last_name, Teacher.first_name)
            .all()
        )

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "first_name",
                    "last_name",
                    "phone",
                    "email",
                    "emergency_contact_name",
                    "emergency_contact_phone",
                    "status",
                    "notes",
                ]
            )

            for t in teachers:
                writer.writerow(
                    [
                        t.id,
                        t.first_name or "",
                        t.last_name or "",
                        t.phone or "",
                        t.email or "",
                        getattr(t, "emergency_contact_name", "") or "",
                        getattr(t, "emergency_contact_phone", "") or "",
                        t.status or "",
                        (t.notes or "").replace("\n", " "),
                    ]
                )

        QMessageBox.information(
            self,
            "Export Teachers CSV",
            f"Exported {len(teachers)} teachers to:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # TEACHER-CLASS LINKS: CSV
    # ------------------------------------------------------------------
    def export_teacher_class_links_csv(self):
        out_dir = self._subdir("rosters", "teachers")
        file_path = out_dir / "teacher_class_links.csv"

        links = self.session.query(TeacherClassLink).all()

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "teacher_id",
                    "teacher_name",
                    "class_id",
                    "class_name",
                    "class_term",
                ]
            )

            for link in links:
                t = link.teacher
                c = link.clazz
                teacher_name = ""
                if t is not None:
                    teacher_name = f"{t.first_name or ''} {t.last_name or ''}".strip()
                class_name = c.name if c is not None else ""
                class_term = c.term if c is not None else ""
                writer.writerow(
                    [
                        link.id,
                        link.teacher_id,
                        teacher_name,
                        link.class_id,
                        class_name,
                        class_term,
                    ]
                )

        QMessageBox.information(
            self,
            "Export Teacher-Class CSV",
            f"Exported {len(links)} teacher-class links to:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # CLASSES: CSV
    # ------------------------------------------------------------------
    def export_classes_csv(self):
        out_dir = self._subdir("rosters", "classes")
        file_path = out_dir / "classes.csv"

        classes = self.session.query(Class).order_by(Class.name).all()

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # We export a single 'teachers' column that lists linked teachers
            # as "id:First Last; id:First Last".
            writer.writerow(
                [
                    "id",
                    "name",
                    "subject",
                    "teachers",  # derived from TeacherClassLink
                    "term",
                    "room",
                ]
            )

            for c in classes:
                teacher_pairs = []
                for link in c.teacher_links:
                    if link.teacher:
                        t = link.teacher
                        full_name = f"{t.first_name or ''} {t.last_name or ''}".strip()
                        teacher_pairs.append(f"{t.id}:{full_name}")
                teachers_field = "; ".join(teacher_pairs)

                writer.writerow(
                    [
                        c.id,
                        c.name or "",
                        c.subject or "",
                        teachers_field,
                        c.term or "",
                        c.room or "",
                    ]
                )

        QMessageBox.information(
            self,
            "Export Classes CSV",
            f"Exported {len(classes)} classes to:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # ENROLLMENTS: CSV
    # ------------------------------------------------------------------
    def export_enrollments_csv(self):
        out_dir = self._subdir("rosters", "enrollments")
        file_path = out_dir / "enrollments.csv"

        enrollments = (
            self.session.query(Enrollment, Student, Class)
            .join(Student, Enrollment.student_id == Student.id)
            .join(Class, Enrollment.class_id == Class.id)
            .all()
        )

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "student_id",
                    "student_first_name",
                    "student_last_name",
                    "class_id",
                    "class_name",
                    "class_term",
                    "start_date",
                    "end_date",
                ]
            )

            for e, s, c in enrollments:
                writer.writerow(
                    [
                        e.id,
                        s.id,
                        s.first_name or "",
                        s.last_name or "",
                        c.id,
                        c.name or "",
                        c.term or "",
                        e.start_date.isoformat() if e.start_date else "",
                        e.end_date.isoformat() if e.end_date else "",
                    ]
                )

        QMessageBox.information(
            self,
            "Export Enrollments CSV",
            f"Exported {len(enrollments)} enrollments to:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # CALENDAR EVENTS: CSV
    # ------------------------------------------------------------------
    def export_calendar_events_csv(self):
        """
        Export all calendar events to a CSV file in:
        <exports>/calendar/events/calendar_events.csv
        (or under the user-configured export base directory).
        """
        out_dir = self._subdir("calendar", "events")
        file_path = out_dir / "calendar_events.csv"

        events = (
            self.session.query(CalendarEvent)
            .order_by(CalendarEvent.start_date, CalendarEvent.end_date, CalendarEvent.title)
            .all()
        )

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "title",
                    "event_type",
                    "start_date",
                    "end_date",
                    "notes",
                ]
            )

            for ev in events:
                writer.writerow(
                    [
                        ev.id,
                        ev.title or "",
                        ev.event_type or "",
                        ev.start_date.isoformat() if ev.start_date else "",
                        ev.end_date.isoformat() if ev.end_date else "",
                        (ev.notes or "").replace("\n", " "),
                    ]
                )

        QMessageBox.information(
            self,
            "Export Calendar Events",
            f"Exported {len(events)} calendar events to:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # ATTENDANCE: CSV (single date, students)
    # ------------------------------------------------------------------
    def _export_attendance_csv_to(self, out_dir: Path, att_date: date) -> int:
        """Helper: write student attendance_DATE.csv into out_dir, return count."""
        file_path = out_dir / f"attendance_{att_date.isoformat()}.csv"

        records = (
            self.session.query(Attendance, Student, Class)
            .join(Student, Attendance.student_id == Student.id)
            .join(Class, Attendance.class_id == Class.id)
            .filter(Attendance.date == att_date)
            .order_by(Class.name, Student.last_name, Student.first_name)
            .all()
        )

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "student_id",
                    "student_first_name",
                    "student_last_name",
                    "class_id",
                    "class_name",
                    "class_term",
                    "date",
                    "status",
                    "marked_by",
                    "timestamp",
                ]
            )

            for a, s, c in records:
                writer.writerow(
                    [
                        a.id,
                        s.id,
                        s.first_name or "",
                        s.last_name or "",
                        c.id,
                        c.name or "",
                        c.term or "",
                        a.date.isoformat() if a.date else "",
                        a.status or "",
                        a.marked_by or "",
                        a.timestamp.isoformat() if a.timestamp else "",
                    ]
                )

        return len(records)

    # ------------------------------------------------------------------
    # TEACHER ATTENDANCE: CSV (single date, helper for bundle)
    # ------------------------------------------------------------------
    def _export_teacher_attendance_csv_to(self, out_dir: Path, att_date: date) -> int:
        """
        Helper: write teacher_attendance_DATE.csv into out_dir, return count.
        """
        file_path = out_dir / f"teacher_attendance_{att_date.isoformat()}.csv"

        records = (
            self.session.query(TeacherAttendance, Teacher)
            .join(Teacher, TeacherAttendance.teacher_id == Teacher.id)
            .filter(TeacherAttendance.date == att_date)
            .order_by(Teacher.last_name, Teacher.first_name, TeacherAttendance.id)
            .all()
        )

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "teacher_id",
                    "teacher_first_name",
                    "teacher_last_name",
                    "date",
                    "status",
                    "check_in_time",
                    "check_out_time",
                    "marked_by",
                    "timestamp",
                ]
            )

            for ta, t in records:
                writer.writerow(
                    [
                        ta.id,
                        t.id,
                        t.first_name or "",
                        t.last_name or "",
                        ta.date.isoformat() if ta.date else "",
                        ta.status or "",
                        ta.check_in_time.isoformat()
                        if ta.check_in_time
                        else "",
                        ta.check_out_time.isoformat()
                        if ta.check_out_time
                        else "",
                        ta.marked_by or "",
                        ta.timestamp.isoformat() if ta.timestamp else "",
                    ]
                )

        return len(records)

    def export_attendance_csv(self):
        out_dir = self._subdir("attendance", "daily")

        qd = self.date_edit.date()
        att_date = date(qd.year(), qd.month(), qd.day())

        count = self._export_attendance_csv_to(out_dir, att_date)
        file_path = out_dir / f"attendance_{att_date.isoformat()}.csv"

        QMessageBox.information(
            self,
            "Export Attendance CSV",
            f"Exported {count} attendance records for {att_date} to:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # PDF summary for a given date (daily bundle)
    # ------------------------------------------------------------------
    def _export_summary_pdf(self, out_dir: Path, att_date: date):
        """Create a simple PDF summary for the given date."""
        file_path = out_dir / f"summary_{att_date.isoformat()}.pdf"

        # Basic stats
        total_students = self.session.query(Student).count()
        total_classes = self.session.query(Class).count()
        total_teachers = self.session.query(Teacher).count()

        # Student attendance records
        stu_records = (
            self.session.query(Attendance)
            .filter(Attendance.date == att_date)
            .all()
        )
        total_attendance_records = len(stu_records)

        # Teacher attendance records
        teach_records = (
            self.session.query(TeacherAttendance)
            .filter(TeacherAttendance.date == att_date)
            .all()
        )
        total_teacher_att_records = len(teach_records)

        # Count student attendance by status, **unique per (student, date, status)**
        student_status_counts: dict[str, int] = {}
        seen_student_keys = set()
        for a in stu_records:
            status_label = (a.status or "").strip() or "(blank)"
            key = (a.student_id, a.date, status_label)
            if key in seen_student_keys:
                continue
            seen_student_keys.add(key)
            student_status_counts[status_label] = student_status_counts.get(status_label, 0) + 1

        # Count teacher attendance by status, **unique per (teacher, date, status)**
        teacher_status_counts: dict[str, int] = {}
        seen_teacher_keys = set()
        for ta in teach_records:
            status_label = (ta.status or "").strip() or "(blank)"
            key = (ta.teacher_id, ta.date, status_label)
            if key in seen_teacher_keys:
                continue
            seen_teacher_keys.add(key)
            teacher_status_counts[status_label] = teacher_status_counts.get(status_label, 0) + 1

        # Create PDF
        c = canvas.Canvas(str(file_path), pagesize=letter)
        width, height = letter

        y = height - 72  # 1 inch margin from top

        c.setFont("Helvetica-Bold", 16)
        c.drawString(72, y, f"RegisTree Daily Summary - {att_date.isoformat()}")
        y -= 36

        c.setFont("Helvetica", 12)
        c.drawString(72, y, f"Total Students: {total_students}")
        y -= 20
        c.drawString(72, y, f"Total Classes: {total_classes}")
        y -= 20
        c.drawString(72, y, f"Total Teachers: {total_teachers}")
        y -= 20
        c.drawString(
            72,
            y,
            f"Student Attendance Records (raw rows): {total_attendance_records}",
        )
        y -= 20
        c.drawString(
            72,
            y,
            f"Teacher Attendance Records (raw rows): {total_teacher_att_records}",
        )
        y -= 30

        # Student status summary
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Unique Student Attendance by Status:")
        y -= 20

        c.setFont("Helvetica", 12)
        if student_status_counts:
            for status, count in student_status_counts.items():
                c.drawString(90, y, f"{status}: {count}")
                y -= 18
        else:
            c.drawString(90, y, "No student attendance records for this date.")
            y -= 18

        y -= 20

        # Teacher status summary
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Unique Teacher Attendance by Status:")
        y -= 20

        c.setFont("Helvetica", 12)
        if teacher_status_counts:
            for status, count in teacher_status_counts.items():
                c.drawString(90, y, f"{status}: {count}")
                y -= 18
        else:
            c.drawString(90, y, "No teacher attendance records for this date.")
            y -= 18

        c.showPage()
        c.save()

    # ------------------------------------------------------------------
    # Generate daily bundle (students.json + attendance CSVs + PDF)
    # ------------------------------------------------------------------
    def generate_daily_bundle(self):
        qd = self.date_edit.date()
        att_date = date(qd.year(), qd.month(), qd.day())

        out_dir = self._get_date_dir(att_date)

        # 1) Students JSON snapshot
        students_count = self._export_students_json_to(out_dir)

        # 2) Student Attendance CSV for that date
        attendance_count = self._export_attendance_csv_to(out_dir, att_date)

        # 3) Teacher Attendance CSV for that date
        teacher_attendance_count = self._export_teacher_attendance_csv_to(out_dir, att_date)

        # 4) PDF summary (students + teachers)
        self._export_summary_pdf(out_dir, att_date)

        QMessageBox.information(
            self,
            "Daily Bundle",
            (
                f"Generated daily bundle for {att_date} in:\n{out_dir}\n\n"
                f"Students in JSON: {students_count}\n"
                f"Student attendance records (rows): {attendance_count}\n"
                f"Teacher attendance records (rows): {teacher_attendance_count}\n"
                f"PDF summary: summary_{att_date.isoformat()}.pdf"
            ),
        )

    # ------------------------------------------------------------------
    # Printable Student / Teacher summary PDFs
    # ------------------------------------------------------------------
    def export_student_summary_pdf(self):
        student_id, ok = QInputDialog.getInt(
            self, "Student Summary", "Enter Student ID:", 1, 1
        )
        if not ok:
            return

        student = self.session.get(Student, student_id)
        if student is None:
            QMessageBox.warning(
                self, "Student Summary", f"Student ID {student_id} not found."
            )
            return

        out_dir = self._subdir("summaries", "students")
        file_path = out_dir / f"student_{student_id}_summary.pdf"

        c = canvas.Canvas(str(file_path), pagesize=letter)
        width, height = letter
        y = height - 72

        c.setFont("Helvetica-Bold", 16)
        c.drawString(72, y, f"Student Summary - ID {student.id}")
        y -= 30

        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Basic Information")
        y -= 18
        c.setFont("Helvetica", 11)
        c.drawString(
            90, y, f"Name: {student.first_name or ''} {student.last_name or ''}"
        )
        y -= 16
        c.drawString(90, y, f"Grade: {student.grade_level or ''}")
        y -= 16
        c.drawString(90, y, f"Status: {student.status or ''}")
        y -= 16
        c.drawString(
            90,
            y,
            f"DOB: {student.dob.isoformat() if student.dob else ''}",
        )
        y -= 16
        c.drawString(90, y, f"Email: {student.contact_email or ''}")
        y -= 24

        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Guardian & Emergency Contacts")
        y -= 18
        c.setFont("Helvetica", 11)
        c.drawString(90, y, f"Guardian: {student.guardian_name or ''}")
        y -= 16
        c.drawString(90, y, f"Guardian Phone: {student.guardian_phone or ''}")
        y -= 16
        c.drawString(
            90,
            y,
            f"Guardian Email: {getattr(student, 'guardian_email', '') or ''}",
        )
        y -= 16
        c.drawString(
            90,
            y,
            f"Emergency Contact: {getattr(student, 'emergency_contact_name', '') or ''}",
        )
        y -= 16
        c.drawString(
            90,
            y,
            "Emergency Phone: "
            f"{getattr(student, 'emergency_contact_phone', '') or ''}",
        )
        y -= 24

        # Classes
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Classes")
        y -= 18
        c.setFont("Helvetica", 11)

        enrolls = (
            self.session.query(Enrollment, Class)
            .join(Class, Enrollment.class_id == Class.id)
            .filter(Enrollment.student_id == student.id)
            .order_by(Class.term, Class.name)
            .all()
        )
        if enrolls:
            for e, cl in enrolls:
                text = (
                    f"{cl.name or ''} | {cl.subject or ''} | "
                    f"{cl.term or ''} | "
                    f"{e.start_date.isoformat() if e.start_date else ''} - "
                    f"{e.end_date.isoformat() if e.end_date else ''}"
                )
                c.drawString(90, y, text)
                y -= 14
                if y < 72:
                    c.showPage()
                    y = height - 72
                    c.setFont("Helvetica", 11)
        else:
            c.drawString(90, y, "No enrollments found.")
            y -= 16

        # Notes
        y -= 16
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Notes")
        y -= 18
        c.setFont("Helvetica", 11)
        notes = student.notes or ""
        for line in notes.splitlines() or ["(none)"]:
            c.drawString(90, y, line)
            y -= 14
            if y < 72:
                c.showPage()
                y = height - 72
                c.setFont("Helvetica", 11)

        c.showPage()
        c.save()

        QMessageBox.information(
            self,
            "Student Summary",
            f"Student summary PDF created:\n{file_path}",
        )

    def export_teacher_summary_pdf(self):
        teacher_id, ok = QInputDialog.getInt(
            self, "Teacher Summary", "Enter Teacher ID:", 1, 1
        )
        if not ok:
            return

        teacher = self.session.get(Teacher, teacher_id)
        if teacher is None:
            QMessageBox.warning(
                self, "Teacher Summary", f"Teacher ID {teacher_id} not found."
            )
            return

        out_dir = self._subdir("summaries", "teachers")
        file_path = out_dir / f"teacher_{teacher_id}_summary.pdf"

        c = canvas.Canvas(str(file_path), pagesize=letter)
        width, height = letter
        y = height - 72

        c.setFont("Helvetica-Bold", 16)
        c.drawString(72, y, f"Teacher Summary - ID {teacher.id}")
        y -= 30

        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Basic Information")
        y -= 18
        c.setFont("Helvetica", 11)
        c.drawString(
            90, y, f"Name: {teacher.first_name or ''} {teacher.last_name or ''}"
        )
        y -= 16
        c.drawString(90, y, f"Status: {teacher.status or ''}")
        y -= 16
        c.drawString(90, y, f"Phone: {teacher.phone or ''}")
        y -= 16
        c.drawString(90, y, f"Email: {teacher.email or ''}")
        y -= 24

        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Emergency Contact")
        y -= 18
        c.setFont("Helvetica", 11)
        c.drawString(
            90,
            y,
            f"Name: {getattr(teacher, 'emergency_contact_name', '') or ''}",
        )
        y -= 16
        c.drawString(
            90,
            y,
            f"Phone: {getattr(teacher, 'emergency_contact_phone', '') or ''}",
        )
        y -= 24

        # Classes
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Classes")
        y -= 18
        c.setFont("Helvetica", 11)

        links = (
            self.session.query(TeacherClassLink)
            .filter(TeacherClassLink.teacher_id == teacher.id)
            .all()
        )
        if links:
            for link in links:
                cl = link.clazz
                if cl is None:
                    continue
                text = (
                    f"{cl.name or ''} | {cl.subject or ''} | "
                    f"{cl.term or ''} | Room {cl.room or ''}"
                )
                c.drawString(90, y, text)
                y -= 14
                if y < 72:
                    c.showPage()
                    y = height - 72
                    c.setFont("Helvetica", 11)
        else:
            c.drawString(90, y, "No classes assigned.")
            y -= 16

        # Notes
        y -= 16
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Notes")
        y -= 18
        c.setFont("Helvetica", 11)
        notes = teacher.notes or ""
        for line in notes.splitlines() or ["(none)"]:
            c.drawString(90, y, line)
            y -= 14
            if y < 72:
                c.showPage()
                y = height - 72
                c.setFont("Helvetica", 11)

        c.showPage()
        c.save()

        QMessageBox.information(
            self,
            "Teacher Summary",
            f"Teacher summary PDF created:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # Attendance Reports: Student / Class histories, monthly summary, absence list
    # ------------------------------------------------------------------
    def export_student_attendance_csv(self):
        start, end = self._get_range()
        if start is None:
            return

        student_id, ok = QInputDialog.getInt(
            self, "Student Attendance", "Enter Student ID:", 1, 1
        )
        if not ok:
            return

        student = self.session.get(Student, student_id)
        if student is None:
            QMessageBox.warning(
                self,
                "Student Attendance",
                f"Student ID {student_id} not found.",
            )
            return

        out_dir = self._subdir("reports", "attendance", "students")
        file_path = out_dir / f"student_{student_id}_attendance_{start}_{end}.csv"

        records = (
            self.session.query(Attendance, Class)
            .join(Class, Attendance.class_id == Class.id)
            .filter(
                Attendance.student_id == student_id,
                Attendance.date >= start,
                Attendance.date <= end,
            )
            .order_by(Attendance.date, Class.name)
            .all()
        )

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "student_id",
                    "student_first_name",
                    "student_last_name",
                    "date",
                    "class_id",
                    "class_name",
                    "class_term",
                    "status",
                    "marked_by",
                    "timestamp",
                ]
            )
            for a, cl in records:
                writer.writerow(
                    [
                        student.id,
                        student.first_name or "",
                        student.last_name or "",
                        a.date.isoformat() if a.date else "",
                        cl.id if cl else "",
                        cl.name if cl else "",
                        cl.term if cl else "",
                        a.status or "",
                        a.marked_by or "",
                        a.timestamp.isoformat() if a.timestamp else "",
                    ]
                )

        QMessageBox.information(
            self,
            "Student Attendance",
            f"Exported {len(records)} records to:\n{file_path}",
        )

    def export_student_attendance_pdf(self):
        start, end = self._get_range()
        if start is None:
            return

        student_id, ok = QInputDialog.getInt(
            self, "Student Attendance PDF", "Enter Student ID:", 1, 1
        )
        if not ok:
            return

        student = self.session.get(Student, student_id)
        if student is None:
            QMessageBox.warning(
                self,
                "Student Attendance PDF",
                f"Student ID {student_id} not found.",
            )
            return

        out_dir = self._subdir("reports", "attendance", "students")
        file_path = out_dir / f"student_{student_id}_attendance_{start}_{end}.pdf"

        records = (
            self.session.query(Attendance, Class)
            .join(Class, Attendance.class_id == Class.id)
            .filter(
                Attendance.student_id == student_id,
                Attendance.date >= start,
                Attendance.date <= end,
            )
            .order_by(Attendance.date, Class.name)
            .all()
        )

        c = canvas.Canvas(str(file_path), pagesize=letter)
        width, height = letter
        y = height - 72

        c.setFont("Helvetica-Bold", 16)
        c.drawString(
            72,
            y,
            f"Student Attendance - {student.first_name} {student.last_name}",
        )
        y -= 24
        c.setFont("Helvetica", 11)
        c.drawString(72, y, f"ID: {student.id}")
        y -= 14
        c.drawString(72, y, f"Range: {start} to {end}")
        y -= 24

        c.setFont("Helvetica-Bold", 11)
        c.drawString(72, y, "Date")
        c.drawString(150, y, "Class")
        c.drawString(340, y, "Term")
        c.drawString(420, y, "Status")
        y -= 16
        c.setFont("Helvetica", 10)

        if records:
            for a, cl in records:
                if y < 72:
                    c.showPage()
                    y = height - 72
                    c.setFont("Helvetica-Bold", 11)
                    c.drawString(72, y, "Date")
                    c.drawString(150, y, "Class")
                    c.drawString(340, y, "Term")
                    c.drawString(420, y, "Status")
                    y -= 16
                    c.setFont("Helvetica", 10)

                c.drawString(
                    72,
                    y,
                    a.date.isoformat() if a.date else "",
                )
                c.drawString(150, y, (cl.name or "") if cl else "")
                c.drawString(340, y, (cl.term or "") if cl else "")
                c.drawString(420, y, a.status or "")
                y -= 14
        else:
            c.drawString(72, y, "No attendance records in this range.")
            y -= 14

        c.showPage()
        c.save()

        QMessageBox.information(
            self,
            "Student Attendance PDF",
            f"Student attendance PDF created:\n{file_path}",
        )

    def export_class_attendance_csv(self):
        start, end = self._get_range()
        if start is None:
            return

        class_id, ok = QInputDialog.getInt(
            self, "Class Attendance", "Enter Class ID:", 1, 1
        )
        if not ok:
            return

        clazz = self.session.get(Class, class_id)
        if clazz is None:
            QMessageBox.warning(
                self, "Class Attendance", f"Class ID {class_id} not found."
            )
            return

        out_dir = self._subdir("reports", "attendance", "classes")
        file_path = out_dir / f"class_{class_id}_attendance_{start}_{end}.csv"

        records = (
            self.session.query(Attendance, Student)
            .join(Student, Attendance.student_id == Student.id)
            .filter(
                Attendance.class_id == class_id,
                Attendance.date >= start,
                Attendance.date <= end,
            )
            .order_by(Attendance.date, Student.last_name, Student.first_name)
            .all()
        )

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "class_id",
                    "class_name",
                    "class_term",
                    "date",
                    "student_id",
                    "student_first_name",
                    "student_last_name",
                    "status",
                    "marked_by",
                    "timestamp",
                ]
            )
            for a, s in records:
                writer.writerow(
                    [
                        clazz.id,
                        clazz.name or "",
                        clazz.term or "",
                        a.date.isoformat() if a.date else "",
                        s.id,
                        s.first_name or "",
                        s.last_name or "",
                        a.status or "",
                        a.marked_by or "",
                        a.timestamp.isoformat() if a.timestamp else "",
                    ]
                )

        QMessageBox.information(
            self,
            "Class Attendance",
            f"Exported {len(records)} records to:\n{file_path}",
        )

    def export_class_attendance_pdf(self):
        start, end = self._get_range()
        if start is None:
            return

        class_id, ok = QInputDialog.getInt(
            self, "Class Attendance PDF", "Enter Class ID:", 1, 1
        )
        if not ok:
            return

        clazz = self.session.get(Class, class_id)
        if clazz is None:
            QMessageBox.warning(
                self, "Class Attendance PDF", f"Class ID {class_id} not found."
            )
            return

        out_dir = self._subdir("reports", "attendance", "classes")
        file_path = out_dir / f"class_{class_id}_attendance_{start}_{end}.pdf"

        records = (
            self.session.query(Attendance, Student)
            .join(Student, Attendance.student_id == Student.id)
            .filter(
                Attendance.class_id == class_id,
                Attendance.date >= start,
                Attendance.date <= end,
            )
            .order_by(Attendance.date, Student.last_name, Student.first_name)
            .all()
        )

        c = canvas.Canvas(str(file_path), pagesize=letter)
        width, height = letter
        y = height - 72

        c.setFont("Helvetica-Bold", 16)
        c.drawString(
            72,
            y,
            f"Class Attendance - {clazz.name or ''} ({clazz.term or ''})",
        )
        y -= 24
        c.setFont("Helvetica", 11)
        c.drawString(72, y, f"ID: {clazz.id}")
        y -= 14
        c.drawString(72, y, f"Range: {start} to {end}")
        y -= 24

        c.setFont("Helvetica-Bold", 11)
        c.drawString(72, y, "Date")
        c.drawString(150, y, "Student")
        c.drawString(340, y, "Status")
        y -= 16
        c.setFont("Helvetica", 10)

        if records:
            for a, s in records:
                if y < 72:
                    c.showPage()
                    y = height - 72
                    c.setFont("Helvetica-Bold", 11)
                    c.drawString(72, y, "Date")
                    c.drawString(150, y, "Student")
                    c.drawString(340, y, "Status")
                    y -= 16
                    c.setFont("Helvetica", 10)

                c.drawString(
                    72,
                    y,
                    a.date.isoformat() if a.date else "",
                )
                c.drawString(
                    150,
                    y,
                    f"{s.last_name or ''}, {s.first_name or ''}",
                )
                c.drawString(340, y, a.status or "")
                y -= 14
        else:
            c.drawString(72, y, "No attendance records in this range.")
            y -= 14

        c.showPage()
        c.save()

        QMessageBox.information(
            self,
            "Class Attendance PDF",
            f"Class attendance PDF created:\n{file_path}",
        )

    def export_teacher_attendance_range_csv(self):
        """
        Range-based teacher attendance export (one teacher at a time),
        similar to the student/class attendance exports.
        """
        start, end = self._get_range()
        if start is None:
            return

        teacher_id, ok = QInputDialog.getInt(
            self, "Teacher Attendance", "Enter Teacher ID:", 1, 1
        )
        if not ok:
            return

        teacher = self.session.get(Teacher, teacher_id)
        if teacher is None:
            QMessageBox.warning(
                self,
                "Teacher Attendance",
                f"Teacher ID {teacher_id} not found.",
            )
            return

        out_dir = self._subdir("reports", "attendance", "teachers")
        file_path = out_dir / f"teacher_{teacher_id}_attendance_{start}_{end}.csv"

        records = (
            self.session.query(TeacherAttendance)
            .filter(
                TeacherAttendance.teacher_id == teacher_id,
                TeacherAttendance.date >= start,
                TeacherAttendance.date <= end,
            )
            .order_by(TeacherAttendance.date, TeacherAttendance.id)
            .all()
        )

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "teacher_id",
                    "teacher_first_name",
                    "teacher_last_name",
                    "date",
                    "status",
                    "check_in_time",
                    "check_out_time",
                    "marked_by",
                    "timestamp",
                ]
            )

            for ta in records:
                writer.writerow(
                    [
                        teacher.id,
                        teacher.first_name or "",
                        teacher.last_name or "",
                        ta.date.isoformat() if ta.date else "",
                        ta.status or "",
                        ta.check_in_time.isoformat() if ta.check_in_time else "",
                        ta.check_out_time.isoformat() if ta.check_out_time else "",
                        ta.marked_by or "",
                        ta.timestamp.isoformat() if ta.timestamp else "",
                    ]
                )

        QMessageBox.information(
            self,
            "Teacher Attendance",
            f"Exported {len(records)} records to:\n{file_path}",
        )

    def export_teacher_attendance_range_pdf(self):
        """
        Range-based teacher attendance export (one teacher at a time) to PDF,
        similar to the student/class attendance PDFs.
        """
        start, end = self._get_range()
        if start is None:
            return

        teacher_id, ok = QInputDialog.getInt(
            self, "Teacher Attendance PDF", "Enter Teacher ID:", 1, 1
        )
        if not ok:
            return

        teacher = self.session.get(Teacher, teacher_id)
        if teacher is None:
            QMessageBox.warning(
                self,
                "Teacher Attendance PDF",
                f"Teacher ID {teacher_id} not found.",
            )
            return

        out_dir = self._subdir("reports", "attendance", "teachers")
        file_path = out_dir / f"teacher_{teacher_id}_attendance_{start}_{end}.pdf"

        records = (
            self.session.query(TeacherAttendance)
            .filter(
                TeacherAttendance.teacher_id == teacher_id,
                TeacherAttendance.date >= start,
                TeacherAttendance.date <= end,
            )
            .order_by(TeacherAttendance.date, TeacherAttendance.id)
            .all()
        )

        c = canvas.Canvas(str(file_path), pagesize=letter)
        width, height = letter
        y = height - 72

        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(
            72,
            y,
            f"Teacher Attendance - {teacher.first_name or ''} {teacher.last_name or ''}",
        )
        y -= 24
        c.setFont("Helvetica", 11)
        c.drawString(72, y, f"ID: {teacher.id}")
        y -= 14
        c.drawString(72, y, f"Range: {start} to {end}")
        y -= 24

        # Column headers
        c.setFont("Helvetica-Bold", 11)
        c.drawString(72, y, "Date")
        c.drawString(170, y, "Status")
        c.drawString(280, y, "Check-In")
        c.drawString(370, y, "Check-Out")
        y -= 16
        c.setFont("Helvetica", 10)

        if records:
            for ta in records:
                # New page if we’re near bottom
                if y < 72:
                    c.showPage()
                    y = height - 72
                    c.setFont("Helvetica-Bold", 11)
                    c.drawString(72, y, "Date")
                    c.drawString(170, y, "Status")
                    c.drawString(280, y, "Check-In")
                    c.drawString(370, y, "Check-Out")
                    y -= 16
                    c.setFont("Helvetica", 10)

                date_str = ta.date.isoformat() if ta.date else ""
                status_str = ta.status or ""
                check_in_str = (
                    ta.check_in_time.strftime("%H:%M")
                    if ta.check_in_time
                    else ""
                )
                check_out_str = (
                    ta.check_out_time.strftime("%H:%M")
                    if ta.check_out_time
                    else ""
                )

                c.drawString(72, y, date_str)
                c.drawString(170, y, status_str)
                c.drawString(280, y, check_in_str)
                c.drawString(370, y, check_out_str)
                y -= 14
        else:
            c.drawString(72, y, "No teacher attendance records in this range.")
            y -= 14

        c.showPage()
        c.save()

        QMessageBox.information(
            self,
            "Teacher Attendance PDF",
            f"Teacher attendance PDF created:\n{file_path}",
        )

    def export_monthly_summary_pdf(self):
        """
        Monthly summary for the month containing the 'From' date.
        Aggregates attendance counts by status (unique per student/date/status)
        and by class, and also shows teacher attendance status totals.
        """
        qs = self.range_start_edit.date()
        month_start = date(qs.year(), qs.month(), 1)
        if qs.month == 12:
            next_month = date(qs.year() + 1, 1, 1)
        else:
            next_month = date(qs.year(), qs.month() + 1, 1)
        month_end = next_month - timedelta(days=1)

        out_dir = self._subdir("reports", "attendance", "monthly")
        file_path = out_dir / f"monthly_summary_{month_start.year}_{month_start.month:02d}.pdf"

        # Student attendance records (with class)
        records = (
            self.session.query(Attendance, Class)
            .join(Class, Attendance.class_id == Class.id)
            .filter(
                Attendance.date >= month_start,
                Attendance.date <= month_end,
            )
            .all()
        )

        # Teacher attendance records
        teacher_records = (
            self.session.query(TeacherAttendance)
            .filter(
                TeacherAttendance.date >= month_start,
                TeacherAttendance.date <= month_end,
            )
            .all()
        )

        # Aggregate student attendance
        status_counts: dict[str, int] = {}
        class_counts: dict[str, int] = {}
        seen_status_keys = set()  # (student_id, date, status_label)

        for a, cl in records:
            status_label = (a.status or "").strip() or "(blank)"
            skey = (a.student_id, a.date, status_label)
            if skey not in seen_status_keys:
                seen_status_keys.add(skey)
                status_counts[status_label] = status_counts.get(status_label, 0) + 1

            if cl is not None:
                cname = f"{cl.name or ''} ({cl.term or ''})"
                class_counts[cname] = class_counts.get(cname, 0) + 1

        # Aggregate teacher attendance
        teacher_status_counts: dict[str, int] = {}
        seen_teacher_keys = set()  # (teacher_id, date, status_label)

        for ta in teacher_records:
            status_label = (ta.status or "").strip() or "(blank)"
            skey = (ta.teacher_id, ta.date, status_label)
            if skey not in seen_teacher_keys:
                seen_teacher_keys.add(skey)
                teacher_status_counts[status_label] = teacher_status_counts.get(status_label, 0) + 1

        c = canvas.Canvas(str(file_path), pagesize=letter)
        width, height = letter
        y = height - 72

        c.setFont("Helvetica-Bold", 16)
        c.drawString(
            72,
            y,
            f"Monthly Attendance Summary - {month_start.year}-{month_start.month:02d}",
        )
        y -= 30

        c.setFont("Helvetica", 11)
        c.drawString(72, y, f"Date range: {month_start} to {month_end}")
        y -= 24

        # Student status totals
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Student Attendance: Unique totals by Status")
        y -= 18
        c.setFont("Helvetica", 11)
        if status_counts:
            for status, count in status_counts.items():
                c.drawString(90, y, f"{status}: {count}")
                y -= 16
                if y < 72:
                    c.showPage()
                    y = height - 72
                    c.setFont("Helvetica", 11)
        else:
            c.drawString(90, y, "No student attendance records for this month.")
            y -= 16

        y -= 16
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Student Attendance: Total rows by Class")
        y -= 18
        c.setFont("Helvetica", 11)
        if class_counts:
            for cname, count in class_counts.items():
                c.drawString(90, y, f"{cname}: {count}")
                y -= 16
                if y < 72:
                    c.showPage()
                    y = height - 72
                    c.setFont("Helvetica", 11)
        else:
            c.drawString(90, y, "No class attendance records for this month.")
            y -= 16

        # Teacher status totals
        y -= 20
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Teacher Attendance: Unique totals by Status")
        y -= 18
        c.setFont("Helvetica", 11)
        if teacher_status_counts:
            for status, count in teacher_status_counts.items():
                c.drawString(90, y, f"{status}: {count}")
                y -= 16
                if y < 72:
                    c.showPage()
                    y = height - 72
                    c.setFont("Helvetica", 11)
        else:
            c.drawString(90, y, "No teacher attendance records for this month.")
            y -= 16

        c.showPage()
        c.save()

        QMessageBox.information(
            self,
            "Monthly Summary",
            f"Monthly summary PDF created:\n{file_path}",
        )

    def export_absence_list_csv(self):
        """
        Generate a CSV of all 'absent' records in the chosen date range
        (all classes, all students).
        """
        start, end = self._get_range()
        if start is None:
            return

        out_dir = self._subdir("reports", "attendance", "absences")
        file_path = out_dir / f"absence_list_{start}_{end}.csv"

        records = (
            self.session.query(Attendance, Student, Class)
            .join(Student, Attendance.student_id == Student.id)
            .join(Class, Attendance.class_id == Class.id)
            .filter(
                Attendance.date >= start,
                Attendance.date <= end,
            )
            .order_by(Attendance.date, Class.name, Student.last_name, Student.first_name)
            .all()
        )

        # Filter to 'absent'-like statuses in Python (case-insensitive)
        filtered = []
        for a, s, cl in records:
            status = (a.status or "").lower()
            if "absent" in status:
                filtered.append((a, s, cl))

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "date",
                    "student_id",
                    "student_first_name",
                    "student_last_name",
                    "class_id",
                    "class_name",
                    "class_term",
                    "status",
                ]
            )
            for a, s, cl in filtered:
                writer.writerow(
                    [
                        a.date.isoformat() if a.date else "",
                        s.id,
                        s.first_name or "",
                        s.last_name or "",
                        cl.id if cl else "",
                        cl.name if cl else "",
                        cl.term if cl else "",
                        a.status or "",
                    ]
                )

        QMessageBox.information(
            self,
            "Absence List",
            f"Exported {len(filtered)} absent records to:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # Teacher attendance log (all teachers, all dates)
    # ------------------------------------------------------------------
    def export_teacher_attendance_log_csv(self):
        """
        Export a CSV of all teacher attendance records (all teachers, all dates).
        """
        out_dir = self._subdir("reports", "attendance", "teachers")
        file_path = out_dir / "teacher_attendance_log.csv"

        records = (
            self.session.query(TeacherAttendance, Teacher)
            .join(Teacher, TeacherAttendance.teacher_id == Teacher.id)
            .order_by(TeacherAttendance.date, Teacher.last_name, Teacher.first_name, TeacherAttendance.id)
            .all()
        )

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "teacher_id",
                    "teacher_first_name",
                    "teacher_last_name",
                    "date",
                    "status",
                    "check_in_time",
                    "check_out_time",
                    "marked_by",
                    "timestamp",
                ]
            )

            for ta, t in records:
                writer.writerow(
                    [
                        ta.id,
                        t.id,
                        t.first_name or "",
                        t.last_name or "",
                        ta.date.isoformat() if ta.date else "",
                        ta.status or "",
                        ta.check_in_time.isoformat()
                        if ta.check_in_time
                        else "",
                        ta.check_out_time.isoformat()
                        if ta.check_out_time
                        else "",
                        ta.marked_by or "",
                        ta.timestamp.isoformat() if ta.timestamp else "",
                    ]
                )

        QMessageBox.information(
            self,
            "Teacher Attendance Log",
            f"Exported {len(records)} teacher attendance records to:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # Open exports folder
    # ------------------------------------------------------------------
    def open_exports_folder(self):
        """
        Open the base exports folder in the system file explorer.

        Respects settings.export_base_dir if set, otherwise uses EXPORTS_DIR
        from data.paths (via _get_exports_dir()).
        """
        base = self._get_exports_dir()  # ensures it exists

        try:
            if sys.platform.startswith("win"):
                # Windows
                os.startfile(base)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                # macOS
                subprocess.Popen(["open", str(base)])
            else:
                # Linux / other
                subprocess.Popen(["xdg-open", str(base)])
        except Exception as e:
            QMessageBox.critical(
                self,
                "Open Exports Folder",
                f"Could not open the exports folder:\n{base}\n\n{e}",
            )


    # ------------------------------------------------------------------
    # Backup database file
    # ------------------------------------------------------------------
    def backup_database(self):
        """
        Automatically create a .db backup in:
        <exports>/backups/db/registree_backup_YYYY-MM-DD_HHMMSS.db
        No file dialog.
        """
        if not DB_FILE.exists():
            QMessageBox.warning(
                self,
                "Backup Database",
                f"Database file not found:\n{DB_FILE}",
            )
            return

        # Directory: <exports>/backups/db
        backups_dir = self._subdir("backups", "db")

        # Timestamped filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_path = backups_dir / f"registree_backup_{timestamp}.db"

        try:
            shutil.copy2(DB_FILE, backup_path)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Backup Database",
                f"Failed to backup database:\n{e}",
            )
            return

        QMessageBox.information(
            self,
            "Backup Database",
            f"Database successfully backed up to:\n{backup_path}",
        )

    # ------------------------------------------------------------------
    # Full RegisTree backup (db + photos/)
    # ------------------------------------------------------------------
    def full_registree_backup(self):
        """
        Create a timestamped folder under <exports>/backups/full that contains:
        - a copy of registree.db
        - a copy of the photos/ directory (if it exists)
        """
        backups_root = self._subdir("backups", "full")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = backups_root / f"registree_full_backup_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Copy database
        if DB_FILE.exists():
            shutil.copy2(DB_FILE, backup_dir / DB_FILE.name)
            db_msg = f"Database copied as {DB_FILE.name}"
        else:
            db_msg = "Database file NOT FOUND."

        # Copy photos directory (if present)
        if PHOTOS_DIR.exists() and PHOTOS_DIR.is_dir():
            dest_photos = backup_dir / PHOTOS_DIR.name
            shutil.copytree(PHOTOS_DIR, dest_photos)
            photos_msg = f"Photos folder copied ({PHOTOS_DIR})"
        else:
            photos_msg = "Photos folder not found; skipped."

        QMessageBox.information(
            self,
            "Full RegisTree Backup",
            f"Full backup created at:\n{backup_dir}\n\n{db_msg}\n{photos_msg}",
        )

    # ------------------------------------------------------------------
    # Restore database file
    # ------------------------------------------------------------------
    def restore_database(self):
        # Let user pick a .db file to restore from
        src_path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select Database File to Restore",
            "",
            "SQLite DB Files (*.db);;All Files (*.*)",
        )
        if not src_path_str:
            return  # user cancelled

        src_path = Path(src_path_str)

        if not src_path.exists():
            QMessageBox.warning(
                self,
                "Restore Database",
                f"Selected file does not exist:\n{src_path}",
            )
            return

        # Confirm overwrite
        reply = QMessageBox.question(
            self,
            "Restore Database",
            (
                "This will OVERWRITE the current RegisTree database file:\n"
                f"{DB_FILE}\n\n"
                "Are you sure you want to restore from:\n"
                f"{src_path} ?\n\n"
                "After restoring, RegisTree must restart."
            ),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Perform copy
        try:
            shutil.copy2(src_path, DB_FILE)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Restore Database",
                f"Failed to restore database:\n{e}",
            )
            return

        # Show Restart Now dialog
        restart_choice = QMessageBox.question(
            self,
            "Database Restored",
            (
                f"Database restored from:\n{src_path}\n\n"
                "RegisTree needs to restart to load the restored data.\n\n"
                "Restart now?"
            ),
            QMessageBox.Yes | QMessageBox.No,
        )

        if restart_choice == QMessageBox.Yes:
            os.execl(sys.executable, sys.executable, *sys.argv)
        else:
            QMessageBox.information(
                self,
                "Restart Later",
                "Please remember to close and reopen RegisTree before continuing.",
            )

    # ------------------------------------------------------------------
    # Change admin password
    # ------------------------------------------------------------------
    def change_admin_password(self):
        # There should be exactly one admin user (username='admin')
        admin = self.session.query(AdminUser).first()
        if admin is None:
            QMessageBox.warning(
                self,
                "Change Password",
                "No admin user found in the database.\n"
                "Please restart RegisTree so it can create an admin account.",
            )
            return

        dialog = ChangePasswordDialog(
            verify_func=verify_password,
            stored_hash=admin.password_hash,
            parent=self,
        )
        result = dialog.exec()

        if result != QMessageBox.Accepted:
            return  # user cancelled or failed validation

        new_pw = dialog.get_new_password()
        if not new_pw:
            return

        # Update hash in DB
        admin.password_hash = hash_password(new_pw)
        self.session.commit()

        QMessageBox.information(
            self,
            "Change Password",
            "Admin password has been updated successfully.",
        )
