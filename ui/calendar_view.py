from datetime import date, timedelta
import json

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QCalendarWidget,
    QDialog,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QSizePolicy,
    QHeaderView,
)
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QPainter

from data.models import Attendance, Student, Class, Enrollment, CalendarEvent, add_audit_log


# ----------------------------------------------------------------------
# Helper serializers for audit logs
# ----------------------------------------------------------------------
def attendance_to_dict(a: Attendance | None):
    if a is None:
        return None
    return {
        "id": a.id,
        "student_id": a.student_id,
        "class_id": a.class_id,
        "date": a.date.isoformat() if a.date else None,
        "status": a.status,
        "marked_by": a.marked_by,
        "timestamp": a.timestamp.isoformat() if getattr(a, "timestamp", None) else None,
    }


def event_to_dict(ev: CalendarEvent | None):
    if ev is None:
        return None
    return {
        "id": ev.id,
        "title": ev.title,
        "start_date": ev.start_date.isoformat() if ev.start_date else None,
        "end_date": ev.end_date.isoformat() if ev.end_date else None,
        "event_type": ev.event_type,
        "notes": ev.notes,
    }


# ----------------------------------------------------------------------
# Custom calendar widget that can draw colored dots + labels
# ----------------------------------------------------------------------
class AttendanceCalendarWidget(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._day_styles = {}  # QDate -> {"bg": QColor | None, "label": str | None}

        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)

    def clear_day_styles(self):
        self._day_styles.clear()
        self.updateCells()

    def set_day_style(self, qdate: QDate, bg_color: QColor | None, label: str | None):
        # Only update internal data; caller will trigger repaint once.
        self._day_styles[qdate] = {"bg": bg_color, "label": label}

    def paintCell(self, painter: QPainter, rect, qdate: QDate):
        info = self._day_styles.get(qdate)

        # First let the default calendar draw the day number, selection, etc.
        super().paintCell(painter, rect, qdate)

        # Draw event label (small text near bottom) if we have one
        if info and info.get("label"):
            painter.save()
            painter.setPen(Qt.black)
            text_rect = rect.adjusted(2, rect.height() // 2, -2, -2)
            painter.drawText(
                text_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                info["label"],
            )
            painter.restore()

        # Draw the color dot in the top-right corner if bg color is set
        if info and info.get("bg"):
            painter.save()
            color = info["bg"]
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)

            # Small circle in the top-right
            radius = min(rect.width(), rect.height()) // 8  # small dot
            cx = rect.right() - radius - 2
            cy = rect.top() + radius + 2
            painter.drawEllipse(cx - radius, cy - radius, 2 * radius, 2 * radius)

            painter.restore()


# ----------------------------------------------------------------------
# Main Calendar View
# ----------------------------------------------------------------------
class CalendarView(QWidget):
    """
    Month-view calendar for attendance + events.

    - Color-codes days based on attendance (present-heavy vs absence-heavy).
    - Overlays "No School" / "Teachers Only" / Custom events.
    - Non-school weekdays (from Settings) act as automatic "No School".
    - Clicking a date lets you view attendance or create/manage events.
    """

    def __init__(self, session, settings=None, attendance_view=None):
        super().__init__()
        self.session = session
        self.settings = settings
        self.attendance_view = attendance_view  # not strictly required, but kept for future integration

        main_layout = QVBoxLayout()

        title = QLabel("<h1>Attendance Calendar</h1>")
        main_layout.addWidget(title)

        # --- Calendar group ---
        calendar_group = QGroupBox("Monthly Attendance")
        calendar_layout = QVBoxLayout()

        self.calendar = AttendanceCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        calendar_layout.addWidget(self.calendar)

        # Info + buttons for selected date
        bottom_layout = QHBoxLayout()
        self.selected_date_label = QLabel("")
        bottom_layout.addWidget(self.selected_date_label)

        bottom_layout.addStretch()

        self.view_attendance_button = QPushButton("View Attendance for This Day")
        self.view_attendance_button.clicked.connect(self.on_view_attendance_clicked)
        bottom_layout.addWidget(self.view_attendance_button)

        self.add_event_button = QPushButton("Add Event…")
        self.add_event_button.clicked.connect(self.on_add_event_clicked)
        bottom_layout.addWidget(self.add_event_button)

        calendar_layout.addLayout(bottom_layout)

        # --- Legend for calendar colors ---
        legend_group = QGroupBox("Legend")
        legend_layout = QHBoxLayout()

        def add_legend_item(text: str, rgb_tuple):
            lbl_color = QLabel()
            lbl_color.setFixedSize(16, 16)
            r, g, b = rgb_tuple
            lbl_color.setStyleSheet(
                f"background-color: rgb({r}, {g}, {b}); border: 1px solid gray;"
            )
            lbl_text = QLabel(text)
            item_layout = QHBoxLayout()
            item_layout.addWidget(lbl_color)
            item_layout.addWidget(lbl_text)
            item_layout.setSpacing(4)
            container = QWidget()
            container.setLayout(item_layout)
            legend_layout.addWidget(container)

        # Match colors used in refresh_month_colors
        add_legend_item("No School / Non-school day", (186, 85, 211))
        add_legend_item("Teachers Only", (147, 112, 219))
        add_legend_item("Custom Event", (135, 206, 235))
        add_legend_item("Good attendance (low absence)", (144, 238, 144))
        add_legend_item("Mixed attendance", (255, 215, 0))
        add_legend_item("High absence", (255, 99, 71))

        legend_layout.addStretch()
        legend_group.setLayout(legend_layout)
        calendar_layout.addWidget(legend_group)

        calendar_group.setLayout(calendar_layout)

        main_layout.addWidget(calendar_group)

        self.setLayout(main_layout)

        # Signals
        self.calendar.selectionChanged.connect(self.on_selection_changed)
        self.calendar.clicked.connect(self.on_date_clicked)
        self.calendar.currentPageChanged.connect(self.on_month_changed)

        # Initial state
        self.on_selection_changed()
        self.refresh_month_colors()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _current_pydate(self) -> date:
        qd = self.calendar.selectedDate()
        return date(qd.year(), qd.month(), qd.day())

    def _month_range_for_current_page(self) -> tuple[date, date]:
        """
        Return (start, end) for the month currently shown in the calendar,
        not the month of the selectedDate.
        """
        year = self.calendar.yearShown()
        month = self.calendar.monthShown()

        start_q = QDate(year, month, 1)
        end_q = start_q.addMonths(1).addDays(-1)
        start = date(start_q.year(), start_q.month(), start_q.day())
        end = date(end_q.year(), end_q.month(), end_q.day())
        return start, end

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
    # UI updates
    # ------------------------------------------------------------------
    def on_selection_changed(self):
        d = self._current_pydate()
        self.selected_date_label.setText(f"Selected date: {d.isoformat()}")

    def on_month_changed(self, year: int, month: int):
        # When user navigates month, refresh colors/labels
        self.refresh_month_colors()

    def on_date_clicked(self, qdate: QDate):
        """
        Clicking a date pops a small dialog with choices:
        - View attendance for that day
        - Add event
        - Manage existing events
        """
        selected = date(qdate.year(), qdate.month(), qdate.day())
        self.selected_date_label.setText(f"Selected date: {selected.isoformat()}")

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Options for {selected.isoformat()}")

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Date: {selected.isoformat()}"))

        # Show existing events on that date (if any)
        events = (
            self.session.query(CalendarEvent)
            .filter(
                CalendarEvent.start_date <= selected,
                CalendarEvent.end_date >= selected,
            )
            .order_by(CalendarEvent.start_date)
            .all()
        )
        if events:
            lines = []
            for ev in events:
                if ev.start_date == ev.end_date:
                    date_str = ev.start_date.isoformat()
                else:
                    date_str = f"{ev.start_date.isoformat()} → {ev.end_date.isoformat()}"
                lines.append(f"- {date_str}: {ev.event_type} – {ev.title}")
            lbl = QLabel("Existing events:\n" + "\n".join(lines))
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
        else:
            layout.addWidget(QLabel("No events for this date."))

        btn_row = QHBoxLayout()
        btn_view = QPushButton("View Attendance")
        btn_event = QPushButton("Add Event…")
        btn_manage = QPushButton("Manage Events…")
        btn_close = QPushButton("Close")

        btn_row.addWidget(btn_view)
        btn_row.addWidget(btn_event)
        btn_row.addWidget(btn_manage)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)
        dialog.setLayout(layout)

        def do_view():
            dialog.accept()
            self.show_attendance_details(selected)

        def do_event():
            dialog.accept()
            self.open_event_dialog(selected)

        def do_manage():
            dialog.accept()
            self.open_event_manager(selected)

        btn_view.clicked.connect(do_view)
        btn_event.clicked.connect(do_event)
        btn_manage.clicked.connect(do_manage)
        btn_close.clicked.connect(dialog.reject)

        dialog.exec()

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def on_view_attendance_clicked(self):
        self.show_attendance_details(self._current_pydate())

    def on_add_event_clicked(self):
        self.open_event_dialog(self._current_pydate())

    # ------------------------------------------------------------------
    # Attendance details dialog
    # ------------------------------------------------------------------
    def show_attendance_details(self, day: date):
        """
        Show a table of attendance across ALL classes for this day.
        """
        rows = (
            self.session.query(Attendance, Student, Class)
            .join(Student, Attendance.student_id == Student.id)
            .join(Class, Attendance.class_id == Class.id)
            .filter(Attendance.date == day)
            .order_by(Student.last_name, Student.first_name, Class.name)
            .all()
        )

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Attendance for {day.isoformat()}")

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Date: {day.isoformat()}"))

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            ["Student ID", "Name", "Class", "Status", "Marked By"]
        )

        table.setRowCount(len(rows))
        for i, (a, s, c) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(str(s.id)))
            table.setItem(i, 1, QTableWidgetItem(f"{s.last_name}, {s.first_name}"))
            table.setItem(i, 2, QTableWidgetItem(c.name or ""))
            table.setItem(i, 3, QTableWidgetItem(a.status or ""))
            table.setItem(i, 4, QTableWidgetItem(a.marked_by or ""))

        table.resizeColumnsToContents()
        layout.addWidget(table)

        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        dialog.setLayout(layout)
        dialog.resize(800, 500)
        dialog.exec()

    # ------------------------------------------------------------------
    # Event creation dialog
    # ------------------------------------------------------------------
    def open_event_dialog(self, default_day: date):
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Event")

        form = QFormLayout()

        title_edit = QLineEdit()
        title_edit.setPlaceholderText("e.g. Winter Break, In-Service Day")
        form.addRow("Title:", title_edit)

        type_combo = QComboBox()
        type_combo.addItems(["No School", "Teachers Only", "Custom"])
        form.addRow("Event type:", type_combo)

        start_edit = QDateEdit()
        start_edit.setCalendarPopup(True)
        start_edit.setDate(QDate(default_day.year, default_day.month, default_day.day))
        form.addRow("Start date:", start_edit)

        end_edit = QDateEdit()
        end_edit.setCalendarPopup(True)
        end_edit.setDate(QDate(default_day.year, default_day.month, default_day.day))
        form.addRow("End date:", end_edit)

        notes_edit = QPlainTextEdit()
        notes_edit.setPlaceholderText("Optional notes…")
        form.addRow("Notes:", notes_edit)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        main_layout.addWidget(btn_box)
        dialog.setLayout(main_layout)

        def on_accept():
            title = title_edit.text().strip()
            if not title:
                QMessageBox.warning(dialog, "Event", "Please enter a title for the event.")
                return

            s_q = start_edit.date()
            e_q = end_edit.date()
            start_d = date(s_q.year(), s_q.month(), s_q.day())
            end_d = date(e_q.year(), e_q.month(), e_q.day())

            if end_d < start_d:
                QMessageBox.warning(
                    dialog,
                    "Event",
                    "End date must be on or after the start date.",
                )
                return

            event_type = type_combo.currentText()
            notes = notes_edit.toPlainText().strip() or None

            ev = CalendarEvent(
                title=title,
                start_date=start_d,
                end_date=end_d,
                event_type=event_type,
                notes=notes,
            )
            self.session.add(ev)
            # Ensure ID is available
            self.session.flush()
            add_audit_log(
                self.session,
                actor="System",
                action="create",
                entity="CalendarEvent",
                entity_id=ev.id,
                before=None,
                after=event_to_dict(ev),
            )
            self.session.commit()

            # If No School or Teachers Only → auto-mark attendance as "No School"
            if event_type in ("No School", "Teachers Only"):
                self._apply_no_school_attendance(start_d, end_d)

            self.refresh_month_colors()
            dialog.accept()

        btn_box.accepted.connect(on_accept)
        btn_box.rejected.connect(dialog.reject)

        dialog.exec()

    # ------------------------------------------------------------------
    # Event manager dialog (edit/delete events for a given day)
    # ------------------------------------------------------------------
    def open_event_manager(self, target_day: date):
        """
        Manage events that cover target_day:
        - list them in a table
        - allow editing fields
        - allow deleting rows
        """
        events = (
            self.session.query(CalendarEvent)
            .filter(
                CalendarEvent.start_date <= target_day,
                CalendarEvent.end_date >= target_day,
            )
            .order_by(CalendarEvent.start_date)
            .all()
        )

        # Snapshot BEFORE edits for audit comparisons
        before_snapshots = {ev.id: event_to_dict(ev) for ev in events}

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Manage Events for {target_day.isoformat()}")

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Events covering {target_day.isoformat()}:"))

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Title", "Type", "Start", "End", "Notes"])
        table.setRowCount(len(events))

        for row, ev in enumerate(events):
            table.setItem(row, 0, QTableWidgetItem(ev.title or ""))
            table.setItem(row, 1, QTableWidgetItem(ev.event_type or ""))
            table.setItem(row, 2, QTableWidgetItem(ev.start_date.isoformat()))
            table.setItem(row, 3, QTableWidgetItem(ev.end_date.isoformat()))
            table.setItem(row, 4, QTableWidgetItem(ev.notes or ""))

        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(table)

        btn_row = QHBoxLayout()
        btn_new = QPushButton("New Event")
        btn_save = QPushButton("Save Changes")
        btn_delete = QPushButton("Delete Selected")
        btn_close = QPushButton("Close")

        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_delete)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dialog.setLayout(layout)
        dialog.resize(700, 400)

        def create_new():
            # Use the standard create dialog with default_day = target_day
            self.open_event_dialog(target_day)
            dialog.accept()
            self.refresh_month_colors()

        def save_changes():
            from datetime import datetime as dt

            for row, ev in enumerate(events):
                title_item = table.item(row, 0)
                type_item = table.item(row, 1)
                start_item = table.item(row, 2)
                end_item = table.item(row, 3)
                notes_item = table.item(row, 4)

                if not title_item or not type_item or not start_item or not end_item:
                    continue

                ev.title = title_item.text().strip() or ev.title
                ev.event_type = type_item.text().strip() or ev.event_type

                try:
                    s = start_item.text().strip()
                    e = end_item.text().strip()
                    ev.start_date = dt.fromisoformat(s).date()
                    ev.end_date = dt.fromisoformat(e).date()
                except Exception:
                    # If parse fails, ignore date change for that row
                    pass

                ev.notes = (notes_item.text().strip() or None) if notes_item else ev.notes

                # Audit log this update
                before = before_snapshots.get(ev.id)
                after = event_to_dict(ev)
                add_audit_log(
                    self.session,
                    actor="System",
                    action="update",
                    entity="CalendarEvent",
                    entity_id=ev.id,
                    before=before,
                    after=after,
                )

            self.session.commit()
            self.refresh_month_colors()
            QMessageBox.information(dialog, "Events", "Changes saved.")

        def delete_selected():
            selected_rows = {idx.row() for idx in table.selectedIndexes()}
            if not selected_rows:
                QMessageBox.information(dialog, "Events", "No row selected.")
                return

            reply = QMessageBox.question(
                dialog,
                "Delete Events",
                "Delete the selected event(s)?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            for row in sorted(selected_rows, reverse=True):
                if 0 <= row < len(events):
                    ev = events[row]
                    before = event_to_dict(ev)
                    add_audit_log(
                        self.session,
                        actor="System",
                        action="delete",
                        entity="CalendarEvent",
                        entity_id=ev.id,
                        before=before,
                        after=None,
                    )
                    self.session.delete(ev)
                    table.removeRow(row)
                    events.pop(row)

            self.session.commit()
            self.refresh_month_colors()

        btn_new.clicked.connect(create_new)
        btn_save.clicked.connect(save_changes)
        btn_delete.clicked.connect(delete_selected)
        btn_close.clicked.connect(dialog.reject)

        dialog.exec()

    # ------------------------------------------------------------------
    # Apply No School attendance for a date range
    # ------------------------------------------------------------------
    def _apply_no_school_attendance(self, start_d: date, end_d: date):
        """
        For every student in every class (via Enrollment),
        mark attendance as "No School" for all days in [start_d, end_d].
        """
        all_enrollments = self.session.query(Enrollment).all()
        if not all_enrollments:
            return

        current = start_d
        from datetime import datetime as dt

        while current <= end_d:
            for enr in all_enrollments:
                attendance = (
                    self.session.query(Attendance)
                    .filter(
                        Attendance.student_id == enr.student_id,
                        Attendance.class_id == enr.class_id,
                        Attendance.date == current,
                    )
                    .first()
                )
                if attendance is None:
                    attendance = Attendance(
                        student_id=enr.student_id,
                        class_id=enr.class_id,
                        date=current,
                        status="No School",
                        marked_by="System(Event)",
                        timestamp=dt.utcnow(),
                    )
                    self.session.add(attendance)
                    # Ensure ID is available before logging
                    self.session.flush()
                    add_audit_log(
                        self.session,
                        actor="System",
                        action="create",
                        entity="Attendance",
                        entity_id=attendance.id,
                        before=None,
                        after=attendance_to_dict(attendance),
                    )
                else:
                    before = attendance_to_dict(attendance)
                    attendance.status = "No School"
                    attendance.marked_by = "System(Event)"
                    attendance.timestamp = dt.utcnow()
                    after = attendance_to_dict(attendance)
                    add_audit_log(
                        self.session,
                        actor="System",
                        action="update",
                        entity="Attendance",
                        entity_id=attendance.id,
                        before=before,
                        after=after,
                    )
            current += timedelta(days=1)

        self.session.commit()

    # ------------------------------------------------------------------
    # Month coloring (attendance + events)
    # ------------------------------------------------------------------
    def refresh_month_colors(self):
        """
        Color-code days based on attendance and overlay events.

        - Greenish if present-heavy
        - Yellowish if mixed
        - Red if absence-heavy
        - Purple-ish for No School / Teachers Only / non-school days
        - Blue-ish for Custom events
        """
        self.calendar.clear_day_styles()

        start, end = self._month_range_for_current_page()

        # --- Gather events in this month range ---
        events = (
            self.session.query(CalendarEvent)
            .filter(
                CalendarEvent.start_date <= end,
                CalendarEvent.end_date >= start,
            )
            .all()
        )

        # Map each date -> highest-priority event (No School > Teachers Only > Custom)
        day_event = {}  # date -> CalendarEvent

        priority = {"No School": 2, "Teachers Only": 1, "Custom": 0}

        for ev in events:
            current = max(ev.start_date, start)
            last = min(ev.end_date, end)
            while current <= last:
                old = day_event.get(current)
                if (old is None) or (
                    priority.get(ev.event_type, 0) > priority.get(old.event_type, 0)
                ):
                    day_event[current] = ev
                current += timedelta(days=1)

        # Treat non-school weekdays as implicit "No School", unless an event overrides
        for day_d in (start + timedelta(days=i) for i in range((end - start).days + 1)):
            if not self._is_school_day(day_d) and day_d not in day_event:
                class DummyEvent:
                    def __init__(self, d):
                        self.start_date = d
                        self.end_date = d
                        self.event_type = "No School"
                        self.title = "Non-school day"
                        self.notes = None

                day_event[day_d] = DummyEvent(day_d)

        # --- Gather attendance stats in this month range ---
        rows = (
            self.session.query(Attendance)
            .filter(
                Attendance.date >= start,
                Attendance.date <= end,
            )
            .all()
        )

        # Compute per (student, date) worst status
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

        status_priority = {
            "No School": 0,
            "Absent": 1,
            "Tardy": 2,
            "Excused": 3,
            "Present": 4,
            "Other": 2,
        }

        per_student_day = {}  # (student_id, date) -> canonical status
        for a in rows:
            key = (a.student_id, a.date)
            status = canonical_status(a.status)
            if key not in per_student_day:
                per_student_day[key] = status
            else:
                existing = per_student_day[key]
                if status_priority[status] < status_priority[existing]:
                    per_student_day[key] = status

        # Count per day
        day_counts: dict[date, dict[str, int]] = {}
        for (sid, d), status in per_student_day.items():
            bucket = day_counts.setdefault(d, {})
            bucket[status] = bucket.get(status, 0) + 1

        # --- Decide colors per day and apply to calendar ---
        for day_d in (start + timedelta(days=i) for i in range((end - start).days + 1)):
            qd = QDate(day_d.year, day_d.month, day_d.day)

            # Event overlay (including implicit non-school days)
            ev = day_event.get(day_d)
            if ev is not None:
                if ev.event_type == "No School":
                    bg = QColor(186, 85, 211, 150)   # purple-ish
                    label = "No School"
                elif ev.event_type == "Teachers Only":
                    bg = QColor(147, 112, 219, 150)  # slightly different purple
                    label = "Teachers"
                else:
                    bg = QColor(135, 206, 235, 120)  # light sky blue for custom
                    label = ev.title[:8]  # short label
                self.calendar.set_day_style(qd, bg, label)
                continue  # event color takes precedence

            # Attendance-based coloring
            counts = day_counts.get(day_d)
            if not counts:
                continue  # no style, default look

            present = counts.get("Present", 0)
            absent = counts.get("Absent", 0)
            tardy = counts.get("Tardy", 0)

            total = present + absent + tardy
            if total <= 0:
                continue

            absence_ratio = absent / total

            if absence_ratio <= 0.1:
                bg = QColor(144, 238, 144, 120)   # light green
            elif absence_ratio <= 0.3:
                bg = QColor(255, 215, 0, 120)     # yellow/gold
            else:
                bg = QColor(255, 99, 71, 120)     # red-ish

            self.calendar.set_day_style(qd, bg, None)

        # Single repaint after all styles are set
        self.calendar.updateCells()
