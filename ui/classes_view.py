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
    QDialogButtonBox,
    QMessageBox,
    QLabel,
    QComboBox,
    QDateEdit,
)

from PySide6.QtCore import QDate
from datetime import date
from data.models import Class, Student, Enrollment
from sqlalchemy import or_


class ClassesView(QWidget):
    def __init__(self, session):
        super().__init__()
        self.session = session

        layout = QVBoxLayout()

        # --- Top buttons ---
        btn_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Class")
        self.delete_button = QPushButton("Delete Selected")
        self.manage_enrollments_button = QPushButton("Manage Enrollments")
        btn_layout.addWidget(self.add_button)
        btn_layout.addWidget(self.delete_button)
        btn_layout.addWidget(self.manage_enrollments_button)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # --- Search + Term Filter row ---
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Class name, subject, or teacher…")
        filter_layout.addWidget(self.search_edit)

        filter_layout.addWidget(QLabel("Term:"))
        self.term_filter = QComboBox()
        self.term_filter.addItem("All")
        filter_layout.addWidget(self.term_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # --- Classes table ---
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "Subject", "Teacher", "Term", "Room"]
        )
        layout.addWidget(self.table)

        self.setLayout(layout)

        # Connect buttons
        self.add_button.clicked.connect(self.add_class)
        self.delete_button.clicked.connect(self.delete_class)
        self.manage_enrollments_button.clicked.connect(self.manage_enrollments)

        # Connect filters
        self.search_edit.textChanged.connect(self.load_classes)
        self.term_filter.currentTextChanged.connect(self.load_classes)
        
        # Edit on double-click
        self.table.itemDoubleClicked.connect(self.edit_selected_class)

        # Initial load
        self.load_classes()

    # ------------------------------------------------------------------
    # Load classes from DB into the table
    # ------------------------------------------------------------------
    def load_classes(self):
        """Load classes into the table, applying search + term filter."""
        self.table.setRowCount(0)

        search_text = ""
        term_value = "All"

        if hasattr(self, "search_edit"):
            search_text = self.search_edit.text().strip()

        if hasattr(self, "term_filter"):
            term_value = self.term_filter.currentText()

        # Base query
        query = self.session.query(Class)

        # Term filter
        if term_value != "All":
            query = query.filter(Class.term == term_value)

        # Search filter
        if search_text:
            pattern = f"%{search_text}%"
            query = query.filter(
                or_(
                    Class.name.ilike(pattern),
                    Class.subject.ilike(pattern),
                    Class.teacher_name.ilike(pattern),
                )
            )

        classes = query.order_by(Class.name).all()

        # Update term filter dropdown with distinct terms
        if hasattr(self, "term_filter"):
            # Collect distinct terms from all classes (ignoring filters)
            all_classes = self.session.query(Class).all()
            terms = sorted({c.term for c in all_classes if c.term})
            # Rebuild term filter but keep "All" at top
            current_term = self.term_filter.currentText()
            self.term_filter.blockSignals(True)
            self.term_filter.clear()
            self.term_filter.addItem("All")
            for t in terms:
                self.term_filter.addItem(t)
            # Try to restore previously selected term if possible
            index = self.term_filter.findText(current_term)
            if index >= 0:
                self.term_filter.setCurrentIndex(index)
            self.term_filter.blockSignals(False)

        self.table.setRowCount(len(classes))

        for row, c in enumerate(classes):
            self.table.setItem(row, 0, QTableWidgetItem(str(c.id)))
            self.table.setItem(row, 1, QTableWidgetItem(c.name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(c.subject or ""))
            self.table.setItem(row, 3, QTableWidgetItem(c.teacher_name or ""))
            self.table.setItem(row, 4, QTableWidgetItem(c.term or ""))
            self.table.setItem(row, 5, QTableWidgetItem(c.room or ""))

        self.table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Add a new class
    # ------------------------------------------------------------------
    def add_class(self):
        """Show a dialog to add a new class."""
        dialog = AddClassDialog(self)
        result = dialog.exec()

        if result == QDialog.Accepted:
            data = dialog.get_data()
            if data is None:
                # Validation failed, dialog already showed an error.
                return

            name, subject, teacher_name, term, room = data

            # Build Class object
            c = Class(
                name=name,
                subject=subject,
                teacher_name=teacher_name,
                term=term,
                room=room,
            )

            # Save to DB
            self.session.add(c)
            self.session.commit()

            # Reload table
            self.load_classes()

    # ------------------------------------------------------------------
    # Delete selected class
    # ------------------------------------------------------------------
    def delete_class(self):
        """Delete the currently selected class from the table and DB."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Delete Class", "Please select a class to delete.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Delete Class", "Could not determine class ID.")
            return

        class_id = int(id_item.text())

        # Confirm
        reply = QMessageBox.question(
            self,
            "Delete Class",
            f"Are you sure you want to delete class ID {class_id}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Fetch from DB and delete
        clazz = self.session.get(Class, class_id)
        if clazz is None:
            QMessageBox.warning(self, "Delete Class", "Class not found in database.")
            return

        self.session.delete(clazz)
        self.session.commit()

        # Reload table
        self.load_classes()
    
    # ------------------------------------------------------------------
    # Edit selected class
    # ------------------------------------------------------------------    
    def edit_selected_class(self):
        """Open an edit dialog for the currently selected class."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Edit Class", "Please select a class to edit.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Edit Class", "Could not determine class ID.")
            return

        class_id = int(id_item.text())

        clazz = (
            self.session.query(Class)
            .filter(Class.id == class_id)
            .first()
        )
        if clazz is None:
            QMessageBox.warning(self, "Edit Class", "Class not found in database.")
            return

        dialog = AddClassDialog(self, clazz=clazz)
        result = dialog.exec()

        if result != QMessageBox.Accepted:
            return

        data = dialog.get_data()
        if data is None:
            return

        name, subject, teacher, term, room = data

        clazz.name = name
        clazz.subject = subject
        clazz.teacher_name = teacher
        clazz.term = term
        clazz.room = room

        self.session.commit()
        self.load_classes()

    # ------------------------------------------------------------------
    # Manage enrollments for selected class
    # ------------------------------------------------------------------
    def manage_enrollments(self):
        """Open a dialog to manage which students are enrolled in this class."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Manage Enrollments", "Please select a class first.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Manage Enrollments", "Could not determine class ID.")
            return

        class_id = int(id_item.text())

        clazz = self.session.get(Class, class_id)
        if clazz is None:
            QMessageBox.warning(self, "Manage Enrollments", "Class not found in database.")
            return

        dialog = ManageEnrollmentsDialog(self.session, clazz, self)
        dialog.exec()
        # No need to reload class table; enrollments are separate.


class AddClassDialog(QDialog):
    """
    Dialog to add or edit a Class.
    If 'clazz' is provided, behaves as an Edit dialog.
    """

    def __init__(self, parent=None, clazz: Class | None = None):
        super().__init__(parent)
        self._clazz = clazz
        self.setWindowTitle("Edit Class" if clazz else "Add Class")

        layout = QVBoxLayout()
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.subject_edit = QLineEdit()
        self.teacher_edit = QLineEdit()
        self.term_edit = QLineEdit()
        self.room_edit = QLineEdit()

        form.addRow("Name:", self.name_edit)
        form.addRow("Subject:", self.subject_edit)
        form.addRow("Teacher:", self.teacher_edit)
        form.addRow("Term:", self.term_edit)
        form.addRow("Room:", self.room_edit)

        layout.addLayout(form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)

        self.setLayout(layout)

        # If editing, pre-fill from existing class
        if self._clazz is not None:
            self.name_edit.setText(self._clazz.name or "")
            self.subject_edit.setText(self._clazz.subject or "")
            self.teacher_edit.setText(self._clazz.teacher_name or "")
            self.term_edit.setText(self._clazz.term or "")
            self.room_edit.setText(self._clazz.room or "")

    def get_data(self):
        """
        Return (name, subject, teacher_name, term, room)
        or None if validation fails.
        """
        name = self.name_edit.text().strip()
        subject = self.subject_edit.text().strip()
        teacher = self.teacher_edit.text().strip()
        term = self.term_edit.text().strip()
        room = self.room_edit.text().strip()

        if not name:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Class name is required.",
            )
            return None

        return name, subject, teacher, term, room


class ManageEnrollmentsDialog(QDialog):
    """
    Dialog to assign/remove students from a given class,
    and set enrollment start/end dates.
    """

    def __init__(self, session, clazz: Class, parent=None):
        super().__init__(parent)
        self.session = session
        self.clazz = clazz

        self.setWindowTitle(f"Manage Enrollments - {clazz.name}")

        main_layout = QVBoxLayout()

        # Label at top
        main_layout.addWidget(QLabel(f"Class: {clazz.name} ({clazz.term or ''})"))

        # Table of currently enrolled students
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Student ID", "First Name", "Last Name", "Start Date", "End Date"]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        main_layout.addWidget(QLabel("Enrolled students:"))
        main_layout.addWidget(self.table)

        # Row: dropdown to add a student
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("Add student:"))

        self.student_combo = QComboBox()
        add_layout.addWidget(self.student_combo)

        self.add_student_button = QPushButton("Enroll")
        self.add_student_button.clicked.connect(self.add_enrollment)
        add_layout.addWidget(self.add_student_button)

        add_layout.addStretch()
        main_layout.addLayout(add_layout)

        # Row: date editors to modify start/end dates for the selected student
        dates_layout = QHBoxLayout()
        dates_layout.addWidget(QLabel("Set dates for selected student:"))

        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate())
        dates_layout.addWidget(QLabel("Start:"))
        dates_layout.addWidget(self.start_date_edit)

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())
        dates_layout.addWidget(QLabel("End:"))
        dates_layout.addWidget(self.end_date_edit)

        self.update_dates_button = QPushButton("Update Dates")
        self.update_dates_button.clicked.connect(self.update_dates)
        dates_layout.addWidget(self.update_dates_button)

        dates_layout.addStretch()
        main_layout.addLayout(dates_layout)

        # Button row for removal + close
        buttons_layout = QHBoxLayout()
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self.remove_enrollment)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        buttons_layout.addWidget(self.remove_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(close_button)

        main_layout.addLayout(buttons_layout)

        self.setLayout(main_layout)

        # Load data into table and combo
        self.load_enrollments()
        self.load_available_students()

    # --------------------------------------------------------------
    # Load currently enrolled students into the table
    # --------------------------------------------------------------
    def load_enrollments(self):
        self.table.setRowCount(0)

        enrollments = (
            self.session.query(Enrollment)
            .filter(Enrollment.class_id == self.clazz.id)
            .all()
        )

        self.table.setRowCount(len(enrollments))

        for row, e in enumerate(enrollments):
            student = e.student  # because of relationship
            self.table.setItem(row, 0, QTableWidgetItem(str(student.id)))
            self.table.setItem(row, 1, QTableWidgetItem(student.first_name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(student.last_name or ""))

            start_text = e.start_date.isoformat() if e.start_date else ""
            end_text = e.end_date.isoformat() if e.end_date else ""

            self.table.setItem(row, 3, QTableWidgetItem(start_text))
            self.table.setItem(row, 4, QTableWidgetItem(end_text))

        self.table.resizeColumnsToContents()

    # --------------------------------------------------------------
    # Load students that are NOT yet enrolled in this class
    # into the combo box
    # --------------------------------------------------------------
    def load_available_students(self):
        self.student_combo.clear()

        enrolled_ids = {
            e.student_id
            for e in self.session.query(Enrollment)
            .filter(Enrollment.class_id == self.clazz.id)
            .all()
        }

        available_students = (
            self.session.query(Student)
            .filter(~Student.id.in_(enrolled_ids) if enrolled_ids else True)
            .order_by(Student.last_name, Student.first_name)
            .all()
        )

        self.combo_id_map = []

        for s in available_students:
            label = f"{s.last_name}, {s.first_name} (ID {s.id})"
            self.student_combo.addItem(label)
            self.combo_id_map.append(s.id)

        if not available_students:
            self.student_combo.addItem("(No available students)")
            self.student_combo.setEnabled(False)
            self.add_student_button.setEnabled(False)
        else:
            self.student_combo.setEnabled(True)
            self.add_student_button.setEnabled(True)

    # --------------------------------------------------------------
    # Enroll selected student from combo into this class
    # --------------------------------------------------------------
    def add_enrollment(self):
        if not hasattr(self, "combo_id_map") or not self.combo_id_map:
            QMessageBox.information(self, "Enroll", "No students available to enroll.")
            return

        index = self.student_combo.currentIndex()
        if index < 0 or index >= len(self.combo_id_map):
            QMessageBox.warning(self, "Enroll", "Please select a valid student.")
            return

        student_id = self.combo_id_map[index]

        existing = (
            self.session.query(Enrollment)
            .filter(
                Enrollment.student_id == student_id,
                Enrollment.class_id == self.clazz.id,
            )
            .first()
        )
        if existing:
            QMessageBox.information(
                self, "Enroll", "That student is already enrolled in this class."
            )
            return

        e = Enrollment(
            student_id=student_id,
            class_id=self.clazz.id,
            start_date=date.today(),
            end_date=None,
        )
        self.session.add(e)
        self.session.commit()

        self.load_enrollments()
        self.load_available_students()

    # --------------------------------------------------------------
    # Update start/end dates for the selected enrollment
    # --------------------------------------------------------------
    def update_dates(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Update Dates", "Please select a student row first.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Update Dates", "Could not determine student ID.")
            return

        student_id = int(id_item.text())

        e = (
            self.session.query(Enrollment)
            .filter(
                Enrollment.student_id == student_id,
                Enrollment.class_id == self.clazz.id,
            )
            .first()
        )
        if e is None:
            QMessageBox.warning(self, "Update Dates", "Enrollment not found in database.")
            return

        # Get dates from the QDateEdits
        s_qdate = self.start_date_edit.date()
        e_qdate = self.end_date_edit.date()

        e.start_date = date(s_qdate.year(), s_qdate.month(), s_qdate.day())
        e.end_date = date(e_qdate.year(), e_qdate.month(), e_qdate.day())

        self.session.commit()
        self.load_enrollments()

    # --------------------------------------------------------------
    # Remove selected enrollment (student from this class)
    # --------------------------------------------------------------
    def remove_enrollment(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Remove", "Please select a student to remove.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Remove", "Could not determine student ID.")
            return

        student_id = int(id_item.text())

        reply = QMessageBox.question(
            self,
            "Remove Enrollment",
            f"Remove student ID {student_id} from this class?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        e = (
            self.session.query(Enrollment)
            .filter(
                Enrollment.student_id == student_id,
                Enrollment.class_id == self.clazz.id,
            )
            .first()
        )
        if e is None:
            QMessageBox.warning(self, "Remove", "Enrollment not found in database.")
            return

        self.session.delete(e)
        self.session.commit()

        self.load_enrollments()
        self.load_available_students()

