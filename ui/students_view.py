import re
from datetime import date
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
from sqlalchemy import or_
from data.models import Student

class StudentsView(QWidget):
    def __init__(self, session, settings=None):
        super().__init__()
        self.session = session
        self.settings = settings

        # Build initial grade choices for Add/Edit dialog
        self.refresh_grade_choices()

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
    # Refresh grade choices in drop down menu
    # ------------------------------------------------------------------
    def refresh_grade_choices(self):
        """
        Rebuild the list of allowed grade choices from self.settings
        (starting_grade → graduating_grade) on the canonical PreK–12 scale.
        Called at startup and whenever Settings are changed.
        """
        canonical_scale = [
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

        # Defaults if settings are missing
        start_name = "K"
        grad_name = "12th"
        if getattr(self, "settings", None) is not None:
            if getattr(self.settings, "starting_grade", None):
                start_name = self.settings.starting_grade
            if getattr(self.settings, "graduating_grade", None):
                grad_name = self.settings.graduating_grade

        if start_name not in canonical_scale:
            start_name = "K"
        if grad_name not in canonical_scale:
            grad_name = "12th"

        start_idx = canonical_scale.index(start_name)
        grad_idx = canonical_scale.index(grad_name)

        if start_idx <= grad_idx:
            self.grade_choices = canonical_scale[start_idx : grad_idx + 1]
        else:
            # Fallback if Settings are somehow inverted
            self.grade_choices = canonical_scale

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

        # Order by grade
        students = query.all()

        # --- Custom sort: grade (PreK→12), then last name, then ID ---

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
        # Build a mapping from normalized grade text → rank
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

            # Fallback: try to parse number like "5", "5th", "5thgrade"
            import re
            m = re.match(r"(\d+)", s)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 12:
                    # Map 1→"1st", 2→"2nd", 3→"3rd", else "nth"
                    if n == 1:
                        key = "1st"
                    elif n == 2:
                        key = "2nd"
                    elif n == 3:
                        key = "3rd"
                    else:
                        key = f"{n}th"
                    return grade_rank_map.get(normalize_grade_text(key), len(GRADE_ORDER) + 1)

            return len(GRADE_ORDER) + 1

        def student_sort_key(s):
            return (
                grade_rank(s.grade_level or ""),
                (s.last_name or "").lower(),
                s.id or 0,  # tie-breaker
            )

        students.sort(key=student_sort_key)

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
        dialog = AddStudentDialog(self, grade_choices=self.grade_choices)
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

        dialog = AddStudentDialog(self, student=student, grade_choices=self.grade_choices)
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
    
    # ------------------------------------------------------------------
    # Promote student by grade level
    # ------------------------------------------------------------------   
    def _promote_grade_level(self, grade_level: str):
        """
        Given the student's current grade_level string, return (new_grade_level, became_graduate).

        This uses a configurable grade range from Settings (starting_grade, graduating_grade)
        over a canonical PreK–12 scale. If the grade text doesn't match the canonical list,
        we fall back to a numeric-based heuristic.
        """
        if not grade_level:
            return None, False

        # Canonical PreK–12 scale
        canonical_scale = [
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

        def normalize(s: str) -> str:
            """Normalize a grade string for comparison."""
            s = s.strip().lower()
            # common synonyms
            if s in ("pre-k", "pre k", "prek", "prekindergarten"):
                return "prek"
            if s in ("k", "kindergarten"):
                return "k"
            # remove words like 'grade'
            s = s.replace("grade", "").strip()
            # remove spaces and hyphens
            s = s.replace(" ", "").replace("-", "")
            return s

        # Build mapping from normalized text to canonical index
        norm_to_index = {}
        for idx, g in enumerate(canonical_scale):
            n = normalize(g)
            norm_to_index[n] = idx

        # Determine the allowed range from settings, defaulting to K–12th
        start_name = "K"
        grad_name = "12th"
        if getattr(self, "settings", None) is not None:
            if self.settings.starting_grade:
                start_name = self.settings.starting_grade
            if self.settings.graduating_grade:
                grad_name = self.settings.graduating_grade

        # Ensure they exist in the canonical list
        if start_name not in canonical_scale:
            start_name = "K"
        if grad_name not in canonical_scale:
            grad_name = "12th"

        start_idx = canonical_scale.index(start_name)
        grad_idx = canonical_scale.index(grad_name)

        # Try to match the student's grade_level against canonical list
        norm_grade = normalize(grade_level)
        if norm_grade in norm_to_index:
            idx = norm_to_index[norm_grade]

            # If grade is at or beyond the graduating grade in this school's scale,
            # mark as Graduated (no further promotion).
            if idx >= grad_idx:
                return grade_level, True

            # If grade is before starting grade, we could either skip or bump up.
            # For now, if below starting grade, just move up one within the full scale.
            new_idx = idx + 1

            # Clamp within the overall canonical scale
            new_idx = min(new_idx, len(canonical_scale) - 1)
            new_grade = canonical_scale[new_idx]
            # If we just went beyond the graduating index, treat as graduate
            if new_idx > grad_idx:
                return grade_level, True

            return new_grade, False

        # ------------------------------------------------------------------
        # Fallback: numeric-based heuristic (old logic) for weird values
        # ------------------------------------------------------------------
        s = grade_level.strip().lower()

        # Kindergarten
        if s in ("k", "kindergarten"):
            return "1st", False

        m = re.match(r"(\d+)", s)
        if not m:
            return None, False

        n = int(m.group(1))

        # Interpret the graduating grade as a number if possible
        # (e.g. "12th" -> 12)
        grad_num = 12
        m_grad = re.match(r"(\d+)", grad_name.lower())
        if m_grad:
            grad_num = int(m_grad.group(1))

        # >= graduating number -> Graduate
        if n >= grad_num:
            return grade_level, True

        new_n = n + 1

        if new_n % 10 == 1 and new_n != 11:
            suffix = "st"
        elif new_n % 10 == 2 and new_n != 12:
            suffix = "nd"
        elif new_n % 10 == 3 and new_n != 13:
            suffix = "rd"
        else:
            suffix = "th"

        return f"{new_n}{suffix}", False

    # ------------------------------------------------------------------
    # Promote all student by a grade level
    # ------------------------------------------------------------------
    def promote_all_students(self):
        """
        Promote all Active students to the next grade.
        - Active students only.
        - Graduated students are not touched.
        - Top grade (e.g. school's graduating grade) students are marked as Graduated.

        NOTE: Any confirmation or admin password checks should be done
        by the caller (e.g. SettingsView) before calling this method.
        """
        # Query all Active students
        active_students = (
            self.session.query(Student)
            .filter(Student.status == "Active")
            .all()
        )

        promoted_count = 0
        graduated_count = 0
        skipped_count = 0

        for student in active_students:
            new_grade, became_graduate = self._promote_grade_level(student.grade_level)

            if new_grade is None and not became_graduate:
                # Could not interpret grade_level nicely -> skip
                skipped_count += 1
                continue

            if became_graduate:
                # Mark as Graduated, keep grade_level as-is
                student.status = "Graduated"
                graduated_count += 1

            if new_grade is not None and not became_graduate:
                student.grade_level = new_grade
                promoted_count += 1

        self.session.commit()

        # Refresh the table to reflect changes
        if hasattr(self, "load_students"):
            self.load_students()

        QMessageBox.information(
            self,
            "Promote Students",
            f"Promotion complete.\n\n"
            f"Promoted: {promoted_count}\n"
            f"Marked Graduated: {graduated_count}\n"
            f"Skipped (unrecognized grade): {skipped_count}",
        )

class AddStudentDialog(QDialog):
    """
    Dialog to collect student info.
    If 'student' is provided, behaves as an Edit dialog (fields pre-filled).
    """

    def __init__(self, parent=None, student: Student | None = None, grade_choices=None):
        super().__init__(parent)
        self._student = student

        # Grade options for the combo box (from StudentsView)
        if grade_choices is not None and len(grade_choices) > 0:
            self._grade_choices = list(grade_choices)
        else:
            # Fallback: full PreK–12 scale if nothing was passed in
            self._grade_choices = [
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
        
        self.setWindowTitle("Edit Student" if student else "Add Student")

        layout = QVBoxLayout()

        form = QFormLayout()

        self.first_name_edit = QLineEdit()
        self.last_name_edit = QLineEdit()

        # Date of birth
        self.dob_edit = QDateEdit()
        self.dob_edit.setCalendarPopup(True)

        # Grade level (combo box)
        self.grade_combo = QComboBox()
        self.grade_combo.addItems(self._grade_choices)

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
        form.addRow("Grade Level:", self.grade_combo)
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

            existing_grade = self._student.grade_level or ""
            if existing_grade:
                idx = self.grade_combo.findText(existing_grade)
                if idx < 0:
                    # If the student's grade is outside the current range,
                    # add it so we don't lose that information.
                    self.grade_combo.addItem(existing_grade)
                    idx = self.grade_combo.count() - 1
                self.grade_combo.setCurrentIndex(idx)
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
        grade_level = self.grade_combo.currentText().strip()
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

