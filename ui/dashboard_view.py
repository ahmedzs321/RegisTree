from datetime import date

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QGridLayout,
)
from PySide6.QtCore import Qt

from data.models import Student, Class, Attendance


class DashboardView(QWidget):
    """
    Dashboard tab:
    - Shows key statistics about RegisTree.
    - Can be refreshed manually.
    """

    def __init__(self, session, settings=None):
        super().__init__()
        self.session = session
        self.settings = settings  # <- store settings object

        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignTop)

        # Title
        title_label = QLabel("<h1>RegisTree Dashboard</h1>")
        main_layout.addWidget(title_label)

        # School name + academic year underneath the title
        self.school_label = QLabel("")          # e.g. "Lincoln Elementary"
        self.academic_year_label = QLabel("")   # e.g. "Academic year: 2025–2026"
        self.academic_year_label.setStyleSheet("color: gray;")

        main_layout.addWidget(self.school_label)
        main_layout.addWidget(self.academic_year_label)

        # --- Key metrics group ---
        metrics_group = QGroupBox("Key Metrics")
        metrics_layout = QGridLayout()

        self.total_students_label = QLabel("Total Students: -")
        self.active_students_label = QLabel("Active Students: -")
        self.graduated_students_label = QLabel("Graduated Students: -")
        self.total_classes_label = QLabel("Total Classes: -")

        metrics_layout.addWidget(self.total_students_label, 0, 0)
        metrics_layout.addWidget(self.active_students_label, 1, 0)
        metrics_layout.addWidget(self.graduated_students_label, 2, 0)
        metrics_layout.addWidget(self.total_classes_label, 3, 0)

        metrics_group.setLayout(metrics_layout)
        main_layout.addWidget(metrics_group)

        # --- Today's attendance group ---
        today_group = QGroupBox("Today's Attendance")
        today_layout = QVBoxLayout()

        self.today_date_label = QLabel("")
        self.today_summary_label = QLabel("No data loaded yet.")
        self.today_status_breakdown_label = QLabel("")

        today_layout.addWidget(self.today_date_label)
        today_layout.addWidget(self.today_summary_label)
        today_layout.addWidget(self.today_status_breakdown_label)

        today_group.setLayout(today_layout)
        main_layout.addWidget(today_group)

        # --- Bottom controls: Refresh button ---
        buttons_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh Now")
        self.refresh_button.clicked.connect(self.refresh_stats)
        buttons_layout.addWidget(self.refresh_button)
        buttons_layout.addStretch()

        main_layout.addLayout(buttons_layout)

        self.setLayout(main_layout)

        # Load initial stats
        self.refresh_stats()

    # ------------------------------------------------------------------
    # Refresh dashboard statistics from the database
    # ------------------------------------------------------------------
    def refresh_stats(self):
        # Show school name + academic year from Settings + date
        if self.settings is not None:
            school_name = (self.settings.school_name or "").strip()
            academic_year = (self.settings.academic_year or "").strip()
        else:
            school_name = ""
            academic_year = ""

        # Fallback text if no school name is set
        if not school_name:
            school_name = "School: (not set)"

        self.school_label.setText(school_name)

        if academic_year:
            self.academic_year_label.setText(f"Academic year: {academic_year}")
        else:
            self.academic_year_label.setText("")
        
        today = date.today()

        # Key metrics
        total_students = self.session.query(Student).count()
        active_students = (
            self.session.query(Student)
            .filter(Student.status == "Active")
            .count()
        )
        graduated_students = (
            self.session.query(Student)
            .filter(Student.status == "Graduated")
            .count()
        )
        total_classes = self.session.query(Class).count()

        self.total_students_label.setText(f"Total Students: {total_students}")
        self.active_students_label.setText(f"Active Students: {active_students}")
        self.graduated_students_label.setText(f"Graduated Students: {graduated_students}")
        self.total_classes_label.setText(f"Total Classes: {total_classes}")

        # Today's attendance
        self.today_date_label.setText(f"Date: {today.isoformat()}")

        # All attendance rows for today (across all classes)
        records = (
            self.session.query(Attendance)
            .filter(Attendance.date == today)
            .all()
        )

        if not records:
            self.today_summary_label.setText(
                "No attendance records have been saved for today."
            )
            self.today_status_breakdown_label.setText("")
            return

        # Collapse to unique students so each student is counted once.
        # If a student has multiple records with different statuses,
        # we pick the "worst" status using a simple priority scheme.
        priority = {
            "Absent": 0,
            "Tardy": 1,
            "Excused": 2,
            "Present": 3,
        }

        def get_priority(status: str) -> int:
            # Unknown statuses get a mid-level priority
            return priority.get(status, 1)

        per_student_status = {}  # student_id -> status (worst for that student)
        for a in records:
            sid = a.student_id
            status = a.status or "Present"

            if sid not in per_student_status:
                per_student_status[sid] = status
            else:
                existing = per_student_status[sid]
                if get_priority(status) < get_priority(existing):
                    per_student_status[sid] = status

        unique_students = len(per_student_status)

        self.today_summary_label.setText(
            f"Students with attendance recorded today: {unique_students}"
        )

        # Breakdown by status (per student, not per class)
        status_counts = {}
        for status in per_student_status.values():
            status_counts[status] = status_counts.get(status, 0) + 1

        breakdown_lines = [
            f"{status}: {count}" for status, count in status_counts.items()
        ]
        breakdown_text = " | ".join(breakdown_lines)
        self.today_status_breakdown_label.setText(
            f"By status (unique students): {breakdown_text}"
        )