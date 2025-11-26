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

    def __init__(self, session):
        super().__init__()
        self.session = session

        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignTop)

        # Title
        title_label = QLabel("<h1>RegisTree Dashboard</h1>")
        main_layout.addWidget(title_label)

        # --- Key metrics group ---
        metrics_group = QGroupBox("Key Metrics")
        metrics_layout = QGridLayout()

        self.total_students_label = QLabel("Total Students: -")
        self.active_students_label = QLabel("Active Students: -")
        self.total_classes_label = QLabel("Total Classes: -")

        metrics_layout.addWidget(self.total_students_label, 0, 0)
        metrics_layout.addWidget(self.active_students_label, 1, 0)
        metrics_layout.addWidget(self.total_classes_label, 2, 0)

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
        today = date.today()

        # Key metrics
        total_students = self.session.query(Student).count()
        active_students = (
            self.session.query(Student)
            .filter(Student.status == "Active")
            .count()
        )
        total_classes = self.session.query(Class).count()

        self.total_students_label.setText(f"Total Students: {total_students}")
        self.active_students_label.setText(f"Active Students: {active_students}")
        self.total_classes_label.setText(f"Total Classes: {total_classes}")

        # Today's attendance
        self.today_date_label.setText(f"Date: {today.isoformat()}")

        records = (
            self.session.query(Attendance)
            .filter(Attendance.date == today)
            .all()
        )
        total_att = len(records)

        if total_att == 0:
            self.today_summary_label.setText(
                "No attendance records have been saved for today."
            )
            self.today_status_breakdown_label.setText("")
            return

        self.today_summary_label.setText(
            f"Total attendance records today: {total_att}"
        )

        # Breakdown by status
        status_counts = {}
        for a in records:
            status_counts[a.status] = status_counts.get(a.status, 0) + 1

        breakdown_lines = []
        for status, count in status_counts.items():
            breakdown_lines.append(f"{status}: {count}")

        breakdown_text = " | ".join(breakdown_lines)
        self.today_status_breakdown_label.setText(
            f"By status: {breakdown_text}"
        )
