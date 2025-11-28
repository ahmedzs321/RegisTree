from datetime import date, datetime
import json

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
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush, QColor
from data.models import (
    Class,
    Student,
    Enrollment,
    Attendance,
    CalendarEvent,
    add_audit_log,
)


STATUS_COL = 3  # column index for "Status"


class AttendanceView(QWidget):
    """
    Attendance tab:
    - Select a class and date.
    - Load roster of enrolled students.
    - Mark attendance using customizable statuses.
    - Save records to the database.
    """

    DEFAULT_STATUS_OPTIONS = ["Present", "Absent", "Tardy", "Excused", "No School"]

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

        # Track dirty (unsaved) rows and a load guard
        self._dirty_rows = set()
        self._loading = False

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
    # Helpers for coloring / dirty tracking
    # ------------------------------------------------------------------
    def _status_to_color(self, status: str) -> QColor:
        """
        Transparent status backgrounds for visibility.
        """
        status = (status or "").strip().lower()
        alpha = 30  # transparency

        if not status:
            # Explicit blank/unedited rows stay light gray
            return QColor(211, 211, 211, alpha)

        if "present" in status:
            return QColor(144, 238, 144, alpha)    # light green
        if "absent" in status:
            return QColor(255, 99, 71, alpha)      # tomato red
        if "tardy" in status or "late" in status:
            return QColor(255, 215, 0, alpha)      # gold
        if "excused" in status:
            return QColor(135, 206, 250, alpha)    # light blue
        if "no school" in status:
            return QColor(186, 85, 211, alpha)     # purple-ish

        # Custom statuses
        return QColor(176, 196, 222, alpha)         # light steel blue

    def _apply_dirty_color_row(self, row: int):
        """Color a row as 'unsaved' with a very soft, transparent yellow."""
        # RGBA: pale yellow with low alpha
        dirty_color = QColor(255, 248, 179, 40)  # alpha 40/255 ≈ 16% opacity
        brush = QBrush(dirty_color)

        for c in range(self.table.columnCount()):
            item = self.table.item(row, c)
            if item is None:
                # create an empty item just to hold the background
                item = QTableWidgetItem("")
                self.table.setItem(row, c, item)
            item.setBackground(brush)

        # Match the combobox background to the same transparent color
        combo = self.table.cellWidget(row, STATUS_COL)
        if isinstance(combo, QComboBox):
            r, g, b, a = (
                dirty_color.red(),
                dirty_color.green(),
                dirty_color.blue(),
                dirty_color.alpha(),
            )
            combo.setStyleSheet(
                f"QComboBox {{ background-color: rgba({r}, {g}, {b}, {a}); }}"
            )

    def _apply_status_color_row(self, row: int):
        """Color a row according to its status (saved state)."""
        if row in self._dirty_rows:
            # Dirty color overrides status color
            return

        status_text = ""
        combo = self.table.cellWidget(row, STATUS_COL)
        if isinstance(combo, QComboBox):
            status_text = combo.currentText().strip()

        color = self._status_to_color(status_text)
        brush = QBrush(color)

        for c in range(self.table.columnCount()):
            item = self.table.item(row, c)
            if item is None:
                item = QTableWidgetItem("")
                self.table.setItem(row, c, item)
            item.setBackground(brush)

        if isinstance(combo, QComboBox):
            if status_text:
                # Use same RGBA as the row, so the shade matches
                r, g, b, a = (
                    color.red(),
                    color.green(),
                    color.blue(),
                    color.alpha(),
                )
                combo.setStyleSheet(
                    f"QComboBox {{ background-color: rgba({r}, {g}, {b}, {a}); }}"
                )
            else:
                combo.setStyleSheet("")

    def _apply_status_colors_all_rows(self):
        for row in range(self.table.rowCount()):
            self._apply_status_color_row(row)

    def _is_school_day(self, d: date) -> bool:
        """
        Return True if d is configured as a school day, False otherwise.
        Defaults to Mon–Fri if not configured.
        """
        if self.settings is None:
            return d.weekday() < 5  # 0–4 = Mon–Fri

        try:
            raw = getattr(self.settings, "school_days_json", "") or ""
            if raw:
                days = json.loads(raw)
            else:
                days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        except Exception:
            days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

        day_keys = {
            0: "Mon",
            1: "Tue",
            2: "Wed",
            3: "Thu",
            4: "Fri",
            5: "Sat",
            6: "Sun",
        }
        return day_keys[d.weekday()] in set(days)

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
        self._loading = True
        self._dirty_rows.clear()
        self.table.setRowCount(0)

        if not hasattr(self, "class_id_map") or not self.class_id_map:
            self._loading = False
            if show_warnings:
                QMessageBox.warning(self, "Attendance", "No classes available.")
            return

        index = self.class_combo.currentIndex()
        if index < 0 or index >= len(self.class_id_map):
            self._loading = False
            if show_warnings:
                QMessageBox.warning(self, "Attendance", "Please select a class.")
            return

        class_id = self.class_id_map[index]

        # Convert QDate to Python date
        qdate = self.date_edit.date()
        att_date = date(qdate.year(), qdate.month(), qdate.day())

        # Check if this date is locked (No School / Teachers Only / non-school day)
        locked_event = self._locked_event_for_date(att_date)

        # Get enrolled students for this class
        enrollments = (
            self.session.query(Enrollment)
            .filter(Enrollment.class_id == class_id)
            .all()
        )

        student_ids = [e.student_id for e in enrollments]
        if not student_ids:
            self._loading = False
            QMessageBox.information(self, "Attendance", "No students enrolled in this class.")
            return
        
        # Order of students in roster
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

        from PySide6.QtWidgets import QComboBox  # ensure imported

        for row, s in enumerate(students):
            self.table.setItem(row, 0, QTableWidgetItem(str(s.id)))
            self.table.setItem(row, 1, QTableWidgetItem(s.first_name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(s.last_name or ""))

            # Status combo box
            combo = QComboBox()
            # Blank first, THEN statuses
            combo.addItem("")  
            combo.addItems(self.status_options)

            # If existing attendance, set the status accordingly
            if s.id in existing:
                current_status = existing[s.id].status or ""
                if current_status in self.status_options:
                    combo.setCurrentText(current_status)
                else:
                    combo.setCurrentIndex(0)  # blank
            else:
                combo.setCurrentIndex(0)  # blank

            # Connect change handler AFTER initial setup
            combo.currentIndexChanged.connect(
                lambda idx, row=row: self.on_status_changed(row)
            )

            self.table.setCellWidget(row, STATUS_COL, combo)

        # If date is locked, force "No School" + disable editing,
        # but do NOT show a popup here (only when user actually tries to edit).
        if locked_event is not None:
            for row in range(self.table.rowCount()):
                combo = self.table.cellWidget(row, STATUS_COL)
                if isinstance(combo, QComboBox):
                    combo.blockSignals(True)
                    combo.setCurrentText("No School")
                    combo.setEnabled(False)
                    combo.blockSignals(False)

        # Apply colors after final statuses are set
        self._apply_status_colors_all_rows()

        # Finished loading
        self._loading = False

    # ------------------------------------------------------------------
    # Row-level status change handler
    # ------------------------------------------------------------------
    def on_status_changed(self, row: int):
        if self._loading:
            return  # ignore changes while loading roster

        # Prevent editing on locked No School / Teachers Only / non-school days
        class_id, att_date = self._get_current_class_and_date()
        if att_date is not None and self._locked_event_for_date(att_date) is not None:
            QMessageBox.warning(
                self,
                "Attendance Locked",
                "Attendance is locked for this date due to a No School / Teachers Only event.",
            )
            # Reload roster to restore original values
            self.load_roster(show_warnings=False)
            return

        # Mark row as dirty
        self._dirty_rows.add(row)
        self._apply_dirty_color_row(row)

        # Auto-save per row if enabled
        if self.auto_save_enabled:
            self._save_single_row(row)
            self.session.commit()
            # After commit, clear dirty + recolor by status
            if row in self._dirty_rows:
                self._dirty_rows.remove(row)
            self._apply_status_color_row(row)

    # ------------------------------------------------------------------
    # Helper to get current (class_id, date)
    # ------------------------------------------------------------------
    def _get_current_class_and_date(self):
        if not hasattr(self, "class_id_map") or not self.class_id_map:
            return None, None

        index = self.class_combo.currentIndex()
        if index < 0 or index >= len(self.class_id_map):
            return None, None

        class_id = self.class_id_map[index]

        qdate = self.date_edit.date()
        att_date = date(qdate.year(), qdate.month(), qdate.day())

        return class_id, att_date

    # ------------------------------------------------------------------
    # Lock attendance for no school day
    # ------------------------------------------------------------------
    def _locked_event_for_date(self, att_date: date):
        """
        Return a CalendarEvent that locks attendance for att_date,
        a synthetic non-school day object, or None.
        """
        ev = (
            self.session.query(CalendarEvent)
            .filter(
                CalendarEvent.start_date <= att_date,
                CalendarEvent.end_date >= att_date,
                CalendarEvent.event_type.in_(["No School", "Teachers Only"]),
            )
            .first()
        )
        if ev is not None:
            return ev

        # Non-school weekdays (from Settings) are implicitly locked as No School
        if not self._is_school_day(att_date):
            class Dummy:
                event_type = "No School"
                title = "Non-school day"
            return Dummy()

        return None

    # ------------------------------------------------------------------
    # Snapshot helper for audit logging
    # ------------------------------------------------------------------
    def _attendance_to_dict(self, attendance: Attendance):
        if attendance is None:
            return None
        return {
            "id": attendance.id,
            "student_id": attendance.student_id,
            "class_id": attendance.class_id,
            "date": attendance.date.isoformat() if attendance.date else None,
            "status": attendance.status,
            "marked_by": attendance.marked_by,
            "timestamp": attendance.timestamp.isoformat() if attendance.timestamp else None,
        }

    # ------------------------------------------------------------------
    # Save a single row to DB (no popups)
    # ------------------------------------------------------------------
    def _save_single_row(self, row: int):
        class_id, att_date = self._get_current_class_and_date()
        if class_id is None:
            return

        if att_date is not None and self._locked_event_for_date(att_date) is not None:
            # Do not save on locked days
            return

        if row < 0 or row >= self.table.rowCount():
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            return

        try:
            student_id = int(id_item.text())
        except ValueError:
            return

        combo = self.table.cellWidget(row, STATUS_COL)
        if not isinstance(combo, QComboBox):
            return

        status = combo.currentText().strip()
        marked_by = "System"

        attendance = (
            self.session.query(Attendance)
            .filter(
                Attendance.student_id == student_id,
                Attendance.class_id == class_id,
                Attendance.date == att_date,
            )
            .first()
        )

        # Blank status → treat as "no record": delete if exists
        if not status:
            if attendance is not None:
                before = self._attendance_to_dict(attendance)
                add_audit_log(
                    self.session,
                    actor=marked_by,
                    action="delete",
                    entity="Attendance",
                    entity_id=attendance.id,
                    before=before,
                    after=None,
                )
                self.session.delete(attendance)
            return

        # Create new record
        if attendance is None:
            attendance = Attendance(
                student_id=student_id,
                class_id=class_id,
                date=att_date,
                status=status,
                marked_by=marked_by,
                timestamp=datetime.utcnow(),
            )
            self.session.add(attendance)
            # Ensure ID is available for the log entry
            self.session.flush()
            after = self._attendance_to_dict(attendance)
            add_audit_log(
                self.session,
                actor=marked_by,
                action="create",
                entity="Attendance",
                entity_id=attendance.id,
                before=None,
                after=after,
            )
        else:
            # Update existing record
            before = self._attendance_to_dict(attendance)

            attendance.status = status
            attendance.marked_by = marked_by
            attendance.timestamp = datetime.utcnow()

            after = self._attendance_to_dict(attendance)

            add_audit_log(
                self.session,
                actor=marked_by,
                action="update",
                entity="Attendance",
                entity_id=attendance.id,
                before=before,
                after=after,
            )

    # ------------------------------------------------------------------
    # Mark all students as Present
    # ------------------------------------------------------------------
    def mark_all_present(self):
        class_id, att_date = self._get_current_class_and_date()
        if att_date is not None and self._locked_event_for_date(att_date) is not None:
            QMessageBox.warning(
                self,
                "Attendance Locked",
                "Attendance is locked for this date due to a No School / Teachers Only event.",
            )
            return

        rows = self.table.rowCount()
        # Use the first status option as the "present" equivalent
        default_status = self.status_options[0] if self.status_options else "Present"

        for row in range(rows):
            combo = self.table.cellWidget(row, STATUS_COL)
            if isinstance(combo, QComboBox):
                combo.setCurrentText(default_status)
                # on_status_changed will be triggered and handle dirty + autosave if enabled

        # If auto-save is disabled, do a bulk save without popup
        if not self.auto_save_enabled:
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

        qdate = self.date_edit.date()
        att_date = date(qdate.year(), qdate.month(), qdate.day())

        locked_event = self._locked_event_for_date(att_date)
        if locked_event is not None:
            QMessageBox.warning(
                self,
                "Attendance Locked",
                f"Attendance for {att_date.isoformat()} is locked due to "
                f"{locked_event.event_type} event:\n{locked_event.title}",
            )
            return

        rows = self.table.rowCount()
        if rows == 0:
            QMessageBox.information(self, "Attendance", "No students to save.")
            return

        # Use row-level helper so logic + audit logging is consistent
        for row in range(rows):
            self._save_single_row(row)

        # Commit all changes at once
        self.session.commit()

        # After commit, clear dirty flags and recolor all rows
        self._dirty_rows.clear()
        self._apply_status_colors_all_rows()

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
