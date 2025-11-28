from datetime import date, timedelta

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QGridLayout,
    QComboBox,
    QDateEdit,
)
from PySide6.QtCore import Qt, QDate

from data.models import Student, Class, Attendance, CalendarEvent

# Matplotlib embedding for PySide6
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class DashboardView(QWidget):
    """
    Dashboard tab:
    - Shows key statistics about RegisTree.
    - Attendance visualization pie chart (day or month, optional grade filter).
    """

    def __init__(self, session, settings=None):
        super().__init__()
        self.session = session
        self.settings = settings  # <- store settings object

        # --------------------------------------------------------------
        # Main vertical layout
        # --------------------------------------------------------------
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

        # --------------------------------------------------------------
        # Content area: split into left + right panes
        # --------------------------------------------------------------
        content_layout = QHBoxLayout()

        # ==========================
        # LEFT PANE (existing stuff)
        # ==========================
        left_layout = QVBoxLayout()

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
        left_layout.addWidget(metrics_group)

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
        left_layout.addWidget(today_group)

        # --- Upcoming events group (from calendar) ---
        events_group = QGroupBox("Today's and Upcoming Events")
        events_layout = QVBoxLayout()
        self.events_label = QLabel("No upcoming events.")
        self.events_label.setWordWrap(True)
        events_layout.addWidget(self.events_label)
        events_group.setLayout(events_layout)
        left_layout.addWidget(events_group)

        # --- Bottom controls: Refresh button ---
        buttons_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh Now")
        self.refresh_button.clicked.connect(self.refresh_stats)
        buttons_layout.addWidget(self.refresh_button)
        buttons_layout.addStretch()

        left_layout.addLayout(buttons_layout)
        left_layout.addStretch()

        # ==========================
        # RIGHT PANE (new chart)
        # ==========================
        right_group = QGroupBox("Attendance Visualization")
        right_layout = QVBoxLayout()

        # --- Controls for chart (view mode, date, grade filter) ---
        controls_layout = QHBoxLayout()

        controls_layout.addWidget(QLabel("View:"))
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["Single Day", "Full Month"])
        controls_layout.addWidget(self.view_mode_combo)

        controls_layout.addWidget(QLabel("Date:"))
        self.chart_date_edit = QDateEdit()
        self.chart_date_edit.setCalendarPopup(True)
        self.chart_date_edit.setDate(QDate.currentDate())
        controls_layout.addWidget(self.chart_date_edit)

        controls_layout.addWidget(QLabel("Grade:"))
        self.grade_filter = QComboBox()
        self.grade_filter.addItem("All grades")  # will be rebuilt with actual grades
        controls_layout.addWidget(self.grade_filter)

        controls_layout.addStretch()
        right_layout.addLayout(controls_layout)

        # --- Matplotlib pie chart canvas ---
        self.figure = Figure(figsize=(4, 3), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        right_layout.addWidget(self.canvas)

        right_group.setLayout(right_layout)

        # Add left + right panes to content layout
        content_layout.addLayout(left_layout, 2)
        content_layout.addWidget(right_group, 3)

        main_layout.addLayout(content_layout)
        self.setLayout(main_layout)

        # Connect chart controls
        self.view_mode_combo.currentTextChanged.connect(self.update_attendance_chart)
        self.chart_date_edit.dateChanged.connect(lambda _d: self.update_attendance_chart())
        self.grade_filter.currentTextChanged.connect(self.update_attendance_chart)

        # Build grade filter and load initial stats + chart
        self._rebuild_grade_filter()
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

        # Today's attendance summary (same logic as before)
        self.today_date_label.setText(f"Date: {today.isoformat()}")

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
        else:
            # Collapse to unique students with "worst" status
            priority = {
                "Absent": 0,
                "Tardy": 1,
                "Excused": 2,
                "Present": 3,
            }

            def canonical_status(raw: str) -> str:
                s = (raw or "").strip().lower()
                if "no school" in s:
                    return "No School"
                if "absent" in s:
                    return "Absent"
                if "tardy" in s or "late" in s:
                    return "Tardy"
                if "excused" in s:
                    return "Excused"
                if "present" in s:
                    return "Present"
                return raw or "Other"

            def get_priority(label: str) -> int:
                label = canonical_status(label)
                return priority.get(label, 1)

            per_student_status = {}
            for a in records:
                sid = a.student_id
                status = canonical_status(a.status)
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

        # Upcoming events (today and future)
        from datetime import timedelta  # if not already imported at top

        events = (
            self.session.query(CalendarEvent)
            .filter(CalendarEvent.end_date >= today)
            .order_by(CalendarEvent.start_date)
            .limit(10)
            .all()
        )

        if not events:
            self.events_label.setText("No upcoming events.")
        else:
            lines = []
            for ev in events:
                if ev.start_date == ev.end_date:
                    date_str = ev.start_date.isoformat()
                else:
                    date_str = f"{ev.start_date.isoformat()} → {ev.end_date.isoformat()}"
                lines.append(f"{date_str}: {ev.event_type} – {ev.title}")
            self.events_label.setText("\n".join(lines))

        # Rebuild grade filter (in case grades changed) and update chart
        self._rebuild_grade_filter()
        self.update_attendance_chart()

    # ------------------------------------------------------------------
    # Build / rebuild grade filter combo box
    # ------------------------------------------------------------------
    def _rebuild_grade_filter(self):
        """
        Populate grade filter with distinct Student.grade_level values.
        Always keeps 'All grades' as the first entry.
        """
        current_text = self.grade_filter.currentText() if self.grade_filter.count() > 0 else "All grades"

        self.grade_filter.blockSignals(True)
        self.grade_filter.clear()
        self.grade_filter.addItem("All grades")

        grades = (
            self.session.query(Student.grade_level)
            .filter(Student.grade_level.isnot(None))
            .distinct()
            .all()
        )
        grade_values = sorted(
            [g[0] for g in grades if g[0]],
            key=lambda x: (x or "").lower(),
        )

        for g in grade_values:
            self.grade_filter.addItem(g)

        # Try to restore previous selection if it still exists
        idx = self.grade_filter.findText(current_text)
        if idx >= 0:
            self.grade_filter.setCurrentIndex(idx)
        else:
            self.grade_filter.setCurrentIndex(0)

        self.grade_filter.blockSignals(False)

    # ------------------------------------------------------------------
    # Attendance pie chart
    # ------------------------------------------------------------------
    def update_attendance_chart(self):
        """
        Build a pie chart of attendance tallies over:
        - Single Day: that exact date
        - Full Month: all days in that month

        Within the range:
        - For each (student, date), we pick the "worst" status that day.
        - Then we tally Present / Excused / Tardy / Absent (plus Other).
        """
        # Clear figure
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # ----------------------------------------------------------
        # Determine date range based on view mode
        # ----------------------------------------------------------
        qd = self.chart_date_edit.date()
        selected = date(qd.year(), qd.month(), qd.day())
        mode = self.view_mode_combo.currentText()

        if mode == "Full Month":
            start = date(selected.year, selected.month, 1)
            if selected.month == 12:
                end = date(selected.year, 12, 31)
            else:
                end = date(selected.year, selected.month + 1, 1) - timedelta(days=1)
            range_title = selected.strftime("%B %Y")
        else:  # "Single Day"
            start = selected
            end = selected
            range_title = selected.isoformat()

        # ----------------------------------------------------------
        # Optional grade filter
        # ----------------------------------------------------------
        grade_text = self.grade_filter.currentText()
        query = (
            self.session.query(Attendance, Student)
            .join(Student, Attendance.student_id == Student.id)
            .filter(
                Attendance.date >= start,
                Attendance.date <= end,
            )
        )

        if grade_text and grade_text != "All grades":
            query = query.filter(Student.grade_level == grade_text)

        rows = query.all()

        if not rows:
            ax.axis("off")
            ax.text(
                0.5,
                0.5,
                "No attendance data\nfor selected range.",
                ha="center",
                va="center",
                fontsize=10,
            )
            self.canvas.draw()
            return

        # ----------------------------------------------------------
        # Canonicalize statuses + compute per (student, date) worst
        # ----------------------------------------------------------
        def canonical_status(raw: str) -> str:
            s = (raw or "").strip().lower()
            if "no school" in s:
                return "No School"
            if "absent" in s:
                return "Absent"
            if "tardy" in s or "late" in s:
                return "Tardy"
            if "excused" in s:
                return "Excused"
            if "present" in s:
                return "Present"
            return "Other"

        priority = {
            "Absent": 0,
            "Tardy": 1,
            "Excused": 2,
            "Present": 3,
            "Other": 1,  # "other" behaves like a mid-level status
        }

        def get_priority(label: str) -> int:
            return priority.get(label, 1)

        # key: (student_id, date) -> canonical status for that day
        per_key_status = {}
        for a, s in rows:
            key = (a.student_id, a.date)
            status = canonical_status(a.status)
            if key not in per_key_status:
                per_key_status[key] = status
            else:
                existing = per_key_status[key]
                if get_priority(status) < get_priority(existing):
                    per_key_status[key] = status

        # Tally counts by canonical status
        counts = {}
        for status in per_key_status.values():
            counts[status] = counts.get(status, 0) + 1

        # ----------------------------------------------------------
        # Prepare pie chart data
        # ----------------------------------------------------------
        # Colors chosen to match Attendance tab colors (but non-transparent)
        STATUS_COLORS = {
            "Present": (144 / 255.0, 238 / 255.0, 144 / 255.0),   # light green
            "Absent": (255 / 255.0, 99 / 255.0, 71 / 255.0),      # tomato red
            "Tardy": (255 / 255.0, 215 / 255.0, 0 / 255.0),       # gold
            "Excused": (135 / 255.0, 206 / 255.0, 250 / 255.0),   # light blue
            "No School": (186 / 255.0, 85 / 255.0, 211 / 255.0),  # purple-ish
            "Other": (211 / 255.0, 211 / 255.0, 211 / 255.0),     # light gray
        }

        order = ["Present", "Excused", "Tardy", "Absent", "No School", "Other"]

        labels = []
        sizes = []
        colors = []
        for label in order:
            cnt = counts.get(label, 0)
            if cnt > 0:
                labels.append(f"{label} ({cnt})")
                sizes.append(cnt)
                colors.append(STATUS_COLORS.get(label, STATUS_COLORS["Other"]))

        if not sizes:
            ax.axis("off")
            ax.text(
                0.5,
                0.5,
                "No recognizable attendance data\nfor selected range.",
                ha="center",
                va="center",
                fontsize=10,
            )
            self.canvas.draw()
            return

        # ----------------------------------------------------------
        # Draw pie chart
        # ----------------------------------------------------------
        wedges, text_labels, autotexts = ax.pie(
            sizes,
            labels=labels,
            colors=colors,
            autopct="%1.0f",
            textprops={"color": "black"},  # pie text black
        )

        # Legend: bottom-right, slightly smaller
        legend = ax.legend(
            wedges,
            labels,
            title="Status",
            loc="lower right",
            fontsize=8,
        )
        legend.get_frame().set_alpha(0.8)

        ax.set_title(f"Attendance: {range_title}", fontsize=10)
        self.canvas.draw()
