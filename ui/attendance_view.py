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
)
from PySide6.QtCore import QDate

from data.models import Class, Student, Enrollment, Attendance


class AttendanceView(QWidget):
    """
    Attendance tab:
    - Select a class and date.
    - Load roster of enrolled students.
    - Mark attendance (Present/Absent/Tardy/Excused).
    - Save records to the database.
    """

    STATUS_OPTIONS = ["Present", "Absent", "Tardy", "Excused"]

    def __init__(self, session):
        super().__init__()
        self.session = session

        main_layout = QVBoxLayout()

        # --- Top controls: class + date + buttons ---
        top_layout = QHBoxLayout()

        top_layout.addWidget(QLabel("Class:"))
        self.class_combo = QComboBox()
        top_layout.addWidget(self.class_combo)

        top_layout.addWidget(QLabel("Date:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        top_layout.addWidget(self.date_edit)

        self.load_button = QPushButton("Load Roster")
        self.load_button.clicked.connect(self.load_roster)
        top_layout.addWidget(self.load_button)

        self.mark_all_present_button = QPushButton("Mark All Present")
        self.mark_all_present_button.clicked.connect(self.mark_all_present)
        top_layout.addWidget(self.mark_all_present_button)

        self.save_button = QPushButton("Save Attendance")
        self.save_button.clicked.connect(self.save_attendance)
        top_layout.addWidget(self.save_button)

        top_layout.addStretch()

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
        self.class_combo.clear()
        classes = self.session.query(Class).order_by(Class.name).all()

        self.class_id_map = []  # index -> class_id
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
    def load_roster(self):
        """Load students enrolled in the selected class for the chosen date."""
        self.table.setRowCount(0)

        if not hasattr(self, "class_id_map") or not self.class_id_map:
            QMessageBox.warning(self, "Attendance", "No classes available.")
            return

        index = self.class_combo.currentIndex()
        if index < 0 or index >= len(self.class_id_map):
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

        students = (
            self.session.query(Student)
            .filter(Student.id.in_(student_ids))
            .order_by(Student.last_name, Student.first_name)
            .all()
        )

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
            combo.addItems(self.STATUS_OPTIONS)

            # If existing attendance, set the status accordingly
            if s.id in existing:
                current_status = existing[s.id].status
                if current_status in self.STATUS_OPTIONS:
                    combo.setCurrentText(current_status)

            self.table.setCellWidget(row, 3, combo)

        self.table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Mark all students as Present
    # ------------------------------------------------------------------
    def mark_all_present(self):
        rows = self.table.rowCount()
        for row in range(rows):
            combo = self.table.cellWidget(row, 3)
            if isinstance(combo, QComboBox):
                combo.setCurrentText("Present")

    # ------------------------------------------------------------------
    # Save attendance records to DB
    # ------------------------------------------------------------------
    def save_attendance(self):
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

        QMessageBox.information(self, "Attendance", "Attendance saved successfully.")
