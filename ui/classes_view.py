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
    QFileDialog,
    QInputDialog,
)
from PySide6.QtCore import QDate
from datetime import date
from data.models import (
    Class,
    Student,
    Enrollment,
    Attendance,
    Teacher,
    TeacherClassLink,
    add_audit_log,
)
from sqlalchemy import or_
from ui.undo_manager import UndoManager

import csv


# ----------------------------------------------------------------------
# Helper serializers for audit logs
# ----------------------------------------------------------------------
def class_to_dict(clazz: Class | None):
    if clazz is None:
        return None
    return {
        "id": clazz.id,
        "name": clazz.name,
        "subject": clazz.subject,
        "term": clazz.term,
        "room": clazz.room,
    }


def enrollment_to_dict(e: Enrollment | None):
    if e is None:
        return None
    return {
        "id": e.id,
        "student_id": e.student_id,
        "class_id": e.class_id,
        "start_date": e.start_date.isoformat() if e.start_date else None,
        "end_date": e.end_date.isoformat() if e.end_date else None,
    }


def teacher_class_link_to_dict(link: TeacherClassLink | None):
    if link is None:
        return None
    return {
        "id": link.id,
        "teacher_id": link.teacher_id,
        "class_id": link.class_id,
    }


class ClassesView(QWidget):
    def __init__(self, session, undo_manager: UndoManager | None = None):
        super().__init__()
        self.session = session
        self.undo_manager = undo_manager

        layout = QVBoxLayout()

        # --- Top buttons ---
        btn_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Class")
        self.delete_button = QPushButton("Delete Selected")
        self.manage_enrollments_button = QPushButton("Manage Enrollments")
        self.manage_teachers_button = QPushButton("Manage Teachers")

        # New quick-action + roster buttons
        self.view_roster_button = QPushButton("View Roster")
        self.view_attendance_button = QPushButton("View Class Attendance")
        self.export_roster_button = QPushButton("Export Roster CSV")
        self.import_roster_button = QPushButton("Import Roster from Class")

        btn_layout.addWidget(self.add_button)
        btn_layout.addWidget(self.delete_button)
        btn_layout.addWidget(self.manage_enrollments_button)
        btn_layout.addWidget(self.manage_teachers_button)
        btn_layout.addWidget(self.view_roster_button)
        btn_layout.addWidget(self.view_attendance_button)
        btn_layout.addWidget(self.export_roster_button)
        btn_layout.addWidget(self.import_roster_button)

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
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Name",
                "Subject",
                "Teacher(s)",
                "Term",
                "Room",
                "Enrolled",
                "Today’s Attendance",
            ]
        )
        layout.addWidget(self.table)

        self.setLayout(layout)

        # Connect buttons
        self.add_button.clicked.connect(self.add_class)
        self.delete_button.clicked.connect(self.delete_class)
        self.manage_enrollments_button.clicked.connect(self.manage_enrollments)
        self.manage_teachers_button.clicked.connect(self.manage_teachers)

        self.view_roster_button.clicked.connect(self.view_roster)
        self.view_attendance_button.clicked.connect(self.view_class_attendance)
        self.export_roster_button.clicked.connect(self.export_roster_csv)
        self.import_roster_button.clicked.connect(self.import_roster_from_class)

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

        # Search filter (class name, subject, term, teacher names)
        if search_text:
            pattern = f"%{search_text}%"
            query = (
                query.outerjoin(TeacherClassLink, TeacherClassLink.class_id == Class.id)
                .outerjoin(Teacher, TeacherClassLink.teacher_id == Teacher.id)
                .filter(
                    or_(
                        Class.name.ilike(pattern),
                        Class.subject.ilike(pattern),
                        Class.term.ilike(pattern),
                        Teacher.first_name.ilike(pattern),
                        Teacher.last_name.ilike(pattern),
                    )
                )
                .distinct()
            )

        classes = query.order_by(Class.term, Class.id).all()

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
        today = date.today()

        for row, c in enumerate(classes):
            # Basic class info
            self.table.setItem(row, 0, QTableWidgetItem(str(c.id)))
            self.table.setItem(row, 1, QTableWidgetItem(c.name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(c.subject or ""))

            # Build teacher display from linked teachers only
            teacher_names = []
            for link in c.teacher_links:
                if link.teacher:
                    full_name = f"{link.teacher.first_name or ''} {link.teacher.last_name or ''}".strip()
                    teacher_names.append(full_name)
            teacher_display = ", ".join(teacher_names) if teacher_names else ""
            self.table.setItem(row, 3, QTableWidgetItem(teacher_display))

            self.table.setItem(row, 4, QTableWidgetItem(c.term or ""))
            self.table.setItem(row, 5, QTableWidgetItem(c.room or ""))

            # --- Enrollment count ---
            enrolled_count = (
                self.session.query(Enrollment)
                .filter(Enrollment.class_id == c.id)
                .count()
            )
            self.table.setItem(row, 6, QTableWidgetItem(str(enrolled_count)))

            # --- Today's attendance summary ---
            records = (
                self.session.query(Attendance)
                .filter(
                    Attendance.class_id == c.id,
                    Attendance.date == today,
                )
                .all()
            )

            if not records:
                summary_text = "-"
            else:
                status_counts = {}
                for a in records:
                    status = a.status or ""
                    status_counts[status] = status_counts.get(status, 0) + 1

                parts = [f"{status}: {count}" for status, count in status_counts.items()]
                summary_text = " | ".join(parts)

            self.table.setItem(row, 7, QTableWidgetItem(summary_text))

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
                return

            name, subject, term, room = data

            c = Class(
                name=name,
                subject=subject,
                term=term,
                room=room,
            )

            # Save to DB
            self.session.add(c)
            # Get ID and snapshot
            self.session.flush()
            after = class_to_dict(c)
            add_audit_log(
                self.session,
                actor="System",
                action="create",
                entity="Class",
                entity_id=c.id,
                before=None,
                after=after,
            )

            self.session.commit()

            # Reload table
            self.load_classes()

    # ------------------------------------------------------------------
    # Delete selected class (UNDOABLE)
    # ------------------------------------------------------------------
    def delete_class(self):
        """Delete the currently selected class from the table and DB (undoable)."""
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

        clazz = self.session.get(Class, class_id)
        if clazz is None:
            QMessageBox.warning(self, "Delete Class", "Class not found in database.")
            return

        # --- Snapshot data BEFORE deleting (for undo + audit) ---
        snapshot = {
            "id": clazz.id,
            "name": clazz.name,
            "subject": clazz.subject,
            "term": clazz.term,
            "room": clazz.room,
        }

        def redo_delete():
            """Do the delete (used for redo and initial action) with audit log."""
            obj = self.session.get(Class, snapshot["id"])
            if obj is None:
                return
            before = class_to_dict(obj)
            # delete attendance rows for this class
            self.session.query(Attendance).filter(
                Attendance.class_id == snapshot["id"]
            ).delete(synchronize_session=False)
            # audit log for class delete
            add_audit_log(
                self.session,
                actor="System",
                action="delete",
                entity="Class",
                entity_id=obj.id,
                before=before,
                after=None,
            )
            # delete the class itself
            self.session.delete(obj)
            self.session.commit()
            self.load_classes()

        def undo_delete():
            """Recreate the class row with the old values (with audit log)."""
            existing = self.session.get(Class, snapshot["id"])
            if existing is None:
                restored = Class(
                    id=snapshot["id"],
                    name=snapshot["name"],
                    subject=snapshot["subject"],
                    term=snapshot["term"],
                    room=snapshot["room"],
                )
                self.session.add(restored)
                self.session.flush()
                after = class_to_dict(restored)
                add_audit_log(
                    self.session,
                    actor="System",
                    action="create",
                    entity="Class",
                    entity_id=restored.id,
                    before=None,
                    after=after,
                )
                self.session.commit()
            self.load_classes()

        # --- Perform the delete now ---
        redo_delete()

        # --- Register with undo manager ---
        if self.undo_manager is not None:
            self.undo_manager.push(
                undo_delete,
                redo_delete,
                f"Delete class {class_id}",
            )

    # ------------------------------------------------------------------
    # Edit selected class (UNDOABLE)
    # ------------------------------------------------------------------
    def edit_selected_class(self):
        """Open an edit dialog for the currently selected class (undoable)."""
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

        # Snapshot BEFORE changes
        old_data = {
            "name": clazz.name,
            "subject": clazz.subject,
            "term": clazz.term,
            "room": clazz.room,
        }
        before_snapshot = class_to_dict(clazz)

        dialog = AddClassDialog(self, clazz=clazz)
        result = dialog.exec()

        if result != QDialog.Accepted:
            return

        data = dialog.get_data()
        if data is None:
            return

        name, subject, term, room = data

        # Apply changes
        clazz.name = name
        clazz.subject = subject
        clazz.term = term
        clazz.room = room

        # Snapshot AFTER changes (for redo + audit)
        new_data = {
            "name": clazz.name,
            "subject": clazz.subject,
            "term": clazz.term,
            "room": clazz.room,
        }
        after_snapshot = class_to_dict(clazz)

        # Audit log for this edit
        add_audit_log(
            self.session,
            actor="System",
            action="update",
            entity="Class",
            entity_id=clazz.id,
            before=before_snapshot,
            after=after_snapshot,
        )

        self.session.commit()
        self.load_classes()

        # Register undo/redo
        if self.undo_manager is not None:
            def undo_edit():
                obj = self.session.get(Class, class_id)
                if obj is None:
                    return
                before = class_to_dict(obj)
                obj.name = old_data["name"]
                obj.subject = old_data["subject"]
                obj.term = old_data["term"]
                obj.room = old_data["room"]
                after = class_to_dict(obj)
                add_audit_log(
                    self.session,
                    actor="System",
                    action="update",
                    entity="Class",
                    entity_id=class_id,
                    before=before,
                    after=after,
                )
                self.session.commit()
                self.load_classes()

            def redo_edit():
                obj = self.session.get(Class, class_id)
                if obj is None:
                    return
                before = class_to_dict(obj)
                obj.name = new_data["name"]
                obj.subject = new_data["subject"]
                obj.term = new_data["term"]
                obj.room = new_data["room"]
                after = class_to_dict(obj)
                add_audit_log(
                    self.session,
                    actor="System",
                    action="update",
                    entity="Class",
                    entity_id=class_id,
                    before=before,
                    after=after,
                )
                self.session.commit()
                self.load_classes()

            self.undo_manager.push(
                undo_edit,
                redo_edit,
                f"Edit class {class_id}",
            )

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

        dialog = ManageEnrollmentsDialog(
            self.session,
            clazz,
            self,
            undo_manager=self.undo_manager,
        )
        dialog.exec()
        # Enrollments changed → update enrolled count
        self.load_classes()

    # ------------------------------------------------------------------
    # Manage teachers for selected class
    # ------------------------------------------------------------------
    def manage_teachers(self):
        """Open a dialog to manage which teachers are linked to this class."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Manage Teachers", "Please select a class first.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Manage Teachers", "Could not determine class ID.")
            return

        class_id = int(id_item.text())

        clazz = self.session.get(Class, class_id)
        if clazz is None:
            QMessageBox.warning(self, "Manage Teachers", "Class not found in database.")
            return

        dialog = ManageClassTeachersDialog(self.session, clazz, self)
        dialog.exec()
        # After changes, refresh class list to update teacher column
        self.load_classes()

    # ------------------------------------------------------------------
    # Export roster of selected class to CSV
    # ------------------------------------------------------------------
    def export_roster_csv(self):
        """Export the roster (enrolled students) for the selected class to CSV."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Export Roster", "Please select a class first.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Export Roster", "Could not determine class ID.")
            return

        class_id = int(id_item.text())
        clazz = self.session.get(Class, class_id)
        if clazz is None:
            QMessageBox.warning(self, "Export Roster", "Class not found in database.")
            return

        # Choose file path
        default_name = f"class_{class_id}_roster.csv"
        file_path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export Class Roster",
            default_name,
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if not file_path_str:
            return  # user cancelled

        # Collect enrollments + student info
        enrollments = (
            self.session.query(Enrollment)
            .filter(Enrollment.class_id == class_id)
            .all()
        )

        with open(file_path_str, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "student_id",
                    "first_name",
                    "last_name",
                    "dob",
                    "grade_level",
                    "status",
                    "guardian_name",
                    "guardian_phone",
                    "guardian_email",
                    "emergency_contact_name",
                    "emergency_contact_phone",
                    "contact_email",
                    "enrollment_start_date",
                    "enrollment_end_date",
                ]
            )

            for e in enrollments:
                s = e.student
                writer.writerow(
                    [
                        s.id,
                        s.first_name or "",
                        s.last_name or "",
                        s.dob.isoformat() if s.dob else "",
                        s.grade_level or "",
                        s.status or "",
                        s.guardian_name or "",
                        s.guardian_phone or "",
                        getattr(s, "guardian_email", "") or "",
                        getattr(s, "emergency_contact_name", "") or "",
                        getattr(s, "emergency_contact_phone", "") or "",
                        s.contact_email or "",
                        e.start_date.isoformat() if e.start_date else "",
                        e.end_date.isoformat() if e.end_date else "",
                    ]
                )

        QMessageBox.information(
            self,
            "Export Roster",
            f"Exported {len(enrollments)} enrolled students to:\n{file_path_str}",
        )

    # ------------------------------------------------------------------
    # Import roster from another class
    # ------------------------------------------------------------------
    def import_roster_from_class(self):
        """
        Copy the roster (enrolled students) from one class into the currently
        selected class. Students already enrolled in the target are skipped.
        New enrollments get start_date = today, end_date = None.
        """
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Import Roster", "Please select a target class first.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Import Roster", "Could not determine class ID.")
            return

        target_class_id = int(id_item.text())
        target_class = self.session.get(Class, target_class_id)
        if target_class is None:
            QMessageBox.warning(self, "Import Roster", "Target class not found in database.")
            return

        # Let user choose source class
        all_other_classes = (
            self.session.query(Class)
            .filter(Class.id != target_class_id)
            .order_by(Class.term, Class.name)
            .all()
        )
        if not all_other_classes:
            QMessageBox.information(
                self,
                "Import Roster",
                "There are no other classes to import from.",
            )
            return

        items = [
            f"ID {c.id} – {c.name or 'Unnamed'} ({c.term or ''})"
            for c in all_other_classes
        ]

        choice, ok = QInputDialog.getItem(
            self,
            "Import Roster",
            "Copy enrolled students from:",
            items,
            0,
            False,
        )
        if not ok or not choice:
            return

        # Parse out the source class id from "ID <id> – ..."
        try:
            prefix = "ID "
            start_idx = choice.find(prefix)
            dash_idx = choice.find("–")
            source_id_str = choice[start_idx + len(prefix):dash_idx].strip()
            source_class_id = int(source_id_str)
        except Exception:
            QMessageBox.warning(
                self,
                "Import Roster",
                "Could not parse selected class.",
            )
            return

        source_class = self.session.get(Class, source_class_id)
        if source_class is None:
            QMessageBox.warning(
                self,
                "Import Roster",
                "Source class no longer exists.",
            )
            return

        today = date.today()

        source_enrollments = (
            self.session.query(Enrollment)
            .filter(Enrollment.class_id == source_class_id)
            .all()
        )

        imported = 0
        skipped = 0

        for e in source_enrollments:
            # Skip if already enrolled in target
            existing = (
                self.session.query(Enrollment)
                .filter(
                    Enrollment.student_id == e.student_id,
                    Enrollment.class_id == target_class_id,
                )
                .first()
            )
            if existing:
                skipped += 1
                continue

            new_enrollment = Enrollment(
                student_id=e.student_id,
                class_id=target_class_id,
                start_date=today,
                end_date=None,
            )
            self.session.add(new_enrollment)
            self.session.flush()
            after = enrollment_to_dict(new_enrollment)
            add_audit_log(
                self.session,
                actor="System",
                action="create",
                entity="Enrollment",
                entity_id=new_enrollment.id,
                before=None,
                after=after,
            )
            imported += 1

        self.session.commit()

        # Reload classes so the "Enrolled" count updates
        self.load_classes()

        QMessageBox.information(
            self,
            "Import Roster",
            f"Imported {imported} students from '{source_class.name}' into "
            f"'{target_class.name}'.\nSkipped (already enrolled): {skipped}",
        )

    # ------------------------------------------------------------------
    # Quick action: View roster for selected class
    # ------------------------------------------------------------------
    def view_roster(self):
        """Open a read-only roster dialog for the selected class."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "View Roster", "Please select a class first.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "View Roster", "Could not determine class ID.")
            return

        class_id = int(id_item.text())
        clazz = self.session.get(Class, class_id)
        if clazz is None:
            QMessageBox.warning(self, "View Roster", "Class not found in database.")
            return

        enrollments = (
            self.session.query(Enrollment)
            .filter(Enrollment.class_id == class_id)
            .all()
        )

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Roster - {clazz.name} ({clazz.term or ''})")

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Class: {clazz.name} ({clazz.term or ''})"))

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            ["Student ID", "First Name", "Last Name", "Grade", "Status"]
        )

        table.setRowCount(len(enrollments))
        for i, e in enumerate(enrollments):
            s = e.student
            table.setItem(i, 0, QTableWidgetItem(str(s.id)))
            table.setItem(i, 1, QTableWidgetItem(s.first_name or ""))
            table.setItem(i, 2, QTableWidgetItem(s.last_name or ""))
            table.setItem(i, 3, QTableWidgetItem(s.grade_level or ""))
            table.setItem(i, 4, QTableWidgetItem(s.status or ""))

        table.resizeColumnsToContents()
        layout.addWidget(table)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)
        dialog.resize(600, 400)
        dialog.exec()

    # ------------------------------------------------------------------
    # Quick action: View attendance history for selected class
    # ------------------------------------------------------------------
    def view_class_attendance(self):
        """Open a dialog showing all attendance records for the selected class."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Class Attendance", "Please select a class first.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Class Attendance", "Could not determine class ID.")
            return

        class_id = int(id_item.text())
        clazz = self.session.get(Class, class_id)
        if clazz is None:
            QMessageBox.warning(self, "Class Attendance", "Class not found in database.")
            return

        records = (
            self.session.query(Attendance, Student)
            .join(Student, Attendance.student_id == Student.id)
            .filter(Attendance.class_id == class_id)
            .order_by(Attendance.date.desc())
            .all()
        )

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Attendance History - {clazz.name} ({clazz.term or ''})")

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Class: {clazz.name} ({clazz.term or ''})"))

        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(
            ["Date", "Student ID", "First Name", "Last Name", "Status", "Marked By"]
        )

        table.setRowCount(len(records))
        for i, (a, s) in enumerate(records):
            date_text = a.date.isoformat() if a.date else ""
            table.setItem(i, 0, QTableWidgetItem(date_text))
            table.setItem(i, 1, QTableWidgetItem(str(s.id)))
            table.setItem(i, 2, QTableWidgetItem(s.first_name or ""))
            table.setItem(i, 3, QTableWidgetItem(s.last_name or ""))
            table.setItem(i, 4, QTableWidgetItem(a.status or ""))
            table.setItem(i, 5, QTableWidgetItem(a.marked_by or ""))

        table.resizeColumnsToContents()
        layout.addWidget(table)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)
        dialog.resize(800, 500)
        dialog.exec()


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
        self.term_edit = QLineEdit()
        self.room_edit = QLineEdit()

        form.addRow("Name:", self.name_edit)
        form.addRow("Subject:", self.subject_edit)
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
            self.term_edit.setText(self._clazz.term or "")
            self.room_edit.setText(self._clazz.room or "")

    def get_data(self):
        """
        Return (name, subject, term, room)
        or None if validation fails.
        """
        name = self.name_edit.text().strip()
        subject = self.subject_edit.text().strip()
        term = self.term_edit.text().strip()
        room = self.room_edit.text().strip()

        if not name:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Class name is required.",
            )
            return None

        return name, subject, term, room


class ManageEnrollmentsDialog(QDialog):
    """
    Dialog to assign/remove students from a given class,
    and set enrollment start/end dates.
    """

    def __init__(
        self,
        session,
        clazz: Class,
        parent=None,
        undo_manager: UndoManager | None = None,
    ):
        super().__init__(parent)
        self.session = session
        self.clazz = clazz
        self.undo_manager = undo_manager

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

        # --- Search + list of available students (Active, not enrolled) ---
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search active students:"))

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Name or ID…")
        self.search_edit.textChanged.connect(self.load_available_students)
        search_layout.addWidget(self.search_edit)

        main_layout.addLayout(search_layout)

        self.available_table = QTableWidget()
        self.available_table.setColumnCount(3)
        self.available_table.setHorizontalHeaderLabels(
            ["ID", "First Name", "Last Name"]
        )
        self.available_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.available_table.setSelectionMode(QTableWidget.SingleSelection)
        self.available_table.setEditTriggers(QTableWidget.NoEditTriggers)

        main_layout.addWidget(QLabel("Available students (Active, not enrolled):"))
        main_layout.addWidget(self.available_table)

        enroll_layout = QHBoxLayout()
        self.add_student_button = QPushButton("Enroll Selected")
        self.add_student_button.clicked.connect(self.add_enrollment)
        enroll_layout.addWidget(self.add_student_button)
        enroll_layout.addStretch()
        main_layout.addLayout(enroll_layout)

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
    # Load available students (Active, not enrolled) into the table
    # --------------------------------------------------------------
    def load_available_students(self):
        """
        Populate the 'available students' table with Active students
        who are NOT already enrolled in this class, applying the search filter.
        """
        if not hasattr(self, "available_table"):
            return

        self.available_table.setRowCount(0)

        # Already enrolled in this class
        enrolled_ids = {
            e.student_id
            for e in self.session.query(Enrollment)
            .filter(Enrollment.class_id == self.clazz.id)
            .all()
        }

        # Base query: Active students not in this class
        query = self.session.query(Student).filter(Student.status == "Active")
        if enrolled_ids:
            query = query.filter(~Student.id.in_(enrolled_ids))

        # Optional search filter
        search_text = ""
        if hasattr(self, "search_edit") and self.search_edit is not None:
            search_text = self.search_edit.text().strip()

        if search_text:
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

        # Sort by last name, first name, id
        available_students = (
            query.order_by(Student.last_name, Student.first_name, Student.id).all()
        )

        if not available_students:
            self.add_student_button.setEnabled(False)
            return

        self.add_student_button.setEnabled(True)
        self.available_table.setRowCount(len(available_students))

        for row, s in enumerate(available_students):
            self.available_table.setItem(row, 0, QTableWidgetItem(str(s.id)))
            self.available_table.setItem(row, 1, QTableWidgetItem(s.first_name or ""))
            self.available_table.setItem(row, 2, QTableWidgetItem(s.last_name or ""))

        self.available_table.resizeColumnsToContents()

    # --------------------------------------------------------------
    # Enroll selected student from the available table
    # --------------------------------------------------------------
    def add_enrollment(self):
        """
        Enroll the selected student from the 'available students' table
        into this class.
        """
        if not hasattr(self, "available_table"):
            return

        row = self.available_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Enroll", "Please select a student to enroll."
            )
            return

        id_item = self.available_table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Enroll", "Could not determine student ID.")
            return

        try:
            student_id = int(id_item.text())
        except ValueError:
            QMessageBox.warning(self, "Enroll", "Invalid student ID.")
            return

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

        # Use the current start/end date controls for the new enrollment
        start_qdate = self.start_date_edit.date()
        start_date_val = date(
            start_qdate.year(), start_qdate.month(), start_qdate.day()
        )

        end_date_val = None
        end_qdate = self.end_date_edit.date()
        if end_qdate.isValid():
            end_date_val = date(
                end_qdate.year(), end_qdate.month(), end_qdate.day()
            )

        e = Enrollment(
            student_id=student_id,
            class_id=self.clazz.id,
            start_date=start_date_val,
            end_date=end_date_val,
        )
        self.session.add(e)
        self.session.flush()
        after = enrollment_to_dict(e)
        add_audit_log(
            self.session,
            actor="System",
            action="create",
            entity="Enrollment",
            entity_id=e.id,
            before=None,
            after=after,
        )

        self.session.commit()

        self.load_enrollments()
        self.load_available_students()

    # --------------------------------------------------------------
    # Update start/end dates for the selected enrollment (UNDOABLE)
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

        # Old values (for undo + audit)
        old_start = e.start_date
        old_end = e.end_date
        before_snapshot = enrollment_to_dict(e)

        # Get new dates from the QDateEdits
        s_qdate = self.start_date_edit.date()
        e_qdate = self.end_date_edit.date()

        new_start = date(s_qdate.year(), s_qdate.month(), s_qdate.day())
        new_end = date(e_qdate.year(), e_qdate.month(), e_qdate.day())

        e.start_date = new_start
        e.end_date = new_end

        after_snapshot = enrollment_to_dict(e)
        add_audit_log(
            self.session,
            actor="System",
            action="update",
            entity="Enrollment",
            entity_id=e.id,
            before=before_snapshot,
            after=after_snapshot,
        )

        self.session.commit()
        self.load_enrollments()

        # Register undo/redo in the global UndoManager
        if self.undo_manager is not None:
            enrollment_id = e.id

            def undo_edit_dates():
                obj = self.session.get(Enrollment, enrollment_id)
                if obj is None:
                    return
                before = enrollment_to_dict(obj)
                obj.start_date = old_start
                obj.end_date = old_end
                after = enrollment_to_dict(obj)
                add_audit_log(
                    self.session,
                    actor="System",
                    action="update",
                    entity="Enrollment",
                    entity_id=enrollment_id,
                    before=before,
                    after=after,
                )
                self.session.commit()
                self.load_enrollments()

            def redo_edit_dates():
                obj = self.session.get(Enrollment, enrollment_id)
                if obj is None:
                    return
                before = enrollment_to_dict(obj)
                obj.start_date = new_start
                obj.end_date = new_end
                after = enrollment_to_dict(obj)
                add_audit_log(
                    self.session,
                    actor="System",
                    action="update",
                    entity="Enrollment",
                    entity_id=enrollment_id,
                    before=before,
                    after=after,
                )
                self.session.commit()
                self.load_enrollments()

            self.undo_manager.push(
                undo_edit_dates,
                redo_edit_dates,
                f"Edit enrollment dates for student {student_id} in class {self.clazz.id}",
            )

    # --------------------------------------------------------------
    # Remove selected enrollment (student from this class) (UNDOABLE)
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

        # Snapshot BEFORE delete
        enrollment_id = e.id
        snapshot = {
            "id": e.id,
            "student_id": e.student_id,
            "class_id": e.class_id,
            "start_date": e.start_date,
            "end_date": e.end_date,
        }
        before_snapshot = enrollment_to_dict(e)

        def redo_remove():
            obj = self.session.get(Enrollment, enrollment_id)
            if obj is None:
                return
            before = enrollment_to_dict(obj)
            add_audit_log(
                self.session,
                actor="System",
                action="delete",
                entity="Enrollment",
                entity_id=enrollment_id,
                before=before,
                after=None,
            )
            self.session.delete(obj)
            self.session.commit()
            self.load_enrollments()
            self.load_available_students()

        def undo_remove():
            obj = self.session.get(Enrollment, enrollment_id)
            if obj is not None:
                return
            restored = Enrollment(
                id=snapshot["id"],
                student_id=snapshot["student_id"],
                class_id=snapshot["class_id"],
                start_date=snapshot["start_date"],
                end_date=snapshot["end_date"],
            )
            self.session.add(restored)
            self.session.flush()
            after = enrollment_to_dict(restored)
            add_audit_log(
                self.session,
                actor="System",
                action="create",
                entity="Enrollment",
                entity_id=restored.id,
                before=None,
                after=after,
            )
            self.session.commit()
            self.load_enrollments()
            self.load_available_students()

        # Perform the delete now
        redo_remove()

        # Register undo/redo
        if self.undo_manager is not None:
            self.undo_manager.push(
                undo_remove,
                redo_remove,
                f"Remove enrollment of student {student_id} from class {self.clazz.id}",
            )


class ManageClassTeachersDialog(QDialog):
    """
    Dialog to assign/remove teachers from a given class.
    Very similar to ManageEnrollmentsDialog, but for TeacherClassLink.
    """

    def __init__(self, session, clazz: Class, parent=None):
        super().__init__(parent)
        self.session = session
        self.clazz = clazz

        self.setWindowTitle(f"Manage Teachers - {clazz.name}")

        main_layout = QVBoxLayout()

        # Label at top
        main_layout.addWidget(QLabel(f"Class: {clazz.name} ({clazz.term or ''})"))

        # Table of currently assigned teachers
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Teacher ID", "First Name", "Last Name", "Email", "Phone"]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        main_layout.addWidget(QLabel("Assigned teachers:"))
        main_layout.addWidget(self.table)

        # --- Search + list of available teachers (Active, not linked) ---
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search active teachers:"))

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Name, email, or ID…")
        self.search_edit.textChanged.connect(self.load_available_teachers)
        search_layout.addWidget(self.search_edit)

        main_layout.addLayout(search_layout)

        self.available_table = QTableWidget()
        self.available_table.setColumnCount(4)
        self.available_table.setHorizontalHeaderLabels(
            ["ID", "First Name", "Last Name", "Email"]
        )
        self.available_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.available_table.setSelectionMode(QTableWidget.SingleSelection)
        self.available_table.setEditTriggers(QTableWidget.NoEditTriggers)

        main_layout.addWidget(QLabel("Available teachers (Active, not assigned):"))
        main_layout.addWidget(self.available_table)

        enroll_layout = QHBoxLayout()
        self.add_teacher_button = QPushButton("Add Selected Teacher")
        self.add_teacher_button.clicked.connect(self.add_teacher_link)
        enroll_layout.addWidget(self.add_teacher_button)
        enroll_layout.addStretch()
        main_layout.addLayout(enroll_layout)

        # Button row for removal + close
        buttons_layout = QHBoxLayout()
        self.remove_button = QPushButton("Remove Selected Teacher")
        self.remove_button.clicked.connect(self.remove_teacher_link)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        buttons_layout.addWidget(self.remove_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(close_button)

        main_layout.addLayout(buttons_layout)

        self.setLayout(main_layout)

        # Load data into tables
        self.load_assigned_teachers()
        self.load_available_teachers()

    # --------------------------------------------------------------
    # Load currently assigned teachers into the table
    # --------------------------------------------------------------
    def load_assigned_teachers(self):
        self.table.setRowCount(0)

        links = (
            self.session.query(TeacherClassLink)
            .filter(TeacherClassLink.class_id == self.clazz.id)
            .all()
        )

        self.table.setRowCount(len(links))

        for row, link in enumerate(links):
            t = link.teacher
            if t is None:
                continue
            self.table.setItem(row, 0, QTableWidgetItem(str(t.id)))
            self.table.setItem(row, 1, QTableWidgetItem(t.first_name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(t.last_name or ""))
            self.table.setItem(row, 3, QTableWidgetItem(t.email or ""))
            self.table.setItem(row, 4, QTableWidgetItem(t.phone or ""))

        self.table.resizeColumnsToContents()

    # --------------------------------------------------------------
    # Load available teachers (Active, not assigned) into the table
    # --------------------------------------------------------------
    def load_available_teachers(self):
        if not hasattr(self, "available_table"):
            return

        self.available_table.setRowCount(0)

        # Already assigned to this class
        assigned_ids = {
            link.teacher_id
            for link in self.session.query(TeacherClassLink)
            .filter(TeacherClassLink.class_id == self.clazz.id)
            .all()
        }

        # Base query: Active teachers not already assigned
        query = self.session.query(Teacher).filter(Teacher.status == "Active")
        if assigned_ids:
            query = query.filter(~Teacher.id.in_(assigned_ids))

        # Optional search filter
        search_text = ""
        if hasattr(self, "search_edit") and self.search_edit is not None:
            search_text = self.search_edit.text().strip()

        if search_text:
            try:
                search_id = int(search_text)
            except ValueError:
                search_id = None

            like = f"%{search_text}%"
            filters = [
                Teacher.first_name.ilike(like),
                Teacher.last_name.ilike(like),
                Teacher.email.ilike(like),
            ]
            if search_id is not None:
                filters.append(Teacher.id == search_id)

            query = query.filter(or_(*filters))

        available_teachers = (
            query.order_by(Teacher.last_name, Teacher.first_name, Teacher.id).all()
        )

        if not available_teachers:
            self.add_teacher_button.setEnabled(False)
            return

        self.add_teacher_button.setEnabled(True)
        self.available_table.setRowCount(len(available_teachers))

        for row, t in enumerate(available_teachers):
            self.available_table.setItem(row, 0, QTableWidgetItem(str(t.id)))
            self.available_table.setItem(row, 1, QTableWidgetItem(t.first_name or ""))
            self.available_table.setItem(row, 2, QTableWidgetItem(t.last_name or ""))
            self.available_table.setItem(row, 3, QTableWidgetItem(t.email or ""))

        self.available_table.resizeColumnsToContents()

    # --------------------------------------------------------------
    # Add link for selected teacher
    # --------------------------------------------------------------
    def add_teacher_link(self):
        row = self.available_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Add Teacher", "Please select a teacher to add."
            )
            return

        id_item = self.available_table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Add Teacher", "Could not determine teacher ID.")
            return

        try:
            teacher_id = int(id_item.text())
        except ValueError:
            QMessageBox.warning(self, "Add Teacher", "Invalid teacher ID.")
            return

        existing = (
            self.session.query(TeacherClassLink)
            .filter(
                TeacherClassLink.teacher_id == teacher_id,
                TeacherClassLink.class_id == self.clazz.id,
            )
            .first()
        )
        if existing:
            QMessageBox.information(
                self, "Add Teacher", "That teacher is already assigned to this class."
            )
            return

        link = TeacherClassLink(
            teacher_id=teacher_id,
            class_id=self.clazz.id,
        )
        self.session.add(link)
        self.session.flush()
        after = teacher_class_link_to_dict(link)
        add_audit_log(
            self.session,
            actor="System",
            action="create",
            entity="TeacherClassLink",
            entity_id=link.id,
            before=None,
            after=after,
        )

        self.session.commit()

        self.load_assigned_teachers()
        self.load_available_teachers()

    # --------------------------------------------------------------
    # Remove selected teacher link
    # --------------------------------------------------------------
    def remove_teacher_link(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Remove Teacher", "Please select a teacher to remove.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Remove Teacher", "Could not determine teacher ID.")
            return

        teacher_id = int(id_item.text())

        reply = QMessageBox.question(
            self,
            "Remove Teacher",
            f"Remove teacher ID {teacher_id} from this class?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        link = (
            self.session.query(TeacherClassLink)
            .filter(
                TeacherClassLink.teacher_id == teacher_id,
                TeacherClassLink.class_id == self.clazz.id,
            )
            .first()
        )
        if link is None:
            QMessageBox.warning(self, "Remove Teacher", "Link not found in database.")
            return

        before = teacher_class_link_to_dict(link)
        add_audit_log(
            self.session,
            actor="System",
            action="delete",
            entity="TeacherClassLink",
            entity_id=link.id,
            before=before,
            after=None,
        )

        self.session.delete(link)
        self.session.commit()

        self.load_assigned_teachers()
        self.load_available_teachers()
