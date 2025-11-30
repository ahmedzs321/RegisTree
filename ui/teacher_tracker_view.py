from datetime import date, datetime
import json

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QAbstractSpinBox,
    QComboBox,
    QTimeEdit,
    QAbstractItemView,
)
from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtGui import QBrush, QColor

from data.models import (
    Teacher,
    TeacherAttendance,
    CalendarEvent,
    add_audit_log,
)


STATUS_COL = 3
CHECKIN_COL = 4
CHECKOUT_COL = 5


class TeacherTrackerView(QWidget):
    """
    Teacher Tracker tab:
    - Shows list of ACTIVE teachers.
    - Per-day teacher attendance (not tied to classes).
    - Statuses: Present / Absent / No School.
    - Optional check-in/check-out times controlled by Settings.teacher_check_in_out_enabled.
    """

    def __init__(self, session, settings=None):
        super().__init__()
        self.session = session
        self.settings = settings

        # Status options for teachers
        self.status_options = ["Present", "Absent", "No School"]

        self._dirty_rows: set[int] = set()
        self._loading = False

        main_layout = QVBoxLayout()

        # --- Top controls: date + buttons ---
        top_layout = QHBoxLayout()

        top_layout.addWidget(QLabel("Date:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        # Disable spinner arrows to avoid accidental scroll changes
        self.date_edit.setButtonSymbols(QAbstractSpinBox.NoButtons)
        top_layout.addWidget(self.date_edit)

        self.load_button = QPushButton("Load Teachers")
        self.load_button.clicked.connect(
            lambda: self.load_teachers_for_date(show_warnings=True)
        )
        top_layout.addWidget(self.load_button)

        self.mark_all_present_button = QPushButton("Mark All Present")
        self.mark_all_present_button.clicked.connect(self.mark_all_present)
        top_layout.addWidget(self.mark_all_present_button)

        self.save_button = QPushButton("Save Teacher Attendance")
        self.save_button.clicked.connect(self.save_attendance)
        top_layout.addWidget(self.save_button)

        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # Auto-load when date changes (no popups)
        self.date_edit.dateChanged.connect(
            lambda _d: self.load_teachers_for_date(show_warnings=False)
        )

        # --- Table ---
        self.table = QTableWidget()
        self._configure_table_columns()
        # Make cells read-only; use dialogs / widgets for edits
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        main_layout.addWidget(self.table)

        self.setLayout(main_layout)

        # Initial load
        self.load_teachers_for_date(show_warnings=False)

    # ------------------------------------------------------------------
    # Table configuration
    # ------------------------------------------------------------------
    def _configure_table_columns(self):
        """
        Configure table columns/headers based on the current times_enabled flag.
        Called at startup and each time we reload data, so changing the
        setting in SettingsView takes effect without restarting.
        """
        if self.times_enabled:
            self.table.setColumnCount(6)
            self.table.setHorizontalHeaderLabels(
                [
                    "Teacher ID",
                    "First Name",
                    "Last Name",
                    "Status",
                    "Check-In",
                    "Check-Out",
                ]
            )
        else:
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(
                [
                    "Teacher ID",
                    "First Name",
                    "Last Name",
                    "Status",
                ]
            )

    # ------------------------------------------------------------------
    # Auto-save property (live view of Settings)
    # ------------------------------------------------------------------
    @property
    def auto_save_enabled(self) -> bool:
        """
        Always reflect the current settings.attendance_auto_save value,
        so changing it in SettingsView takes effect immediately.
        """
        if self.settings is None:
            return False
        return bool(getattr(self.settings, "attendance_auto_save", False))

    # ------------------------------------------------------------------
    # Times-enabled property (live view of Settings)
    # ------------------------------------------------------------------
    @property
    def times_enabled(self) -> bool:
        """
        Always reflect the current Settings.teacher_check_in_out_enabled value,
        so toggling it in SettingsView takes effect immediately.
        """
        if self.settings is None:
            return False
        return bool(getattr(self.settings, "teacher_check_in_out_enabled", False))

    # ------------------------------------------------------------------
    # Helpers: school days / locking
    # ------------------------------------------------------------------
    def _is_school_day(self, d: date) -> bool:
        """
        True if d is configured as a school day. Defaults to Mon–Fri if unset.
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

    def _locked_event_for_date(self, att_date: date):
        """
        For teacher tracker, a date is locked ONLY if:
          - There is a CalendarEvent of type "No School", OR
          - It is a non-school weekday from Settings.
        "Teachers Only" DOES NOT lock teacher attendance.
        """
        ev = (
            self.session.query(CalendarEvent)
            .filter(
                CalendarEvent.start_date <= att_date,
                CalendarEvent.end_date >= att_date,
                CalendarEvent.event_type == "No School",
            )
            .first()
        )
        if ev is not None:
            return ev

        if not self._is_school_day(att_date):
            class Dummy:
                event_type = "No School"
                title = "Non-school day"
            return Dummy()

        return None

    # ------------------------------------------------------------------
    # Coloring helpers
    # ------------------------------------------------------------------
    def _status_to_color(self, status: str) -> QColor:
        status = (status or "").strip().lower()
        alpha = 30

        if not status:
            return QColor(211, 211, 211, alpha)  # light gray

        if "present" in status:
            return QColor(144, 238, 144, alpha)   # light green
        if "absent" in status:
            return QColor(255, 99, 71, alpha)     # tomato
        if "no school" in status:
            return QColor(186, 85, 211, alpha)    # purple-ish

        return QColor(176, 196, 222, alpha)       # light steel blue (fallback)

    def _apply_dirty_color_row(self, row: int):
        dirty_color = QColor(255, 248, 179, 40)
        brush = QBrush(dirty_color)

        for c in range(self.table.columnCount()):
            item = self.table.item(row, c)
            if item is None:
                item = QTableWidgetItem("")
                self.table.setItem(row, c, item)
            item.setBackground(brush)

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

        if self.times_enabled:
            for col in (CHECKIN_COL, CHECKOUT_COL):
                te = self.table.cellWidget(row, col)
                if isinstance(te, QTimeEdit):
                    r, g, b, a = (
                        dirty_color.red(),
                        dirty_color.green(),
                        dirty_color.blue(),
                        dirty_color.alpha(),
                    )
                    te.setStyleSheet(
                        f"QTimeEdit {{ background-color: rgba({r}, {g}, {b}, {a}); }}"
                    )

    def _apply_status_color_row(self, row: int):
        if row in self._dirty_rows:
            return

        combo = self.table.cellWidget(row, STATUS_COL)
        status_text = ""
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

        if self.times_enabled:
            for col in (CHECKIN_COL, CHECKOUT_COL):
                te = self.table.cellWidget(row, col)
                if isinstance(te, QTimeEdit):
                    if status_text and te.isEnabled():
                        r, g, b, a = (
                            color.red(),
                            color.green(),
                            color.blue(),
                            color.alpha(),
                        )
                        te.setStyleSheet(
                            f"QTimeEdit {{ background-color: rgba({r}, {g}, {b}, {a}); }}"
                        )
                    else:
                        te.setStyleSheet("")

    def _apply_status_colors_all_rows(self):
        for row in range(self.table.rowCount()):
            self._apply_status_color_row(row)

    # ------------------------------------------------------------------
    # Loading teachers
    # ------------------------------------------------------------------
    def _get_current_date(self) -> date:
        qd = self.date_edit.date()
        return date(qd.year(), qd.month(), qd.day())

    def load_teachers_for_date(self, show_warnings: bool = True):
        self._loading = True
        self._dirty_rows.clear()

        # Reconfigure columns in case the check-in/out setting changed
        self._configure_table_columns()

        self.table.setRowCount(0)

        att_date = self._get_current_date()
        locked_event = self._locked_event_for_date(att_date)

        # Active-only teachers
        teachers = (
            self.session.query(Teacher)
            .filter(Teacher.status == "Active")
            .order_by(Teacher.last_name, Teacher.first_name, Teacher.id)
            .all()
        )

        if not teachers:
            self._loading = False
            if show_warnings:
                QMessageBox.information(
                    self,
                    "Teacher Tracker",
                    "No active teachers found.",
                )
            return

        # Existing attendance rows
        existing = {
            ta.teacher_id: ta
            for ta in self.session.query(TeacherAttendance)
            .filter(TeacherAttendance.date == att_date)
            .all()
        }

        self.table.setRowCount(len(teachers))

        for row, t in enumerate(teachers):
            # ID / name columns
            self.table.setItem(row, 0, QTableWidgetItem(str(t.id)))
            self.table.setItem(row, 1, QTableWidgetItem(t.first_name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(t.last_name or ""))

            # Status combo
            combo = QComboBox()
            combo.addItem("")  # blank first
            combo.addItems(self.status_options)

            ta = existing.get(t.id)
            if ta is not None:
                current_status = ta.status or ""
                if current_status in self.status_options:
                    combo.setCurrentText(current_status)
                else:
                    combo.setCurrentIndex(0)
            else:
                combo.setCurrentIndex(0)

            combo.currentIndexChanged.connect(
                lambda _idx, row=row: self.on_status_changed(row)
            )
            self.table.setCellWidget(row, STATUS_COL, combo)

            # Time fields (if enabled)
            if self.times_enabled:
                # Check-in
                check_in_edit = QTimeEdit()
                check_in_edit.setDisplayFormat("HH:mm")
                check_in_edit.setTime(QTime(0, 0))
                check_in_edit.setEnabled(False)
                check_in_edit.timeChanged.connect(
                    lambda _t, row=row: self.on_time_changed(row)
                )
                self.table.setCellWidget(row, CHECKIN_COL, check_in_edit)

                # Check-out
                check_out_edit = QTimeEdit()
                check_out_edit.setDisplayFormat("HH:mm")
                check_out_edit.setTime(QTime(0, 0))
                check_out_edit.setEnabled(False)
                check_out_edit.timeChanged.connect(
                    lambda _t, row=row: self.on_time_changed(row)
                )
                self.table.setCellWidget(row, CHECKOUT_COL, check_out_edit)

                # Populate from existing record
                if ta is not None:
                    if ta.check_in_time is not None:
                        ci = ta.check_in_time
                        check_in_edit.setTime(QTime(ci.hour, ci.minute))
                    if ta.check_out_time is not None:
                        co = ta.check_out_time
                        check_out_edit.setTime(QTime(co.hour, co.minute))

                    # If teacher was marked Present on this date, allow editing times
                    if ta.status == "Present":
                        check_in_edit.setEnabled(True)
                        check_out_edit.setEnabled(True)

        # If date is locked, force No School + disable editing
        if locked_event is not None:
            for row in range(self.table.rowCount()):
                combo = self.table.cellWidget(row, STATUS_COL)
                if isinstance(combo, QComboBox):
                    combo.blockSignals(True)
                    combo.setCurrentText("No School")
                    combo.setEnabled(False)
                    combo.blockSignals(False)

                if self.times_enabled:
                    for col in (CHECKIN_COL, CHECKOUT_COL):
                        te = self.table.cellWidget(row, col)
                        if isinstance(te, QTimeEdit):
                            te.setEnabled(False)
                            te.setTime(QTime(0, 0))

        self._apply_status_colors_all_rows()
        self._loading = False

    # ------------------------------------------------------------------
    # Change handlers
    # ------------------------------------------------------------------
    def on_status_changed(self, row: int):
        if self._loading:
            return

        att_date = self._get_current_date()
        if self._locked_event_for_date(att_date) is not None:
            QMessageBox.warning(
                self,
                "Teacher Attendance Locked",
                "Teacher attendance is locked for this date due to a No School event.",
            )
            self.load_teachers_for_date(show_warnings=False)
            return

        combo = self.table.cellWidget(row, STATUS_COL)
        if not isinstance(combo, QComboBox):
            return

        status_text = combo.currentText().strip()

        # Handle time fields based on status
        if self.times_enabled and 0 <= row < self.table.rowCount():
            check_in_edit = self.table.cellWidget(row, CHECKIN_COL)
            check_out_edit = self.table.cellWidget(row, CHECKOUT_COL)

            if isinstance(check_in_edit, QTimeEdit) and isinstance(
                check_out_edit, QTimeEdit
            ):
                if status_text == "Present":
                    check_in_edit.setEnabled(True)
                    check_out_edit.setEnabled(True)
                else:
                    # Clear + disable when not Present
                    check_in_edit.blockSignals(True)
                    check_out_edit.blockSignals(True)
                    check_in_edit.setTime(QTime(0, 0))
                    check_out_edit.setTime(QTime(0, 0))
                    check_in_edit.setEnabled(False)
                    check_out_edit.setEnabled(False)
                    check_in_edit.blockSignals(False)
                    check_out_edit.blockSignals(False)

        # Mark row dirty and recolor
        self._dirty_rows.add(row)
        self._apply_dirty_color_row(row)

        # Auto-save row if enabled
        if self.auto_save_enabled:
            self._save_single_row(row)
            self.session.commit()
            if row in self._dirty_rows:
                self._dirty_rows.remove(row)
            self._apply_status_color_row(row)

    def on_time_changed(self, row: int):
        if self._loading or not self.times_enabled:
            return

        # If status is not Present, ignore
        combo = self.table.cellWidget(row, STATUS_COL)
        if not isinstance(combo, QComboBox):
            return
        if combo.currentText().strip() != "Present":
            return

        self._dirty_rows.add(row)
        self._apply_dirty_color_row(row)

        if self.auto_save_enabled:
            self._save_single_row(row)
            self.session.commit()
            if row in self._dirty_rows:
                self._dirty_rows.remove(row)
            self._apply_status_color_row(row)

    # ------------------------------------------------------------------
    # Snapshot helper
    # ------------------------------------------------------------------
    def _teacher_attendance_to_dict(self, ta: TeacherAttendance | None):
        if ta is None:
            return None
        return {
            "id": ta.id,
            "teacher_id": ta.teacher_id,
            "date": ta.date.isoformat() if ta.date else None,
            "status": ta.status,
            "check_in_time": ta.check_in_time.isoformat() if ta.check_in_time else None,
            "check_out_time": ta.check_out_time.isoformat()
            if ta.check_out_time
            else None,
            "marked_by": ta.marked_by,
            "timestamp": ta.timestamp.isoformat() if ta.timestamp else None,
        }

    # ------------------------------------------------------------------
    # Core save logic
    # ------------------------------------------------------------------
    def _save_single_row(self, row: int):
        att_date = self._get_current_date()
        if self._locked_event_for_date(att_date) is not None:
            return

        if row < 0 or row >= self.table.rowCount():
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            return

        try:
            teacher_id = int(id_item.text())
        except ValueError:
            return

        combo = self.table.cellWidget(row, STATUS_COL)
        if not isinstance(combo, QComboBox):
            return

        status = combo.currentText().strip()
        marked_by = "System"

        # Time helpers
        def time_to_dt(te: QTimeEdit | None):
            if (
                not self.times_enabled
                or te is None
                or not isinstance(te, QTimeEdit)
                or not te.isEnabled()
            ):
                return None
            t = te.time()
            if not t.isValid():
                return None
            # Treat 00:00 as "no time" so default doesn't get stored
            if t.hour() == 0 and t.minute() == 0 and t.second() == 0:
                return None
            return datetime(
                att_date.year,
                att_date.month,
                att_date.day,
                t.hour(),
                t.minute(),
                t.second(),
            )

        check_in_dt = None
        check_out_dt = None

        if status == "Present" and self.times_enabled:
            check_in_edit = self.table.cellWidget(row, CHECKIN_COL)
            check_out_edit = self.table.cellWidget(row, CHECKOUT_COL)
            if isinstance(check_in_edit, QTimeEdit) and isinstance(
                check_out_edit, QTimeEdit
            ):
                check_in_dt = time_to_dt(check_in_edit)
                check_out_dt = time_to_dt(check_out_edit)

        ta = (
            self.session.query(TeacherAttendance)
            .filter(
                TeacherAttendance.teacher_id == teacher_id,
                TeacherAttendance.date == att_date,
            )
            .first()
        )

        # Blank status → delete existing record if any
        if not status:
            if ta is not None:
                before = self._teacher_attendance_to_dict(ta)
                add_audit_log(
                    self.session,
                    actor=marked_by,
                    action="delete",
                    entity="TeacherAttendance",
                    entity_id=ta.id,
                    before=before,
                    after=None,
                )
                self.session.delete(ta)
            return

        # Create new
        if ta is None:
            ta = TeacherAttendance(
                teacher_id=teacher_id,
                date=att_date,
                status=status,
                check_in_time=check_in_dt,
                check_out_time=check_out_dt,
                marked_by=marked_by,
                timestamp=datetime.utcnow(),
            )
            self.session.add(ta)
            self.session.flush()
            after = self._teacher_attendance_to_dict(ta)
            add_audit_log(
                self.session,
                actor=marked_by,
                action="create",
                entity="TeacherAttendance",
                entity_id=ta.id,
                before=None,
                after=after,
            )
        else:
            before = self._teacher_attendance_to_dict(ta)

            ta.status = status

            # Only modify time fields when check-in/out is enabled.
            # This preserves historical times if the feature is toggled off.
            if self.times_enabled:
                ta.check_in_time = check_in_dt
                ta.check_out_time = check_out_dt

            ta.marked_by = marked_by
            ta.timestamp = datetime.utcnow()

            after = self._teacher_attendance_to_dict(ta)
            add_audit_log(
                self.session,
                actor=marked_by,
                action="update",
                entity="TeacherAttendance",
                entity_id=ta.id,
                before=before,
                after=after,
            )

    # ------------------------------------------------------------------
    # Mark all Present
    # ------------------------------------------------------------------
    def mark_all_present(self):
        att_date = self._get_current_date()
        if self._locked_event_for_date(att_date) is not None:
            QMessageBox.warning(
                self,
                "Teacher Attendance Locked",
                "Teacher attendance is locked for this date due to a No School event.",
            )
            return

        rows = self.table.rowCount()
        default_status = "Present"

        for row in range(rows):
            combo = self.table.cellWidget(row, STATUS_COL)
            if isinstance(combo, QComboBox):
                combo.setCurrentText(default_status)
                # on_status_changed will handle dirty + autosave

        # If we are in manual-save mode, do a one-shot save after marking.
        if not self.auto_save_enabled:
            self._auto_save_current()

    # ------------------------------------------------------------------
    # Save all rows
    # ------------------------------------------------------------------
    def save_attendance(self, show_message: bool = True):
        att_date = self._get_current_date()
        locked_event = self._locked_event_for_date(att_date)
        if locked_event is not None:
            QMessageBox.warning(
                self,
                "Teacher Attendance Locked",
                f"Teacher attendance for {att_date.isoformat()} is locked due to "
                f"{locked_event.event_type} event:\n{locked_event.title}",
            )
            return

        rows = self.table.rowCount()
        if rows == 0:
            QMessageBox.information(
                self,
                "Teacher Attendance",
                "No teachers to save.",
            )
            return

        for row in range(rows):
            self._save_single_row(row)

        self.session.commit()
        self._dirty_rows.clear()
        self._apply_status_colors_all_rows()

        if show_message:
            QMessageBox.information(
                self,
                "Teacher Attendance",
                "Teacher attendance saved successfully.",
            )

    # ------------------------------------------------------------------
    # Auto-save helper
    # ------------------------------------------------------------------
    def _auto_save_current(self):
        if self.table.rowCount() == 0:
            return
        self.save_attendance(show_message=False)