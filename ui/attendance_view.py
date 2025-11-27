from datetime import date, datetime
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QAbstractSpinBox,
)
from PySide6.QtCore import QDate
from data.models import Class, Student, Enrollment, Attendance


class AttendanceView(QWidget):
    """
    Attendance tab:
    - Select a class and date.
    - Load roster of enrolled students.
    - Mark attendance using customizable statuses.
    - Save records to the database.
    """

    DEFAULT_STATUS_OPTIONS = ["Present", "Absent", "Tardy", "Excused"]

    def __init__(self, session, settings=None):
        super().__init__()
        self.session = session
        self.settings = settings
        
        # Auto-save flag from Settings
        self.auto_save_enabled = False
        if self.settings is not None:
            self.auto_save_enabled = bool(
                getattr(self.settings, "attendance_auto_save", False)
            )

        # Determine which statuses to use
        self.status_options = list(self.DEFAULT_STATUS_OPTIONS)
        if self.settings is not None and getattr(
            self.settings, "attendance_statuses_json", None
        ):
            try:
                import json

                data = json.loads(self.settings.attendance_statuses_json)
                if (
                    isinstance(data, list)
                    and data
                    and all(isinstance(x, str) for x in data)
                ):
                    self.status_options = data
            except Exception:
                # Fall back to defaults on any parsing error
                self.status_options = list(self.DEFAULT_STATUS_OPTIONS)

        main_layout = QVBoxLayout()

        # --- Top controls: term + class + date + buttons ---
        top_layout = QHBoxLayout()

        # Term filter
        top_layout.addWidget(QLabel("Term:"))
        self.term_filter = QComboBox()
        self.term_filter.addItem("All terms")
        top_layout.addWidget(self.term_filter)

        # Class selection within term
        top_layout.addWidget(QLabel("Class:"))
        self.class_combo = QComboBox()
        top_layout.addWidget(self.class_combo)

        # Date selector
        top_layout.addWidget(QLabel("Date:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        # Disable up/down spin buttons so clicks near the arrow don't increment the date
        self.date_edit.setButtonSymbols(QAbstractSpinBox.NoButtons)
        top_layout.addWidget(self.date_edit)

        self.load_button = QPushButton("Load Roster")
        self.load_button.clicked.connect(lambda: self.load_roster(show_warnings=True))
        top_layout.addWidget(self.load_button)

        self.mark_all_present_button = QPushButton("Mark All Present")
        self.mark_all_present_button.clicked.connect(self.mark_all_present)
        top_layout.addWidget(self.mark_all_present_button)

        self.save_button = QPushButton("Save Attendance")
        self.save_button.clicked.connect(self.save_attendance)
        top_layout.addWidget(self.save_button)
        top_layout.addStretch()

        # Term change → rebuild classes for that term
        self.term_filter.currentTextChanged.connect(self.on_term_changed)

        # Auto-load roster when class/date change (no warnings)
        self.class_combo.currentIndexChanged.connect(self.on_class_or_date_changed)
        self.date_edit.dateChanged.connect(self.on_class_or_date_changed)

        main_layout.addLayout(top_layout)

        # --- Table for roster ---
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Student ID", "First Name", "Last Name", "Status"]
        )
        # We will place QComboBox widgets in the Status column.
        main_layout.addWidget(self.table)

        self.setLayout(main_layout)

        # Load class list into combo box
        self.load_classes()

    # ------------------------------------------------------------------
    # Load list of classes into class_combo
    # ------------------------------------------------------------------
    def load_classes(self):
        """
        Load list of classes into class_combo, filtered by the selected term.
        """
        self.class_combo.clear()
        self.class_id_map = []

        # Get all classes sorted by term, then id
        all_classes = (
            self.session.query(Class)
            .order_by(Class.term, Class.id)
            .all()
        )

        # Update term filter dropdown with distinct terms
        if hasattr(self, "term_filter"):
            terms = sorted({c.term for c in all_classes if c.term})
            current_term = self.term_filter.currentText()

            self.term_filter.blockSignals(True)
            self.term_filter.clear()
            self.term_filter.addItem("All terms")
            for t in terms:
                self.term_filter.addItem(t)
            # Try to restore previously selected term if possible
            index = self.term_filter.findText(current_term)
            if index >= 0:
                self.term_filter.setCurrentIndex(index)
            self.term_filter.blockSignals(False)

            selected_term = self.term_filter.currentText()
            if selected_term == "All terms":
                classes = all_classes
            else:
                classes = [c for c in all_classes if (c.term or "") == selected_term]
        else:
            classes = all_classes

        # Populate the class combo
        for c in classes:
            label = f"{c.name} ({c.term or ''})"
            self.class_combo.addItem(label)
            self.class_id_map.append(c.id)

        if not classes:
            self.class_combo.addItem("(No classes)")
            self.class_combo.setEnabled(False)
            self.load_button.setEnabled(False)
            self.mark_all_present_button.setEnabled(False)
            self.save_button.setEnabled(False)
        else:
            self.class_combo.setEnabled(True)
            self.load_button.setEnabled(True)
            self.mark_all_present_button.setEnabled(True)
            self.save_button.setEnabled(True)

    # ------------------------------------------------------------------
    # Load roster for selected class & date
    # ------------------------------------------------------------------
    def load_roster(self, show_warnings: bool = True):
        """
        Load students enrolled in the selected class for the chosen date.

        show_warnings:
            - True  -> show popups if there are no classes / no selection.
            - False -> fail silently (used for auto-load at startup, tab-change, etc.).
        """
        self.table.setRowCount(0)

        if not hasattr(self, "class_id_map") or not self.class_id_map:
            if show_warnings:
                QMessageBox.warning(self, "Attendance", "No classes available.")
            return

        index = self.class_combo.currentIndex()
        if index < 0 or index >= len(self.class_id_map):
            if show_warnings:
                QMessageBox.warning(self, "Attendance", "Please select a class.")
            return

        class_id = self.class_id_map[index]

        # Convert QDate to Python date
        qdate = self.date_edit.date()
        att_date = date(qdate.year(), qdate.month(), qdate.day())

        # Get enrolled students for this class
        enrollments = (
            self.session.query(Enrollment)
            .filter(Enrollment.class_id == class_id)
            .all()
        )

        student_ids = [e.student_id for e in enrollments]
        if not student_ids:
            QMessageBox.information(self, "Attendance", "No students enrolled in this class.")
            return
        
        #Order of students in roster
        students = (
            self.session.query(Student)
            .filter(Student.id.in_(student_ids))
            .all()
        )

        # --- Sort students: grade (PreK→12), then last name, then ID ---

        GRADE_ORDER = [
            "PreK",
            "K",
            "1st",
            "2nd",
            "3rd",
            "4th",
            "5th",
            "6th",
            "7th",
            "8th",
            "9th",
            "10th",
            "11th",
            "12th",
        ]

        def normalize_grade_text(s: str) -> str:
            s = s.strip().lower()
            if s in ("pre-k", "pre k", "prek", "prekindergarten"):
                return "prek"
            if s in ("k", "kindergarten"):
                return "k"
            s = s.replace("grade", "").strip()
            s = s.replace(" ", "").replace("-", "")
            return s

        grade_rank_map = {}
        for idx, g in enumerate(GRADE_ORDER):
            grade_rank_map[normalize_grade_text(g)] = idx

        def grade_rank(grade_level: str) -> int:
            if not grade_level:
                return len(GRADE_ORDER) + 1  # unknown grades at bottom

            s = normalize_grade_text(grade_level)
            if s in grade_rank_map:
                return grade_rank_map[s]

            import re
            m = re.match(r"(\d+)", s)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 12:
                    if n == 1:
                        key = "1st"
                    elif n == 2:
                        key = "2nd"
                    elif n == 3:
                        key = "3rd"
                    else:
                        key = f"{n}th"
                    return grade_rank_map.get(
                        normalize_grade_text(key),
                        len(GRADE_ORDER) + 1,
                    )

            return len(GRADE_ORDER) + 1

        def student_sort_key(s):
            return (
                grade_rank(s.grade_level or ""),
                (s.last_name or "").lower(),
                s.id or 0,  # tie-breaker
            )

        students.sort(key=student_sort_key)


        # Preload any existing attendance records for this date & class
        existing = {
            (a.student_id): a
            for a in self.session.query(Attendance)
            .filter(
                Attendance.class_id == class_id,
                Attendance.date == att_date,
            )
            .all()
        }

        self.table.setRowCount(len(students))

        for row, s in enumerate(students):
            self.table.setItem(row, 0, QTableWidgetItem(str(s.id)))
            self.table.setItem(row, 1, QTableWidgetItem(s.first_name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(s.last_name or ""))

            # Status combo box
            combo = QComboBox()
            combo.addItems(self.status_options)

            # If existing attendance, set the status accordingly
            if s.id in existing:
                current_status = existing[s.id].status
                if current_status in self.status_options:
                    combo.setCurrentText(current_status)

            self.table.setCellWidget(row, 3, combo)

        self.table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Mark all students as Present
    # ------------------------------------------------------------------
    def mark_all_present(self):
        rows = self.table.rowCount()
        # Use the first status option as the "present" equivalent
        default_status = self.status_options[0] if self.status_options else "Present"

        for row in range(rows):
            combo = self.table.cellWidget(row, 3)
            if isinstance(combo, QComboBox):
                combo.setCurrentText(default_status)

        # If auto-save is enabled, immediately save after marking all
        self._auto_save_current()

    # ------------------------------------------------------------------
    # Save attendance records to DB
    # ------------------------------------------------------------------
    def save_attendance(self, show_message: bool = True):
        """Save current table entries as attendance for the selected date/class."""
        if not hasattr(self, "class_id_map") or not self.class_id_map:
            QMessageBox.warning(self, "Attendance", "No classes available.")
            return

        index = self.class_combo.currentIndex()
        if index < 0 or index >= len(self.class_id_map):
            QMessageBox.warning(self, "Attendance", "Please select a class.")
            return

        class_id = self.class_id_map[index]

        qdate = self.date_edit.date()
        att_date = date(qdate.year(), qdate.month(), qdate.day())

        rows = self.table.rowCount()
        if rows == 0:
            QMessageBox.information(self, "Attendance", "No students to save.")
            return

        # For now, we'll use a simple marker name; later this can come from logged-in user.
        marked_by = "System"

        for row in range(rows):
            id_item = self.table.item(row, 0)
            if id_item is None:
                continue

            student_id = int(id_item.text())

            combo = self.table.cellWidget(row, 3)
            if not isinstance(combo, QComboBox):
                continue

            status = combo.currentText()

            # Check if an attendance record already exists
            attendance = (
                self.session.query(Attendance)
                .filter(
                    Attendance.student_id == student_id,
                    Attendance.class_id == class_id,
                    Attendance.date == att_date,
                )
                .first()
            )

            if attendance is None:
                # Create new record
                attendance = Attendance(
                    student_id=student_id,
                    class_id=class_id,
                    date=att_date,
                    status=status,
                    marked_by=marked_by,
                    timestamp=datetime.utcnow(),
                )
                self.session.add(attendance)
            else:
                # Update existing record
                attendance.status = status
                attendance.marked_by = marked_by
                attendance.timestamp = datetime.utcnow()

        # Commit all changes at once
        self.session.commit()

        if show_message:
            QMessageBox.information(self, "Attendance", "Attendance saved successfully.")
    
    # ------------------------------------------------------------------
    # Auto-save helper
    # ------------------------------------------------------------------
    def _auto_save_current(self):
        """
        Auto-save the current table if auto-save is enabled and there is data.
        No popups shown.
        """
        if not self.auto_save_enabled:
            return

        if self.table.rowCount() == 0:
            return

        # Reuse main logic, but no popup
        self.save_attendance(show_message=False)

    # ------------------------------------------------------------------
    # Class/date change handler
    # ------------------------------------------------------------------
    def on_class_or_date_changed(self):
        """
        When class or date changes:
        load the roster for the new selection.
        """
        self.load_roster(show_warnings=False)
        
    # ------------------------------------------------------------------
    # Filter class by term on term change
    # ------------------------------------------------------------------
    def on_term_changed(self):
        """
        When the term changes, rebuild the class list to only show classes
        from that term (or all terms).
        """
        self.load_classes()
        # Optionally auto-load roster for the new term/class:
        # self.load_roster(show_warnings=False)
