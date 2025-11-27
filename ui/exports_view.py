from datetime import date
from pathlib import Path
import csv
import json
import shutil
import os
import sys

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QDateEdit,
    QMessageBox,
    QFileDialog,
)

from PySide6.QtCore import QDate
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from data.models import Student, Class, Enrollment, Attendance, AdminUser
from data.security import hash_password, verify_password
from ui.auth_dialogs import ChangePasswordDialog


DB_FILE = Path("registree.db")


class ExportsView(QWidget):
    """
    Exports tab:
    - Export Students, Classes, Enrollments as CSV.
    - Export Attendance for a chosen date as CSV.
    - Export Students JSON snapshot.
    - Generate a daily bundle: students.json + attendance CSV + PDF summary.
    - Backup and restore the entire SQLite database file.
    """

    def __init__(self, session, settings=None):
        super().__init__()
        self.session = session
        self.settings = settings

        main_layout = QVBoxLayout()

        # --- Section: Roster exports (Students / Classes / Enrollments / JSON) ---
        main_layout.addWidget(QLabel("<b>Roster Exports</b>"))

        roster_layout = QHBoxLayout()

        self.export_students_button = QPushButton("Export Students CSV")
        self.export_students_button.clicked.connect(self.export_students_csv)
        roster_layout.addWidget(self.export_students_button)

        self.export_students_json_button = QPushButton("Export Students JSON")
        self.export_students_json_button.clicked.connect(self.export_students_json)
        roster_layout.addWidget(self.export_students_json_button)

        self.export_classes_button = QPushButton("Export Classes CSV")
        self.export_classes_button.clicked.connect(self.export_classes_csv)
        roster_layout.addWidget(self.export_classes_button)

        self.export_enrollments_button = QPushButton("Export Enrollments CSV")
        self.export_enrollments_button.clicked.connect(self.export_enrollments_csv)
        roster_layout.addWidget(self.export_enrollments_button)

        roster_layout.addStretch()
        main_layout.addLayout(roster_layout)

        # --- Section: Attendance exports + bundle ---
        main_layout.addSpacing(20)
        main_layout.addWidget(QLabel("<b>Attendance & Daily Bundle</b>"))

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
        main_layout.addLayout(attendance_layout)

        # --- Section: Database backup/restore + change password ---
        main_layout.addSpacing(20)
        main_layout.addWidget(QLabel("<b>Database Backup / Restore</b>"))

        db_layout = QHBoxLayout()

        self.backup_button = QPushButton("Backup Database…")
        self.backup_button.clicked.connect(self.backup_database)
        db_layout.addWidget(self.backup_button)

        self.restore_button = QPushButton("Restore Database…")
        self.restore_button.clicked.connect(self.restore_database)
        db_layout.addWidget(self.restore_button)

        self.change_pw_button = QPushButton("Change Admin Password…")
        self.change_pw_button.clicked.connect(self.change_admin_password)
        db_layout.addWidget(self.change_pw_button)

        db_layout.addStretch()
        main_layout.addLayout(db_layout)

        self.setLayout(main_layout)

    # ------------------------------------------------------------------
    # Helpers for paths
    # ------------------------------------------------------------------
    def _get_exports_dir(self) -> Path:
        """Generic exports folder, possibly overridden by Settings.export_base_dir."""
        if self.settings is not None and getattr(
            self.settings, "export_base_dir", None
        ):
            base = Path(self.settings.export_base_dir)
        else:
            base = Path("exports")

        base.mkdir(parents=True, exist_ok=True)
        return base

    def _get_date_dir(self, att_date: date) -> Path:
        """Folder for a specific date, e.g. <base>/2025-11-25/."""
        base = self._get_exports_dir()
        out_dir = base / att_date.isoformat()
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    # ------------------------------------------------------------------
    # STUDENTS: CSV
    # ------------------------------------------------------------------
    def export_students_csv(self):
        out_dir = self._get_exports_dir()
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
                    "status",
                    "guardian_name",
                    "guardian_phone",
                    "contact_email",
                ]
            )

            for s in students:
                writer.writerow(
                    [
                        s.id,
                        s.first_name,
                        s.last_name,
                        s.dob.isoformat() if s.dob else "",
                        s.grade_level or "",
                        s.status or "",
                        s.guardian_name or "",
                        s.guardian_phone or "",
                        s.contact_email or "",
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
                    "status": s.status,
                    "guardian_name": s.guardian_name,
                    "guardian_phone": s.guardian_phone,
                    "contact_email": s.contact_email,
                }
            )

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return len(students)

    def export_students_json(self):
        out_dir = self._get_exports_dir()
        count = self._export_students_json_to(out_dir)
        file_path = out_dir / "students.json"

        QMessageBox.information(
            self,
            "Export Students JSON",
            f"Exported {count} students to JSON:\n{file_path}",
        )

    # ------------------------------------------------------------------
    # CLASSES: CSV
    # ------------------------------------------------------------------
    def export_classes_csv(self):
        out_dir = self._get_exports_dir()
        file_path = out_dir / "classes.csv"

        classes = self.session.query(Class).order_by(Class.name).all()

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "name",
                    "subject",
                    "teacher_name",
                    "term",
                    "room",
                ]
            )

            for c in classes:
                writer.writerow(
                    [
                        c.id,
                        c.name or "",
                        c.subject or "",
                        c.teacher_name or "",
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
        out_dir = self._get_exports_dir()
        file_path = out_dir / "enrollments.csv"

        enrollments = self.session.query(Enrollment).all()

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "student_id",
                    "class_id",
                    "start_date",
                    "end_date",
                ]
            )

            for e in enrollments:
                writer.writerow(
                    [
                        e.id,
                        e.student_id,
                        e.class_id,
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
    # ATTENDANCE: CSV (single date)
    # ------------------------------------------------------------------
    def _export_attendance_csv_to(self, out_dir: Path, att_date: date) -> int:
        """Helper: write attendance_DATE.csv into out_dir, return count."""
        file_path = out_dir / f"attendance_{att_date.isoformat()}.csv"

        records = (
            self.session.query(Attendance)
            .filter(Attendance.date == att_date)
            .all()
        )

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "student_id",
                    "class_id",
                    "date",
                    "status",
                    "marked_by",
                    "timestamp",
                ]
            )

            for a in records:
                writer.writerow(
                    [
                        a.id,
                        a.student_id,
                        a.class_id,
                        a.date.isoformat() if a.date else "",
                        a.status or "",
                        a.marked_by or "",
                        a.timestamp.isoformat() if a.timestamp else "",
                    ]
                )

        return len(records)

    def export_attendance_csv(self):
        out_dir = self._get_exports_dir()

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
    # PDF summary for a given date
    # ------------------------------------------------------------------
    def _export_summary_pdf(self, out_dir: Path, att_date: date):
        """Create a simple PDF summary for the given date."""
        file_path = out_dir / f"summary_{att_date.isoformat()}.pdf"

        # Basic stats
        total_students = self.session.query(Student).count()
        total_classes = self.session.query(Class).count()

        records = (
            self.session.query(Attendance)
            .filter(Attendance.date == att_date)
            .all()
        )
        total_attendance_records = len(records)

        # Count by status
        status_counts = {}
        for a in records:
            status_counts[a.status] = status_counts.get(a.status, 0) + 1

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
        c.drawString(72, y, f"Attendance Records for this date: {total_attendance_records}")
        y -= 30

        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Attendance by Status:")
        y -= 20

        c.setFont("Helvetica", 12)
        if status_counts:
            for status, count in status_counts.items():
                c.drawString(90, y, f"{status}: {count}")
                y -= 18
        else:
            c.drawString(90, y, "No attendance records for this date.")
            y -= 18

        c.showPage()
        c.save()

    # ------------------------------------------------------------------
    # Generate daily bundle (students.json + attendance CSV + PDF)
    # ------------------------------------------------------------------
    def generate_daily_bundle(self):
        qd = self.date_edit.date()
        att_date = date(qd.year(), qd.month(), qd.day())

        out_dir = self._get_date_dir(att_date)

        # 1) Students JSON snapshot
        students_count = self._export_students_json_to(out_dir)

        # 2) Attendance CSV for that date
        attendance_count = self._export_attendance_csv_to(out_dir, att_date)

        # 3) PDF summary
        self._export_summary_pdf(out_dir, att_date)

        QMessageBox.information(
            self,
            "Daily Bundle",
            (
                f"Generated daily bundle for {att_date} in:\n{out_dir}\n\n"
                f"Students in JSON: {students_count}\n"
                f"Attendance records: {attendance_count}\n"
                f"PDF summary: summary_{att_date.isoformat()}.pdf"
            ),
        )

    # ------------------------------------------------------------------
    # Backup database file
    # ------------------------------------------------------------------
    def backup_database(self):
        if not DB_FILE.exists():
            QMessageBox.warning(
                self,
                "Backup Database",
                f"Database file not found:\n{DB_FILE}",
            )
            return

        # Choose where to save the backup
        default_name = f"registree_backup_{date.today().isoformat()}.db"
        dest_path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save Database Backup",
            default_name,
            "SQLite DB Files (*.db);;All Files (*.*)",
        )
        if not dest_path_str:
            return  # user cancelled

        dest_path = Path(dest_path_str)

        try:
            shutil.copy2(DB_FILE, dest_path)
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
            f"Database backed up to:\n{dest_path}",
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
            # Relaunch the current Python process with the same script/arguments.
            # On Windows, this will effectively re-run `python app.py` (or whatever
            # command was used), in the same console.
            os.execl(sys.executable, sys.executable, *sys.argv)
        else:
            QMessageBox.information(
                self,
                "Restart Later",
                "Please remember to close and reopen RegisTree before continuing."
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
