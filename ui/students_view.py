import re
from datetime import date, timedelta
from pathlib import Path
import shutil

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
    QTextEdit,
    QGroupBox,
    QFileDialog,
    QSizePolicy,
)
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPixmap
from sqlalchemy import or_

from data.models import Student, Class, Enrollment, Attendance, add_audit_log
from ui.undo_manager import UndoManager   # <-- NEW


def student_to_dict(student: Student | None):
    """Convert a Student ORM object into a JSON-serializable dict for audit logs."""
    if student is None:
        return None
    return {
        "id": student.id,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "dob": student.dob.isoformat() if student.dob else None,
        "grade_level": student.grade_level,
        "status": student.status,
        "contact_email": student.contact_email,
        "guardian_name": student.guardian_name,
        "guardian_phone": student.guardian_phone,
        "guardian_email": student.guardian_email,
        "emergency_contact_name": student.emergency_contact_name,
        "emergency_contact_phone": student.emergency_contact_phone,
        "notes": student.notes,
        "photo_path": getattr(student, "photo_path", None),
    }


class StudentsView(QWidget):
    def __init__(
        self,
        session,
        settings=None,
        undo_manager: UndoManager | None = None,  # <-- NEW PARAM
    ):
        super().__init__()
        self.session = session
        self.settings = settings
        self.undo_manager = undo_manager          # <-- STORE IT

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
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "First Name",
                "Last Name",
                "DOB",
                "Grade",
                "Email",                 # student email
                "Guardian Name",
                "Guardian Phone",
                "Guardian Email",
                "Emergency Contact Name",
                "Emergency Contact Phone",
                "Status",
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

        # Double-click → open profile (not raw edit dialog)
        self.table.itemDoubleClicked.connect(self.open_student_profile)

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

        # Order by grade (PreK → 12), then last name, then id
        students = query.all()

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

            # Fallback: try to parse number like "5", "5th", "5thgrade"
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

        self.table.setRowCount(len(students))

        for row, s in enumerate(students):
            self.table.setItem(row, 0, QTableWidgetItem(str(s.id)))
            self.table.setItem(row, 1, QTableWidgetItem(s.first_name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(s.last_name or ""))
            self.table.setItem(row, 3, QTableWidgetItem(s.dob.isoformat() if s.dob else ""))
            self.table.setItem(row, 4, QTableWidgetItem(s.grade_level or ""))
            self.table.setItem(row, 5, QTableWidgetItem(s.contact_email or ""))
            self.table.setItem(row, 6, QTableWidgetItem(s.guardian_name or ""))
            self.table.setItem(row, 7, QTableWidgetItem(s.guardian_phone or ""))
            self.table.setItem(row, 8, QTableWidgetItem(s.guardian_email or ""))
            self.table.setItem(row, 9, QTableWidgetItem(s.emergency_contact_name or ""))
            self.table.setItem(row, 10, QTableWidgetItem(s.emergency_contact_phone or ""))
            self.table.setItem(row, 11, QTableWidgetItem(s.status or ""))

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
                guardian_email,
                emergency_name,
                emergency_phone,
                notes,
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
                guardian_email=guardian_email,
                emergency_contact_name=emergency_name,
                emergency_contact_phone=emergency_phone,
                notes=notes,
            )

            self.session.add(s)
            # Ensure we have an ID for logging
            self.session.flush()
            after = student_to_dict(s)
            add_audit_log(
                self.session,
                actor="System",
                action="create",
                entity="Student",
                entity_id=s.id,
                before=None,
                after=after,
            )

            self.session.commit()
            self.load_students()

    # ------------------------------------------------------------------
    # Delete selected student (UNDOABLE)
    # ------------------------------------------------------------------
    def delete_student(self):
        """Delete the currently selected student from the table and DB (undoable)."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, "Delete Student", "Please select a student to delete."
            )
            return

        # ID is in column 0
        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(
                self, "Delete Student", "Could not determine student ID."
            )
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

        # Look up the student in the DB
        student = self.session.get(Student, student_id)
        if student is None:
            QMessageBox.warning(
                self, "Delete Student", "Student not found in database."
            )
            return

        # Snapshot the student's fields for undo
        snapshot = {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "dob": student.dob,
            "grade_level": student.grade_level,
            "status": student.status,
            "contact_email": student.contact_email,
            "guardian_name": student.guardian_name,
            "guardian_phone": student.guardian_phone,
            "guardian_email": student.guardian_email,
            "emergency_contact_name": student.emergency_contact_name,
            "emergency_contact_phone": student.emergency_contact_phone,
            "notes": student.notes,
            "photo_path": getattr(student, "photo_path", None),
        }

        def redo_delete():
            obj = self.session.get(Student, snapshot["id"])
            if obj is None:
                return
            before = student_to_dict(obj)
            add_audit_log(
                self.session,
                actor="System",
                action="delete",
                entity="Student",
                entity_id=obj.id,
                before=before,
                after=None,
            )
            self.session.delete(obj)
            self.session.commit()
            self.load_students()

        def undo_delete():
            existing = self.session.get(Student, snapshot["id"])
            if existing is not None:
                return

            restored = Student(
                id=snapshot["id"],
                first_name=snapshot["first_name"],
                last_name=snapshot["last_name"],
                dob=snapshot["dob"],
                grade_level=snapshot["grade_level"],
                status=snapshot["status"],
                contact_email=snapshot["contact_email"],
                guardian_name=snapshot["guardian_name"],
                guardian_phone=snapshot["guardian_phone"],
                guardian_email=snapshot["guardian_email"],
                emergency_contact_name=snapshot["emergency_contact_name"],
                emergency_contact_phone=snapshot["emergency_contact_phone"],
                notes=snapshot["notes"],
            )
            if snapshot["photo_path"] is not None:
                restored.photo_path = snapshot["photo_path"]

            self.session.add(restored)
            after = student_to_dict(restored)
            add_audit_log(
                self.session,
                actor="System",
                action="create",
                entity="Student",
                entity_id=restored.id,
                before=None,
                after=after,
            )
            self.session.commit()
            self.load_students()

        # Perform the delete now
        redo_delete()

        # Register with UndoManager
        if self.undo_manager is not None:
            self.undo_manager.push(
                undo_delete,
                redo_delete,
                f"Delete student {student_id}",
            )

    # ------------------------------------------------------------------
    # Open student profile
    # ------------------------------------------------------------------
    def open_student_profile(self, item=None):
        """Open profile dialog for the selected student."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, "Student Profile", "Please select a student first."
            )
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(
                self, "Student Profile", "Could not determine student ID."
            )
            return

        student_id = int(id_item.text())

        student = (
            self.session.query(Student)
            .filter(Student.id == student_id)
            .first()
        )
        if student is None:
            QMessageBox.warning(
                self, "Student Profile", "Student not found in database."
            )
            return

        dialog = StudentProfileDialog(self.session, student, parent_view=self, parent=self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Edit selected student (UNDOABLE – used by profile dialog)
    # ------------------------------------------------------------------
    def edit_selected_student_by_id(self, student_id: int):
        """Open edit dialog for a given student id (undoable)."""
        student = (
            self.session.query(Student)
            .filter(Student.id == student_id)
            .first()
        )

        if student is None:
            QMessageBox.warning(self, "Edit Student", "Student not found in database.")
            return

        # Snapshot BEFORE edit (for both undo and audit)
        before_snapshot = student_to_dict(student)

        # Snapshot for undo manager (field-wise dicts)
        old_data = {
            "first_name": student.first_name,
            "last_name": student.last_name,
            "dob": student.dob,
            "grade_level": student.grade_level,
            "status": student.status,
            "contact_email": student.contact_email,
            "guardian_name": student.guardian_name,
            "guardian_phone": student.guardian_phone,
            "guardian_email": student.guardian_email,
            "emergency_contact_name": student.emergency_contact_name,
            "emergency_contact_phone": student.emergency_contact_phone,
            "notes": student.notes,
        }

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
            guardian_email,
            emergency_name,
            emergency_phone,
            notes,
        ) = data

        # Apply new values
        student.first_name = first_name
        student.last_name = last_name
        student.dob = dob
        student.grade_level = grade_level
        student.status = status
        student.contact_email = email
        student.guardian_name = guardian_name
        student.guardian_phone = guardian_phone
        student.guardian_email = guardian_email
        student.emergency_contact_name = emergency_name
        student.emergency_contact_phone = emergency_phone
        student.notes = notes

        # Snapshot AFTER edit for both undo and audit
        new_data = {
            "first_name": student.first_name,
            "last_name": student.last_name,
            "dob": student.dob,
            "grade_level": student.grade_level,
            "status": student.status,
            "contact_email": student.contact_email,
            "guardian_name": student.guardian_name,
            "guardian_phone": student.guardian_phone,
            "guardian_email": student.guardian_email,
            "emergency_contact_name": student.emergency_contact_name,
            "emergency_contact_phone": student.emergency_contact_phone,
            "notes": student.notes,
        }

        after_snapshot = student_to_dict(student)

        # Audit log for the edit
        add_audit_log(
            self.session,
            actor="System",
            action="update",
            entity="Student",
            entity_id=student.id,
            before=before_snapshot,
            after=after_snapshot,
        )

        self.session.commit()
        self.load_students()

        # Register undo/redo
        if self.undo_manager is not None:
            sid = student.id

            def undo_edit():
                obj = self.session.get(Student, sid)
                if obj is None:
                    return
                before = student_to_dict(obj)
                obj.first_name = old_data["first_name"]
                obj.last_name = old_data["last_name"]
                obj.dob = old_data["dob"]
                obj.grade_level = old_data["grade_level"]
                obj.status = old_data["status"]
                obj.contact_email = old_data["contact_email"]
                obj.guardian_name = old_data["guardian_name"]
                obj.guardian_phone = old_data["guardian_phone"]
                obj.guardian_email = old_data["guardian_email"]
                obj.emergency_contact_name = old_data["emergency_contact_name"]
                obj.emergency_contact_phone = old_data["emergency_contact_phone"]
                obj.notes = old_data["notes"]
                after = student_to_dict(obj)
                add_audit_log(
                    self.session,
                    actor="System",
                    action="update",
                    entity="Student",
                    entity_id=obj.id,
                    before=before,
                    after=after,
                )
                self.session.commit()
                self.load_students()

            def redo_edit():
                obj = self.session.get(Student, sid)
                if obj is None:
                    return
                before = student_to_dict(obj)
                obj.first_name = new_data["first_name"]
                obj.last_name = new_data["last_name"]
                obj.dob = new_data["dob"]
                obj.grade_level = new_data["grade_level"]
                obj.status = new_data["status"]
                obj.contact_email = new_data["contact_email"]
                obj.guardian_name = new_data["guardian_name"]
                obj.guardian_phone = new_data["guardian_phone"]
                obj.guardian_email = new_data["guardian_email"]
                obj.emergency_contact_name = new_data["emergency_contact_name"]
                obj.emergency_contact_phone = new_data["emergency_contact_phone"]
                obj.notes = new_data["notes"]
                after = student_to_dict(obj)
                add_audit_log(
                    self.session,
                    actor="System",
                    action="update",
                    entity="Student",
                    entity_id=obj.id,
                    before=before,
                    after=after,
                )
                self.session.commit()
                self.load_students()

            self.undo_manager.push(
                undo_edit,
                redo_edit,
                f"Edit student {sid}",
            )

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

            if idx >= grad_idx:
                return grade_level, True

            new_idx = idx + 1
            new_idx = min(new_idx, len(canonical_scale) - 1)
            new_grade = canonical_scale[new_idx]
            if new_idx > grad_idx:
                return grade_level, True

            return new_grade, False

        # Fallback: numeric heuristic
        s = grade_level.strip().lower()

        if s in ("k", "kindergarten"):
            return "1st", False

        m = re.match(r"(\d+)", s)
        if not m:
            return None, False

        n = int(m.group(1))

        grad_num = 12
        m_grad = re.match(r"(\d+)", grad_name.lower())
        if m_grad:
            grad_num = int(m_grad.group(1))

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
            before = student_to_dict(student)

            new_grade, became_graduate = self._promote_grade_level(student.grade_level)

            if new_grade is None and not became_graduate:
                skipped_count += 1
                continue

            if became_graduate:
                student.status = "Graduated"
                graduated_count += 1

            if new_grade is not None and not became_graduate:
                student.grade_level = new_grade
                promoted_count += 1

            after = student_to_dict(student)
            if before != after:
                add_audit_log(
                    self.session,
                    actor="System",
                    action="update",
                    entity="Student",
                    entity_id=student.id,
                    before=before,
                    after=after,
                )

        self.session.commit()

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


# ----------------------------------------------------------------------
# AddStudentDialog (unchanged API; now used with audit logging above)
# ----------------------------------------------------------------------
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

        #Student email
        self.email_edit = QLineEdit()

        # Guardian name and phone
        self.guardian_name_edit = QLineEdit()
        self.guardian_phone_edit = QLineEdit()
        self.guardian_email_edit = QLineEdit()

        # Emergency contact
        self.emergency_name_edit = QLineEdit()
        self.emergency_phone_edit = QLineEdit()
        
        # Status combo box
        self.status_combo = QComboBox()
        self.status_combo.addItems(["Active", "Inactive", "Graduated"])

        # Notes
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Notes about this student (optional)…")
        self.notes_edit.setFixedHeight(80)

        #Form
        form.addRow("First Name:", self.first_name_edit)
        form.addRow("Last Name:", self.last_name_edit)
        form.addRow("Date of Birth:", self.dob_edit)
        form.addRow("Grade Level:", self.grade_combo)
        form.addRow("Email:", self.email_edit)
        form.addRow("Guardian Name:", self.guardian_name_edit)
        form.addRow("Guardian Phone:", self.guardian_phone_edit)
        form.addRow("Guardian Email:", self.guardian_email_edit)
        form.addRow("Emergency Contact Name:", self.emergency_name_edit)
        form.addRow("Emergency Contact Phone:", self.emergency_phone_edit)
        form.addRow("Status:", self.status_combo)
        form.addRow("Notes:", self.notes_edit)

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
                self.dob_edit.setDate(
                    QDate(
                        self._student.dob.year,
                        self._student.dob.month,
                        self._student.dob.day,
                    )
                )
            else:
                self.dob_edit.setDate(QDate.currentDate())

            # Grade
            existing_grade = self._student.grade_level or ""
            if existing_grade:
                idx = self.grade_combo.findText(existing_grade)
                if idx < 0:
                    self.grade_combo.addItem(existing_grade)
                    idx = self.grade_combo.count() - 1
                self.grade_combo.setCurrentIndex(idx)

            # Status
            status = self._student.status or "Active"
            idx = self.status_combo.findText(status)
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)

            # Contacts
            self.email_edit.setText(self._student.contact_email or "")
            self.guardian_name_edit.setText(self._student.guardian_name or "")
            self.guardian_phone_edit.setText(self._student.guardian_phone or "")
            self.guardian_email_edit.setText(self._student.guardian_email or "")
            self.emergency_name_edit.setText(self._student.emergency_contact_name or "")
            self.emergency_phone_edit.setText(self._student.emergency_contact_phone or "")

            # Notes
            self.notes_edit.setPlainText(self._student.notes or "")
        else:
            # Adding new student → default DOB to today
            self.dob_edit.setDate(QDate.currentDate())

    def get_data(self):
        """
        Return the data as a tuple:
        (first_name, last_name, dob (date), grade_level, status, email,
         guardian_name, guardian_phone, guardian_email,
         emergency_name, emergency_phone, notes)
        If validation fails, return None.
        """
        first_name = self.first_name_edit.text().strip()
        last_name = self.last_name_edit.text().strip()
        grade_level = self.grade_combo.currentText().strip()
        status = self.status_combo.currentText()
        email = self.email_edit.text().strip()
        guardian_name = self.guardian_name_edit.text().strip()
        guardian_phone = self.guardian_phone_edit.text().strip()
        guardian_email = self.guardian_email_edit.text().strip()
        emergency_name = self.emergency_name_edit.text().strip()
        emergency_phone = self.emergency_phone_edit.text().strip()
        notes = self.notes_edit.toPlainText().strip()

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
            guardian_email,
            emergency_name,
            emergency_phone,
            notes,
        )


# ----------------------------------------------------------------------
# StudentProfileDialog (now logs notes/photo updates)
# ----------------------------------------------------------------------
class StudentProfileDialog(QDialog):
    """
    Detailed student profile:
    - Photo (upload + display)
    - Basic info (name, grade, status, DOB, email)
    - Guardian info
    - Editable notes
    - Enrollment history (filterable by term)
    - Attendance history (range presets, including from first class to today)
    """

    def __init__(self, session, student: Student, parent_view: StudentsView, parent=None):
        super().__init__(parent)
        self.session = session
        self.student = student
        self.parent_view = parent_view

        self.setWindowTitle(
            f"Student Profile - {student.first_name} {student.last_name}"
        )

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # Make the profile wider so three panes are comfortable
        self.resize(1200, 650)

        self._build_ui()
        self._load_enrollments()
        self._init_attendance_range()
        self._reload_attendance_table()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------
    def _build_ui(self):
        """
        Build a 3-pane layout:

        Left pane:
          - Photo
          - Name / grade / status / DOB / email
          - Guardian + emergency contact
          - Notes (editable)

        Middle pane:
          - Enrollment history + term filter

        Right pane:
          - Attendance history + range selector
        """
        # ---------- Top-level: 3 columns ----------
        three_pane_layout = QHBoxLayout()

        # ==========================================
        # LEFT PANE: photo + basic info + contacts + notes
        # ==========================================
        left_pane = QVBoxLayout()

        # --- Photo + basic info side-by-side (small row inside left pane) ---
        top_info_layout = QHBoxLayout()

        # Photo
        self.photo_label = QLabel()
        self.photo_label.setFixedSize(120, 160)  # 3:4 headshot rectangle
        self.photo_label.setAlignment(Qt.AlignCenter)
        self.photo_label.setStyleSheet(
            "border: 1px solid #ccc; background-color: #f5f5f5;"
        )
        top_info_layout.addWidget(self.photo_label)

        # Basic info
        info_layout = QVBoxLayout()
        self.name_label = QLabel()
        self.name_label.setTextFormat(Qt.RichText)
        info_layout.addWidget(self.name_label)

        self.grade_status_label = QLabel()
        self.grade_status_label.setTextFormat(Qt.RichText)
        info_layout.addWidget(self.grade_status_label)

        self.contact_label = QLabel()
        self.contact_label.setTextFormat(Qt.RichText)
        info_layout.addWidget(self.contact_label)

        info_layout.addStretch()
        top_info_layout.addLayout(info_layout)

        left_pane.addLayout(top_info_layout)

        # --- Guardian & Emergency Contact group ---
        guardian_group = QGroupBox("Guardian & Emergency Contact")
        guardian_layout = QVBoxLayout()
        self.guardian_label = QLabel()
        self.guardian_label.setTextFormat(Qt.RichText)
        self.guardian_label.setWordWrap(True)
        guardian_layout.addWidget(self.guardian_label)
        guardian_group.setLayout(guardian_layout)
        left_pane.addWidget(guardian_group)

        # --- Notes group (still editable) ---
        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout()
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Notes about this student…")
        notes_layout.addWidget(self.notes_edit)

        notes_button_layout = QHBoxLayout()
        self.save_notes_button = QPushButton("Save Notes")
        notes_button_layout.addWidget(self.save_notes_button)
        notes_button_layout.addStretch()
        notes_layout.addLayout(notes_button_layout)

        notes_group.setLayout(notes_layout)
        left_pane.addWidget(notes_group)

        left_pane.addStretch()

        # ==========================================
        # MIDDLE PANE: enrollment history
        # ==========================================
        middle_pane = QVBoxLayout()

        enroll_group = QGroupBox("Enrollment History")
        enroll_layout = QVBoxLayout()

        # Term filter row
        term_filter_row = QHBoxLayout()
        term_filter_row.addWidget(QLabel("Term:"))
        self.enrollment_term_filter = QComboBox()
        self.enrollment_term_filter.addItem("All terms")
        term_filter_row.addWidget(self.enrollment_term_filter)
        term_filter_row.addStretch()
        enroll_layout.addLayout(term_filter_row)

        # Enrollment table
        self.enrollment_table = QTableWidget()
        self.enrollment_table.setColumnCount(5)
        self.enrollment_table.setHorizontalHeaderLabels(
            ["Class", "Subject", "Term", "Start Date", "End Date"]
        )
        self.enrollment_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        enroll_layout.addWidget(self.enrollment_table)

        enroll_group.setLayout(enroll_layout)
        # Let the enrollment group take all vertical space in middle pane
        middle_pane.addWidget(enroll_group, 1)
        # (no extra stretch needed)

        # ==========================================
        # RIGHT PANE: attendance history
        # ==========================================
        right_pane = QVBoxLayout()

        attendance_group = QGroupBox("Attendance History")
        attendance_layout = QVBoxLayout()

        # Range selector
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("Range:"))
        self.attendance_range_combo = QComboBox()
        range_row.addWidget(self.attendance_range_combo)
        range_row.addStretch()
        attendance_layout.addLayout(range_row)

        # Attendance table
        self.attendance_table = QTableWidget()
        self.attendance_table.setColumnCount(4)
        self.attendance_table.setHorizontalHeaderLabels(
            ["Date", "Class", "Term", "Status"]
        )
        self.attendance_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        attendance_layout.addWidget(self.attendance_table)

        attendance_group.setLayout(attendance_layout)
        # Let the attendance group take all vertical space in right pane
        right_pane.addWidget(attendance_group, 1)
        # (no extra stretch)

        # ==========================================
        # Assemble 3 panes
        # ==========================================
        three_pane_layout.addLayout(left_pane, 2)    # left a bit wider
        three_pane_layout.addLayout(middle_pane, 2)
        three_pane_layout.addLayout(right_pane, 2)

        self.main_layout.addLayout(three_pane_layout)

        # ---------- Bottom buttons: Change Photo / Edit / Close ----------
        bottom_buttons = QDialogButtonBox()
        self.change_photo_button = QPushButton("Change Photo…")
        bottom_buttons.addButton(self.change_photo_button, QDialogButtonBox.ActionRole)

        self.edit_button = QPushButton("Edit Student…")
        bottom_buttons.addButton(self.edit_button, QDialogButtonBox.ActionRole)

        close_button = bottom_buttons.addButton(QDialogButtonBox.Close)
        close_button.clicked.connect(self.reject)

        self.main_layout.addWidget(bottom_buttons)

        # Signals
        self.save_notes_button.clicked.connect(self.save_notes)
        self.change_photo_button.clicked.connect(self.change_photo)
        self.edit_button.clicked.connect(self.edit_student)
        self.enrollment_term_filter.currentTextChanged.connect(
            self._update_enrollment_table_from_filter
        )
        self.attendance_range_combo.currentTextChanged.connect(
            lambda _: self._reload_attendance_table()
        )

        # Fill initial data
        self._refresh_header_and_notes()
        self._load_photo()

    # ------------------------------------------------------------------
    # Header / notes / guardian display
    # ------------------------------------------------------------------
    def _refresh_header_and_notes(self):
        s = self.student
        full_name = f"{s.first_name} {s.last_name}"
        self.name_label.setText(f"<h2>{full_name}</h2>")

        dob_text = s.dob.isoformat() if s.dob else "Unknown"
        self.grade_status_label.setText(
            f"<b>Grade:</b> {s.grade_level or ''} &nbsp;&nbsp; "
            f"<b>Status:</b> {s.status or ''} &nbsp;&nbsp; "
            f"<b>DOB:</b> {dob_text}"
        )

        # Student contact
        self.contact_label.setText(
            f"<b>Email:</b> {s.contact_email or ''}"
        )

        # Guardian + emergency contact block
        self.guardian_label.setText(
            f"<b>Guardian:</b> {s.guardian_name or ''}<br>"
            f"<b>Guardian Phone:</b> {s.guardian_phone or ''}<br>"
            f"<b>Guardian Email:</b> {s.guardian_email or ''}<br>"
            f"<b>Emergency Contact:</b> {s.emergency_contact_name or ''}<br>"
            f"<b>Emergency Phone:</b> {s.emergency_contact_phone or ''}"
        )
        
        # Notes
        self.notes_edit.setPlainText(s.notes or "")

    # ------------------------------------------------------------------
    # Photo loading / changing
    # ------------------------------------------------------------------
    def _load_photo(self):
        self.photo_label.setPixmap(QPixmap())
        self.photo_label.setText("No Photo")

        path_str = self.student.photo_path
        if not path_str:
            return

        path = Path(path_str)
        if not path.is_file():
            return

        pix = QPixmap(str(path))
        if pix.isNull():
            return

        scaled = pix.scaled(
            self.photo_label.width(),
            self.photo_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.photo_label.setPixmap(scaled)
        self.photo_label.setText("")

    def change_photo(self):
        file_path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Student Photo",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*.*)",
        )
        if not file_path_str:
            return

        src_path = Path(file_path_str)
        if not src_path.is_file():
            QMessageBox.warning(
                self,
                "Change Photo",
                "The selected file does not exist.",
            )
            return

        student = self.session.get(Student, self.student.id)
        if student is None:
            QMessageBox.warning(
                self,
                "Change Photo",
                "Student no longer exists in the database.",
            )
            return

        photos_dir = Path("photos") / "students"
        try:
            photos_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Change Photo",
                f"Could not create photo directory:\n{photos_dir}\n\n{exc}",
            )
            return

        suffix = src_path.suffix.lower() or ".png"
        dest_path = photos_dir / f"student_{student.id}{suffix}"

        try:
            shutil.copy2(src_path, dest_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Change Photo",
                f"Failed to copy photo:\n{exc}",
            )
            return

        before = student_to_dict(student)
        student.photo_path = str(dest_path)
        after = student_to_dict(student)

        add_audit_log(
            self.session,
            actor="System",
            action="update",
            entity="Student",
            entity_id=student.id,
            before=before,
            after=after,
        )

        self.session.commit()

        self.student = student
        self._load_photo()
        QMessageBox.information(
            self,
            "Change Photo",
            "Photo updated successfully.",
        )

    # ------------------------------------------------------------------
    # Notes saving
    # ------------------------------------------------------------------
    def save_notes(self):
        text = self.notes_edit.toPlainText().strip()
        student = self.session.get(Student, self.student.id)
        if student is None:
            QMessageBox.warning(
                self,
                "Save Notes",
                "Student no longer exists in the database.",
            )
            return

        before = student_to_dict(student)
        student.notes = text
        after = student_to_dict(student)

        add_audit_log(
            self.session,
            actor="System",
            action="update",
            entity="Student",
            entity_id=student.id,
            before=before,
            after=after,
        )

        self.session.commit()
        self.student = student
        QMessageBox.information(
            self,
            "Save Notes",
            "Notes saved.",
        )

    # ------------------------------------------------------------------
    # Enrollment history
    # ------------------------------------------------------------------
    def _load_enrollments(self):
        """
        Load all enrollment rows and populate the term filter + table.
        """
        self._enrollment_rows = []

        records = (
            self.session.query(Enrollment, Class)
            .join(Class, Enrollment.class_id == Class.id)
            .filter(Enrollment.student_id == self.student.id)
            .all()
        )

        terms = set()
        for e, c in records:
            term = c.term or ""
            if term:
                terms.add(term)
            self._enrollment_rows.append(
                {
                    "class_name": c.name or "",
                    "subject": c.subject or "",
                    "term": term,
                    "start_date": e.start_date,
                    "end_date": e.end_date,
                }
            )

        # Build term filter
        self.enrollment_term_filter.blockSignals(True)
        self.enrollment_term_filter.clear()
        self.enrollment_term_filter.addItem("All terms")
        for term in sorted(t for t in terms if t):
            self.enrollment_term_filter.addItem(term)
        self.enrollment_term_filter.blockSignals(False)

        self._update_enrollment_table_from_filter()

    def _update_enrollment_table_from_filter(self):
        selected_term = self.enrollment_term_filter.currentText()
        rows = []
        for r in self._enrollment_rows:
            if selected_term == "All terms" or r["term"] == selected_term:
                rows.append(r)

        self.enrollment_table.setRowCount(len(rows))
        for row, r in enumerate(rows):
            self.enrollment_table.setItem(row, 0, QTableWidgetItem(r["class_name"]))
            self.enrollment_table.setItem(row, 1, QTableWidgetItem(r["subject"]))
            self.enrollment_table.setItem(row, 2, QTableWidgetItem(r["term"]))
            start_text = r["start_date"].isoformat() if r["start_date"] else ""
            end_text = r["end_date"].isoformat() if r["end_date"] else ""
            self.enrollment_table.setItem(row, 3, QTableWidgetItem(start_text))
            self.enrollment_table.setItem(row, 4, QTableWidgetItem(end_text))

        self.enrollment_table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Attendance history
    # ------------------------------------------------------------------
    def _init_attendance_range(self):
        """
        Determine earliest relevant date (first enrollment start_date or first attendance)
        and initialize the range presets.
        """
        # Earliest enrollment start_date
        enroll_dates = [
            e.start_date
            for e in self.session.query(Enrollment)
            .filter(
                Enrollment.student_id == self.student.id,
                Enrollment.start_date.isnot(None),
            )
            .all()
            if e.start_date is not None
        ]

        earliest_enroll = min(enroll_dates) if enroll_dates else None

        # Earliest attendance
        first_att = (
            self.session.query(Attendance)
            .filter(Attendance.student_id == self.student.id)
            .order_by(Attendance.date)
            .first()
        )
        earliest_att = first_att.date if first_att is not None else None

        candidates = [d for d in [earliest_enroll, earliest_att] if d is not None]
        self.first_relevant_date = min(candidates) if candidates else None
        self.today = date.today()

        self.attendance_range_combo.blockSignals(True)
        self.attendance_range_combo.clear()
        self.attendance_range_combo.addItem("Last 30 days")
        self.attendance_range_combo.addItem("Last 60 days")
        if self.first_relevant_date is not None:
            self.attendance_range_combo.addItem("From first enrollment to today")
        self.attendance_range_combo.blockSignals(False)

        # Default: Last 30 days
        self.attendance_range_combo.setCurrentIndex(0)

    def _compute_attendance_range(self):
        choice = self.attendance_range_combo.currentText()
        end = self.today

        if choice == "Last 60 days":
            start = end - timedelta(days=59)
        elif choice == "From first enrollment to today" and self.first_relevant_date:
            start = self.first_relevant_date
        else:  # "Last 30 days" or fallback
            start = end - timedelta(days=29)

        # Don't go earlier than first_relevant_date if we have one
        if self.first_relevant_date is not None and start < self.first_relevant_date:
            start = self.first_relevant_date

        return start, end

    def _reload_attendance_table(self):
        start, end = self._compute_attendance_range()

        records = (
            self.session.query(Attendance, Class)
            .join(Class, Attendance.class_id == Class.id)
            .filter(
                Attendance.student_id == self.student.id,
                Attendance.date >= start,
                Attendance.date <= end,
            )
            .order_by(Attendance.date.desc())
            .all()
        )

        self.attendance_table.setRowCount(len(records))
        for row, (a, c) in enumerate(records):
            date_text = a.date.isoformat() if a.date else ""
            class_name = c.name or ""
            term = c.term or ""
            status = a.status or ""

            self.attendance_table.setItem(row, 0, QTableWidgetItem(date_text))
            self.attendance_table.setItem(row, 1, QTableWidgetItem(class_name))
            self.attendance_table.setItem(row, 2, QTableWidgetItem(term))
            self.attendance_table.setItem(row, 3, QTableWidgetItem(status))

        self.attendance_table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Edit student from profile
    # ------------------------------------------------------------------
    def edit_student(self):
        self.parent_view.edit_selected_student_by_id(self.student.id)
        # Reload the student from DB to reflect updates
        student = self.session.get(Student, self.student.id)
        if student is None:
            self.reject()
            return
        self.student = student
        self._refresh_header_and_notes()
        self._load_photo()
        self._load_enrollments()
        self._reload_attendance_table()
