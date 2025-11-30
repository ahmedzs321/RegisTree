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
    QDialogButtonBox,
    QTextEdit,
    QMessageBox,
    QGroupBox,
    QFileDialog,
    QDateEdit,
    QSizePolicy,
    QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from sqlalchemy import or_

from pathlib import Path
import shutil

from data.models import Teacher, TeacherClassLink, Class, TeacherAttendance, add_audit_log
from ui.undo_manager import UndoManager
from data.paths import TEACHER_PHOTOS_DIR


def teacher_to_dict(teacher: Teacher | None):
    """
    Convert a Teacher ORM object into a JSON-serializable dict
    for storing in AuditLog.before_json / after_json.
    """
    if teacher is None:
        return None
    return {
        "id": teacher.id,
        "first_name": teacher.first_name,
        "last_name": teacher.last_name,
        "phone": teacher.phone,
        "email": teacher.email,
        "emergency_contact_name": teacher.emergency_contact_name,
        "emergency_contact_phone": teacher.emergency_contact_phone,
        "status": teacher.status,
        "notes": teacher.notes,
        "photo_path": teacher.photo_path,
    }


class TeachersView(QWidget):
    """
    Teachers tab:
    - List all teachers
    - Search/filter
    - Add / Edit / Delete
    - Double-click → open Teacher Profile
    """

    def __init__(self, session, settings=None, undo_manager: UndoManager | None = None):
        super().__init__()
        self.session = session
        self.settings = settings
        self.undo_manager = undo_manager

        layout = QVBoxLayout()

        # --- Top buttons ---
        btn_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Teacher")
        self.delete_button = QPushButton("Delete Selected")
        btn_layout.addWidget(self.add_button)
        btn_layout.addWidget(self.delete_button)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # --- Search + Status filter ---
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Name, email, or ID…")
        filter_layout.addWidget(self.search_edit)

        filter_layout.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Active", "Inactive"])
        filter_layout.addWidget(self.status_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # --- Teachers table ---
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "First Name",
                "Last Name",
                "Phone",
                "Email",
                "Emergency Contact Name",
                "Emergency Contact Phone",
                "Status",
                "Notes",
            ]
        )
        # Make cells read-only; use dialogs / widgets for edits
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        layout.addWidget(self.table)

        self.setLayout(layout)

        # Wire up signals
        self.add_button.clicked.connect(self.add_teacher)
        self.delete_button.clicked.connect(self.delete_teacher)
        self.search_edit.textChanged.connect(self.load_teachers)
        self.status_filter.currentTextChanged.connect(self.load_teachers)
        self.table.itemDoubleClicked.connect(self.open_teacher_profile)

        # Initial load
        self.load_teachers()

    # ------------------------------------------------------------------
    # Load teachers into table
    # ------------------------------------------------------------------
    def load_teachers(self):
        self.table.setRowCount(0)

        search_text = self.search_edit.text().strip() if hasattr(self, "search_edit") else ""
        status_value = self.status_filter.currentText() if hasattr(self, "status_filter") else "All"

        query = self.session.query(Teacher)

        # Status filter
        if status_value != "All":
            query = query.filter(Teacher.status == status_value)

        # Search filter
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

        # Order: last name, first name, then id
        teachers = (
            query.order_by(Teacher.last_name, Teacher.first_name, Teacher.id).all()
        )

        self.table.setRowCount(len(teachers))

        for row, t in enumerate(teachers):
            self.table.setItem(row, 0, QTableWidgetItem(str(t.id)))
            self.table.setItem(row, 1, QTableWidgetItem(t.first_name or ""))
            self.table.setItem(row, 2, QTableWidgetItem(t.last_name or ""))
            self.table.setItem(row, 3, QTableWidgetItem(t.phone or ""))
            self.table.setItem(row, 4, QTableWidgetItem(t.email or ""))
            self.table.setItem(row, 5, QTableWidgetItem(t.emergency_contact_name or ""))
            self.table.setItem(row, 6, QTableWidgetItem(t.emergency_contact_phone or ""))
            self.table.setItem(row, 7, QTableWidgetItem(t.status or ""))
            self.table.setItem(row, 8, QTableWidgetItem(t.notes or ""))

        self.table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Add new teacher
    # ------------------------------------------------------------------
    def add_teacher(self):
        dialog = AddTeacherDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        data = dialog.get_data()
        if data is None:
            return

        (
            first_name,
            last_name,
            phone,
            email,
            emergency_name,
            emergency_phone,
            status,
            notes,
        ) = data

        t = Teacher(
            first_name=first_name,
            last_name=last_name,
            phone=phone or None,
            email=email or None,
            emergency_contact_name=emergency_name or None,
            emergency_contact_phone=emergency_phone or None,
            status=status,
            notes=notes or None,
        )
        self.session.add(t)
        # Get PK + snapshot before commit
        self.session.flush()
        after = teacher_to_dict(t)
        add_audit_log(
            self.session,
            actor="System",
            action="create",
            entity="Teacher",
            entity_id=t.id,
            before=None,
            after=after,
        )

        self.session.commit()
        self.load_teachers()

    # ------------------------------------------------------------------
    # Delete selected teacher (UNDOABLE)
    # ------------------------------------------------------------------
    def delete_teacher(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Delete Teacher", "Please select a teacher to delete.")
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Delete Teacher", "Could not determine teacher ID.")
            return

        teacher_id = int(id_item.text())

        reply = QMessageBox.question(
            self,
            "Delete Teacher",
            f"Are you sure you want to delete teacher ID {teacher_id}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        teacher = self.session.get(Teacher, teacher_id)
        if teacher is None:
            QMessageBox.warning(self, "Delete Teacher", "Teacher not found in database.")
            return

        # Snapshot teacher + class links BEFORE delete (for undo + audit)
        snapshot_teacher = {
            "id": teacher.id,
            "first_name": teacher.first_name,
            "last_name": teacher.last_name,
            "phone": teacher.phone,
            "email": teacher.email,
            "emergency_contact_name": teacher.emergency_contact_name,
            "emergency_contact_phone": teacher.emergency_contact_phone,
            "status": teacher.status,
            "notes": teacher.notes,
            "photo_path": teacher.photo_path,
        }

        snapshot_links = [
            {"class_id": link.class_id}
            for link in teacher.class_links
        ]

        def redo_delete():
            """Perform the delete (used initially and on redo) with audit log."""
            obj = self.session.get(Teacher, snapshot_teacher["id"])
            if obj is None:
                return
            before = teacher_to_dict(obj)
            add_audit_log(
                self.session,
                actor="System",
                action="delete",
                entity="Teacher",
                entity_id=obj.id,
                before=before,
                after=None,
            )
            self.session.delete(obj)
            self.session.commit()
            self.load_teachers()

        def undo_delete():
            """Recreate the teacher + their class links, with audit log."""
            existing = self.session.get(Teacher, snapshot_teacher["id"])
            if existing is None:
                restored = Teacher(
                    id=snapshot_teacher["id"],
                    first_name=snapshot_teacher["first_name"],
                    last_name=snapshot_teacher["last_name"],
                    phone=snapshot_teacher["phone"],
                    email=snapshot_teacher["email"],
                    emergency_contact_name=snapshot_teacher["emergency_contact_name"],
                    emergency_contact_phone=snapshot_teacher["emergency_contact_phone"],
                    status=snapshot_teacher["status"],
                    notes=snapshot_teacher["notes"],
                    photo_path=snapshot_teacher["photo_path"],
                )
                self.session.add(restored)
                self.session.flush()

                # Recreate links
                for link_data in snapshot_links:
                    link = TeacherClassLink(
                        teacher_id=restored.id,
                        class_id=link_data["class_id"],
                    )
                    self.session.add(link)

                after = teacher_to_dict(restored)
                add_audit_log(
                    self.session,
                    actor="System",
                    action="create",
                    entity="Teacher",
                    entity_id=restored.id,
                    before=None,
                    after=after,
                )

                self.session.commit()

            self.load_teachers()

        # Perform the delete now (logs once for the user action)
        redo_delete()

        # Register undo/redo
        if self.undo_manager is not None:
            self.undo_manager.push(
                undo_delete,
                redo_delete,
                f"Delete teacher {teacher_id}",
            )

    # ------------------------------------------------------------------
    # Open teacher profile on double-click
    # ------------------------------------------------------------------
    def open_teacher_profile(self, item=None):
        row = self.table.currentRow()
        if row < 0:
            return

        id_item = self.table.item(row, 0)
        if id_item is None:
            return

        teacher_id = int(id_item.text())
        teacher = (
            self.session.query(Teacher)
            .filter(Teacher.id == teacher_id)
            .first()
        )
        if teacher is None:
            QMessageBox.warning(self, "Teacher Profile", "Teacher not found in database.")
            return

        dialog = TeacherProfileDialog(
            self.session,
            teacher,
            parent_view=self,
            undo_manager=self.undo_manager,
            parent=self,
        )
        dialog.exec()


class AddTeacherDialog(QDialog):
    """
    Dialog to add or edit a Teacher.
    """

    def __init__(self, parent=None, teacher: Teacher | None = None):
        super().__init__(parent)
        self._teacher = teacher
        self.setWindowTitle("Edit Teacher" if teacher else "Add Teacher")

        layout = QVBoxLayout()
        form = QFormLayout()

        self.first_name_edit = QLineEdit()
        self.last_name_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.email_edit = QLineEdit()

        # Emergency contact
        self.emergency_name_edit = QLineEdit()
        self.emergency_phone_edit = QLineEdit()

        self.status_combo = QComboBox()
        self.status_combo.addItems(["Active", "Inactive"])

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Notes about this teacher (optional)…")

        form.addRow("First Name:", self.first_name_edit)
        form.addRow("Last Name:", self.last_name_edit)
        form.addRow("Phone:", self.phone_edit)
        form.addRow("Email:", self.email_edit)
        form.addRow("Emergency Contact Name:", self.emergency_name_edit)
        form.addRow("Emergency Contact Phone:", self.emergency_phone_edit)
        form.addRow("Status:", self.status_combo)
        form.addRow("Notes:", self.notes_edit)

        layout.addLayout(form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

        # If editing, pre-fill from existing teacher
        if self._teacher is not None:
            self.first_name_edit.setText(self._teacher.first_name or "")
            self.last_name_edit.setText(self._teacher.last_name or "")
            self.phone_edit.setText(self._teacher.phone or "")
            self.email_edit.setText(self._teacher.email or "")
            self.emergency_name_edit.setText(self._teacher.emergency_contact_name or "")
            self.emergency_phone_edit.setText(self._teacher.emergency_contact_phone or "")
            status = self._teacher.status or "Active"
            idx = self.status_combo.findText(status)
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)
            self.notes_edit.setPlainText(self._teacher.notes or "")

    def get_data(self):
        first_name = self.first_name_edit.text().strip()
        last_name = self.last_name_edit.text().strip()
        phone = self.phone_edit.text().strip()
        email = self.email_edit.text().strip()
        emergency_name = self.emergency_name_edit.text().strip()
        emergency_phone = self.emergency_phone_edit.text().strip()
        status = self.status_combo.currentText()
        notes = self.notes_edit.toPlainText().strip()

        if not first_name or not last_name:
            QMessageBox.warning(
                self,
                "Validation Error",
                "First name and last name are required.",
            )
            return None

        return (
            first_name,
            last_name,
            phone,
            email,
            emergency_name,
            emergency_phone,
            status,
            notes,
        )


class TeacherProfileDialog(QDialog):
    """
    Profile view for a Teacher:
    LEFT PANE:
        - Photo, name, contact info, status, notes, classes
    RIGHT PANE:
        - Teacher attendance / check-in history (read-only table)
    """

    def __init__(
        self,
        session,
        teacher: Teacher,
        parent_view: TeachersView,
        undo_manager: UndoManager | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.session = session
        self.teacher = teacher
        self.parent_view = parent_view
        self.undo_manager = undo_manager

        self.setWindowTitle(f"Teacher Profile - {teacher.first_name} {teacher.last_name}")

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # Build UI once, then we can update labels after edits
        self._build_ui()
        self._populate_classes()
        self._populate_attendance_history()

    def _build_ui(self):
        t = self.teacher

        # ------------------------------------------------------------------
        # Two-pane content area: left (profile) and right (attendance history)
        # ------------------------------------------------------------------
        content_layout = QHBoxLayout()

        # =======================
        # LEFT COLUMN (Profile)
        # =======================
        left_col = QVBoxLayout()

        # --- Top area: photo + name/contact side by side ---
        top_layout = QHBoxLayout()

        # Photo label (headshot rectangle)
        self.photo_label = QLabel()
        self.photo_label.setFixedSize(120, 160)  # headshot-like rectangle
        self.photo_label.setAlignment(Qt.AlignCenter)
        self.photo_label.setStyleSheet(
            "border: 1px solid #ccc; background-color: #f5f5f5;"
        )
        top_layout.addWidget(self.photo_label)

        # Name + contact on the right
        name_contact_layout = QVBoxLayout()

        self.name_label = QLabel()
        self.name_label.setTextFormat(Qt.RichText)
        name_contact_layout.addWidget(self.name_label)

        self.contact_label = QLabel()
        self.contact_label.setTextFormat(Qt.RichText)
        name_contact_layout.addWidget(self.contact_label)

        name_contact_layout.addStretch()
        top_layout.addLayout(name_contact_layout)

        left_col.addLayout(top_layout)

        # Notes
        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout()
        self.notes_view = QTextEdit()
        self.notes_view.setReadOnly(True)
        notes_layout.addWidget(self.notes_view)
        notes_group.setLayout(notes_layout)
        left_col.addWidget(notes_group)

        # Class history / list
        self.classes_group = QGroupBox("Classes")
        self.classes_layout = QVBoxLayout()
        self.classes_group.setLayout(self.classes_layout)
        left_col.addWidget(self.classes_group)

        left_col.addStretch()

        # ============================
        # RIGHT COLUMN (Attendance)
        # ============================
        right_col = QVBoxLayout()

        self.attendance_group = QGroupBox("Teacher Tracker")
        att_layout = QVBoxLayout()

        self.attendance_table = QTableWidget()
        self.attendance_table.setColumnCount(5)
        self.attendance_table.setHorizontalHeaderLabels(
            ["Date", "Status", "Check-In", "Check-Out", "Marked By"]
        )
        self.attendance_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.attendance_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.attendance_table.setSelectionMode(QTableWidget.SingleSelection)

        att_layout.addWidget(self.attendance_table)
        self.attendance_group.setLayout(att_layout)

        # Make the attendance pane use available vertical space
        self.attendance_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        right_col.addWidget(self.attendance_group)

        # Put both columns into the content layout
        content_layout.addLayout(left_col, 3)   # wider profile column
        content_layout.addLayout(right_col, 4)  # slightly wider history column

        self.main_layout.addLayout(content_layout)

        # ------------------------------------------------------------------
        # Bottom buttons: Change Photo + Edit + Close
        # ------------------------------------------------------------------
        button_box = QDialogButtonBox()
        self.change_photo_button = QPushButton("Change Photo…")
        button_box.addButton(self.change_photo_button, QDialogButtonBox.ActionRole)

        self.edit_button = QPushButton("Edit Teacher…")
        button_box.addButton(self.edit_button, QDialogButtonBox.ActionRole)

        close_button = button_box.addButton(QDialogButtonBox.Close)
        close_button.clicked.connect(self.reject)

        self.change_photo_button.clicked.connect(self.change_photo)
        self.edit_button.clicked.connect(self.edit_teacher)

        self.main_layout.addWidget(button_box)

        # Initial text + photo
        self._refresh_header_and_notes()
        self._load_photo()

    def _refresh_header_and_notes(self):
        t = self.teacher
        self.name_label.setText(f"<h2>{t.first_name} {t.last_name}</h2>")
        self.contact_label.setText(
            f"<b>Status:</b> {t.status or ''}<br>"
            f"<b>Phone:</b> {t.phone or ''}<br>"
            f"<b>Email:</b> {t.email or ''}<br>"
            f"<b>Emergency Contact:</b> {t.emergency_contact_name or ''}<br>"
            f"<b>Emergency Phone:</b> {t.emergency_contact_phone or ''}"
        )
        self.notes_view.setPlainText(t.notes or "")

    def _load_photo(self):
        """
        Load and display the teacher's photo from teacher.photo_path
        into self.photo_label, scaled to fit.
        """
        # Clear any previous pixmap/text
        self.photo_label.setPixmap(QPixmap())
        self.photo_label.setText("No Photo")

        path_str = self.teacher.photo_path
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
        """
        Let the user choose a new photo for this teacher.
        The chosen file is copied into photos/teachers/ and the teacher.photo_path
        is updated to point to the copied file, with audit log.
        """
        # Choose image file
        file_path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Teacher Photo",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*.*)",
        )
        if not file_path_str:
            return  # user cancelled

        src_path = Path(file_path_str)
        if not src_path.is_file():
            QMessageBox.warning(
                self,
                "Change Photo",
                "The selected file does not exist.",
            )
            return

        # Ensure this teacher is still in DB
        teacher = self.session.get(Teacher, self.teacher.id)
        if teacher is None:
            QMessageBox.warning(
                self,
                "Change Photo",
                "Teacher no longer exists in the database.",
            )
            return

        # Destination folder for teacher photos (from paths.py)
        photos_dir = TEACHER_PHOTOS_DIR
        try:
            photos_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Change Photo",
                f"Could not create photo directory:\n{photos_dir}\n\n{exc}",
            )
            return

        # Use teacher id + original extension as filename
        suffix = src_path.suffix.lower() or ".png"
        dest_path = photos_dir / f"teacher_{teacher.id}{suffix}"

        try:
            shutil.copy2(src_path, dest_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Change Photo",
                f"Failed to copy photo:\n{exc}",
            )
            return

        before = teacher_to_dict(teacher)
        # Update DB field
        teacher.photo_path = str(dest_path)
        after = teacher_to_dict(teacher)

        add_audit_log(
            self.session,
            actor="System",
            action="update",
            entity="Teacher",
            entity_id=teacher.id,
            before=before,
            after=after,
        )

        self.session.commit()

        # Refresh local object + UI
        self.teacher = teacher
        self._load_photo()
        QMessageBox.information(
            self,
            "Change Photo",
            "Photo updated successfully.",
        )

    def _populate_classes(self):
        # Clear any existing labels
        while self.classes_layout.count():
            item = self.classes_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        links = (
            self.session.query(TeacherClassLink)
            .filter(TeacherClassLink.teacher_id == self.teacher.id)
            .all()
        )
        if links:
            for link in links:
                clazz = link.clazz
                if clazz is None:
                    continue
                text = f"{clazz.name or 'Unnamed'}  |  {clazz.subject or ''}  |  {clazz.term or ''}"
                self.classes_layout.addWidget(QLabel(text))
        else:
            self.classes_layout.addWidget(QLabel("No classes assigned."))

    def _populate_attendance_history(self):
        """
        Fill the right-pane table with this teacher's per-day attendance
        (TeacherAttendance), ordered by date descending.
        """
        records = (
            self.session.query(TeacherAttendance)
            .filter(TeacherAttendance.teacher_id == self.teacher.id)
            .order_by(TeacherAttendance.date.desc())
            .all()
        )

        self.attendance_table.setRowCount(0)

        # --- NEW: detect if any record has check-in or check-out times ---
        has_any_times = any(
            (rec.check_in_time is not None) or (rec.check_out_time is not None)
            for rec in records
        )

        if not records:
            # No rows at all → also hide the time columns for a clean look
            self.attendance_table.setColumnHidden(2, True)  # Check-In
            self.attendance_table.setColumnHidden(3, True)  # Check-Out
            return

        self.attendance_table.setRowCount(len(records))

        for row, rec in enumerate(records):
            # Date
            date_str = rec.date.isoformat() if rec.date else ""
            item_date = QTableWidgetItem(date_str)
            self.attendance_table.setItem(row, 0, item_date)

            # Status
            item_status = QTableWidgetItem(rec.status or "")
            self.attendance_table.setItem(row, 1, item_status)

            # Check-in / Check-out (only show time portion if present)
            if rec.check_in_time is not None:
                check_in_str = rec.check_in_time.isoformat(sep=" ", timespec="minutes")
            else:
                check_in_str = ""
            if rec.check_out_time is not None:
                check_out_str = rec.check_out_time.isoformat(sep=" ", timespec="minutes")
            else:
                check_out_str = ""

            item_in = QTableWidgetItem(check_in_str)
            item_out = QTableWidgetItem(check_out_str)
            self.attendance_table.setItem(row, 2, item_in)
            self.attendance_table.setItem(row, 3, item_out)

            # Marked by
            item_marked = QTableWidgetItem(rec.marked_by or "")
            self.attendance_table.setItem(row, 4, item_marked)

        self.attendance_table.resizeColumnsToContents()

        # --- NEW: hide/show the time columns based on whether any times exist ---
        self.attendance_table.setColumnHidden(2, not has_any_times)  # Check-In
        self.attendance_table.setColumnHidden(3, not has_any_times)  # Check-Out

    def edit_teacher(self):
        """
        Open the AddTeacherDialog in 'edit' mode, update the DB,
        refresh the parent view table and this profile UI, and register undo/redo.
        """
        # Re-fetch latest teacher from DB, in case of stale instance
        teacher = self.session.get(Teacher, self.teacher.id)
        if teacher is None:
            QMessageBox.warning(
                self,
                "Edit Teacher",
                "Teacher no longer exists in the database.",
            )
            return

        # Snapshot BEFORE changes (for undo + audit)
        old_data = {
            "first_name": teacher.first_name,
            "last_name": teacher.last_name,
            "phone": teacher.phone,
            "email": teacher.email,
            "emergency_contact_name": teacher.emergency_contact_name,
            "emergency_contact_phone": teacher.emergency_contact_phone,
            "status": teacher.status,
            "notes": teacher.notes,
        }
        before_snapshot = teacher_to_dict(teacher)

        dialog = AddTeacherDialog(self, teacher=teacher)
        if dialog.exec() != QDialog.Accepted:
            return

        data = dialog.get_data()
        if data is None:
            return

        (
            first_name,
            last_name,
            phone,
            email,
            emergency_name,
            emergency_phone,
            status,
            notes,
        ) = data

        teacher.first_name = first_name
        teacher.last_name = last_name
        teacher.phone = phone or None
        teacher.email = email or None
        teacher.emergency_contact_name = emergency_name or None
        teacher.emergency_contact_phone = emergency_phone or None
        teacher.status = status
        teacher.notes = notes or None

        # Snapshot AFTER changes (for undo + audit)
        new_data = {
            "first_name": teacher.first_name,
            "last_name": teacher.last_name,
            "phone": teacher.phone,
            "email": teacher.email,
            "emergency_contact_name": teacher.emergency_contact_name,
            "emergency_contact_phone": teacher.emergency_contact_phone,
            "status": teacher.status,
            "notes": teacher.notes,
        }
        after_snapshot = teacher_to_dict(teacher)

        # Audit log for this edit
        add_audit_log(
            self.session,
            actor="System",
            action="update",
            entity="Teacher",
            entity_id=teacher.id,
            before=before_snapshot,
            after=after_snapshot,
        )

        self.session.commit()

        # Refresh parent view table
        if hasattr(self.parent_view, "load_teachers"):
            self.parent_view.load_teachers()

        # Refresh our own labels
        self.teacher = teacher
        self._refresh_header_and_notes()
        self._load_photo()
        # Attendance history is derived from TeacherAttendance; no change
        # is made here, so we don't need to repopulate that table.

        # Register undo/redo
        if self.undo_manager is not None:
            teacher_id = teacher.id

            def apply_data(obj: Teacher, data_dict: dict):
                obj.first_name = data_dict["first_name"]
                obj.last_name = data_dict["last_name"]
                obj.phone = data_dict["phone"]
                obj.email = data_dict["email"]
                obj.emergency_contact_name = data_dict["emergency_contact_name"]
                obj.emergency_contact_phone = data_dict["emergency_contact_phone"]
                obj.status = data_dict["status"]
                obj.notes = data_dict["notes"]

            def undo_edit():
                obj = self.session.get(Teacher, teacher_id)
                if obj is None:
                    return
                before = teacher_to_dict(obj)
                apply_data(obj, old_data)
                after = teacher_to_dict(obj)
                add_audit_log(
                    self.session,
                    actor="System",
                    action="update",
                    entity="Teacher",
                    entity_id=obj.id,
                    before=before,
                    after=after,
                )
                self.session.commit()
                if hasattr(self.parent_view, "load_teachers"):
                    self.parent_view.load_teachers()
                self.teacher = obj
                self._refresh_header_and_notes()
                self._load_photo()

            def redo_edit():
                obj = self.session.get(Teacher, teacher_id)
                if obj is None:
                    return
                before = teacher_to_dict(obj)
                apply_data(obj, new_data)
                after = teacher_to_dict(obj)
                add_audit_log(
                    self.session,
                    actor="System",
                    action="update",
                    entity="Teacher",
                    entity_id=obj.id,
                    before=before,
                    after=after,
                )
                self.session.commit()
                if hasattr(self.parent_view, "load_teachers"):
                    self.parent_view.load_teachers()
                self.teacher = obj
                self._refresh_header_and_notes()
                self._load_photo()

            self.undo_manager.push(
                undo_edit,
                redo_edit,
                f"Edit teacher {teacher_id}",
            )
