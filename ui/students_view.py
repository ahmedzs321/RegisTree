from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QDialog,
    QFormLayout,
    QLineEdit,
    QLabel,
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QMessageBox,
)

from PySide6.QtCore import QDate
from datetime import date
from data.models import Student
from sqlalchemy import or_


class StudentsView(QWidget):
    def __init__(self, session):
        super().__init__()
        self.session = session

        layout = QVBoxLayout()

        # --- Top buttons (Add / Delete) ---
        btn_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Student")
        self.delete_button = QPushButton("Delete Selected")
        btn_layout.addWidget(self.add_button)
        btn_layout.addWidget(self.delete_button)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # --- Search + Status Filter row ---
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Name or ID…")
        filter_layout.addWidget(self.search_edit)

        filter_layout.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Active", "Inactive", "Graduated"])
        filter_layout.addWidget(self.status_filter)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # --- Students table ---
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "First Name",
                "Last Name",
                "DOB",
                "Grade",
                "Status",
                "Email",
                "Guardian Name",
                "Guardian Phone",
            ]
        )
        layout.addWidget(self.table)

        self.setLayout(layout)

        # Button actions
        self.add_button.clicked.connect(self.add_student)
        self.delete_button.clicked.connect(self.delete_student)

        # Search/filter actions
        self.search_edit.textChanged.connect(self.load_students)
        self.status_filter.currentTextChanged.connect(self.load_students)
        
        # Edit on double-click
        self.table.itemDoubleClicked.connect(self.edit_selected_student)

        # Initial load
        self.load_students()

    # ------------------------------------------------------------------
    # Load students from DB into the table
    # ------------------------------------------------------------------
    def load_students(self):
        """Load students into the table, applying search + status filter."""
        self.table.setRowCount(0)

        # Get current filter values
        search_text = ""
        status_value = "All"

        if hasattr(self, "search_edit"):
            search_text = self.search_edit.text().strip()

        if hasattr(self, "status_filter"):
            status_value = self.status_filter.currentText()

        # Build base query
        query = self.session.query(Student)

        # Status filter
        if status_value != "All":
            query = query.filter(Student.status == status_value)

        # Search filter (by id or name)
        if search_text:
            # Try to parse numeric ID
            try:
                search_id = int(search_text)
            except ValueError:
                search_id = None

            like_pattern = f"%{search_text}%"

            filters = [
                Student.first_name.ilike(like_pattern),
                Student.last_name.ilike(like_pattern),
            ]
            if search_id is not None:
                filters.append(Student.id == search_id)

            query = query.filter(or_(*filters))

        # Order by last, first
        students = query.order_by(Student.last_name, Student.first_name).all()

        self.table.setRowCount(len(students))

        for row, s in enumerate(students):
            self.table.setItem(row, 0, QTableWidgetItem(str(s.id)))
            self.table.setItem(row, 1, QTableWidgetItem(s.first_name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(s.last_name or ""))
            self.table.setItem(
                row, 3, QTableWidgetItem(s.dob.isoformat() if s.dob else "")
            )
            self.table.setItem(row, 4, QTableWidgetItem(s.grade_level or ""))
            self.table.setItem(row, 5, QTableWidgetItem(s.status or ""))
            self.table.setItem(row, 6, QTableWidgetItem(s.contact_email or ""))
            self.table.setItem(row, 7, QTableWidgetItem(s.guardian_name or ""))
            self.table.setItem(row, 8, QTableWidgetItem(s.guardian_phone or ""))

        self.table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Add a new student
    # ------------------------------------------------------------------
    def add_student(self):
        """Show a dialog to add a new student."""
        dialog = AddStudentDialog(self)
        result = dialog.exec()

        if result == QDialog.Accepted:
            data = dialog.get_data()
            if data is None:
                # Dialog will already show an error message; just return.
                return

            # Unpack the data
            (
                first_name,
                last_name,
                dob,
                grade_level,
                status,
                email,
                guardian_name,
                guardian_phone,
            ) = data

            # Create a new Student object
            s = Student(
                first_name=first_name,
                last_name=last_name,
                dob=dob,
                grade_level=grade_level,
                status=status,
                contact_email=email,
                guardian_name=guardian_name,
                guardian_phone=guardian_phone,
            )

            # Save to DB
            self.session.add(s)
            self.session.commit()

            # Reload table
            self.load_students()


    # ------------------------------------------------------------------
    # Delete selected student
    # ------------------------------------------------------------------
    def delete_student(self):
        """Delete the currently selected student from the table and DB."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Delete Student", "Please select a student to delete.")
            return

        # ID is in column 0
        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Delete Student", "Could not determine student ID.")
            return

        student_id = int(id_item.text())

        # Confirm with the user
        reply = QMessageBox.question(
            self,
            "Delete Student",
            f"Are you sure you want to delete student ID {student_id}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Look up the student in the DB and delete
        student = self.session.get(Student, student_id)
        if student is None:
            QMessageBox.warning(self, "Delete Student", "Student not found in database.")
            return

        self.session.delete(student)
        self.session.commit()

        # Reload table
        self.load_students()
        
    # ------------------------------------------------------------------
    # Edit selected student
    # ------------------------------------------------------------------    
    def edit_selected_student(self):
        """Open an edit dialog for the currently selected student."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Edit Student", "Please select a student to edit.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Edit Student", "Could not determine student ID.")
            return

        student_id = int(id_item.text())

        student = (
            self.session.query(Student)
            .filter(Student.id == student_id)
            .first()
        )

        if student is None:
            QMessageBox.warning(self, "Edit Student", "Student not found in database.")
            return

        dialog = AddStudentDialog(self, student=student)
        result = dialog.exec()

        if result != QDialog.Accepted:
            return

        data = dialog.get_data()
        if data is None:
            return

        (
            first_name,
            last_name,
            dob,
            grade_level,
            status,
            email,
            guardian_name,
            guardian_phone,
        ) = data

        # Update fields
        student.first_name = first_name
        student.last_name = last_name
        student.dob = dob
        student.grade_level = grade_level
        student.status = status
        student.contact_email = email
        student.guardian_name = guardian_name
        student.guardian_phone = guardian_phone

        self.session.commit()
        self.load_students()


class AddStudentDialog(QDialog):
    """
    Dialog to collect student info.
    If 'student' is provided, behaves as an Edit dialog (fields pre-filled).
    """

    def __init__(self, parent=None, student: Student | None = None):
        super().__init__(parent)
        self._student = student
        self.setWindowTitle("Edit Student" if student else "Add Student")

        layout = QVBoxLayout()

        form = QFormLayout()

        self.first_name_edit = QLineEdit()
        self.last_name_edit = QLineEdit()

        # Date of birth
        self.dob_edit = QDateEdit()
        self.dob_edit.setCalendarPopup(True)

        # Grade level (free text)
        self.grade_edit = QLineEdit()

        # Status combo box
        self.status_combo = QComboBox()
        self.status_combo.addItems(["Active", "Inactive", "Graduated"])

        self.email_edit = QLineEdit()

        # Guardian name and phone
        self.guardian_name_edit = QLineEdit()
        self.guardian_phone_edit = QLineEdit()

        form.addRow("First Name:", self.first_name_edit)
        form.addRow("Last Name:", self.last_name_edit)
        form.addRow("Date of Birth:", self.dob_edit)
        form.addRow("Grade Level:", self.grade_edit)
        form.addRow("Status:", self.status_combo)
        form.addRow("Email:", self.email_edit)
        form.addRow("Guardian Name:", self.guardian_name_edit)
        form.addRow("Guardian Phone:", self.guardian_phone_edit)

        layout.addLayout(form)

        # OK / Cancel buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)

        self.setLayout(layout)

        # If editing, pre-fill fields from existing student
        if self._student is not None:
            self.first_name_edit.setText(self._student.first_name or "")
            self.last_name_edit.setText(self._student.last_name or "")
            if self._student.dob:
                self.dob_edit.setDate(QDate(
                    self._student.dob.year,
                    self._student.dob.month,
                    self._student.dob.day,
                ))
            else:
                self.dob_edit.setDate(QDate.currentDate())

            self.grade_edit.setText(self._student.grade_level or "")
            status = self._student.status or "Active"
            idx = self.status_combo.findText(status)
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)
            self.email_edit.setText(self._student.contact_email or "")
            self.guardian_name_edit.setText(self._student.guardian_name or "")
            self.guardian_phone_edit.setText(self._student.guardian_phone or "")
        else:
            # Adding new student → default DOB to today
            self.dob_edit.setDate(QDate.currentDate())

    def get_data(self):
        """
        Return the data as a tuple:
        (first_name, last_name, dob (date), grade_level, status, email,
         guardian_name, guardian_phone)
        If validation fails, return None.
        """
        first_name = self.first_name_edit.text().strip()
        last_name = self.last_name_edit.text().strip()
        grade_level = self.grade_edit.text().strip()
        status = self.status_combo.currentText()
        email = self.email_edit.text().strip()
        guardian_name = self.guardian_name_edit.text().strip()
        guardian_phone = self.guardian_phone_edit.text().strip()

        if not first_name or not last_name or not grade_level:
            QMessageBox.warning(
                self,
                "Validation Error",
                "First name, last name, and grade level are required.",
            )
            return None

        qdate = self.dob_edit.date()
        dob = date(qdate.year(), qdate.month(), qdate.day())

        return (
            first_name,
            last_name,
            dob,
            grade_level,
            status,
            email,
            guardian_name,
            guardian_phone,
        )

