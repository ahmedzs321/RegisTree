import json
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QComboBox,
    QFormLayout,
    QPlainTextEdit,
)
from data.models import AdminUser
from data.security import verify_password
from ui.auth_dialogs import LoginDialog

GRADE_SCALE = [
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

class SettingsView(QWidget):
    """
    Global application settings for RegisTree.

    Backed by a single Settings row in the database.
    """

    DEFAULT_STATUSES = ["Present", "Absent", "Tardy", "Excused"]

    def __init__(self, session, settings, students_view=None):
        super().__init__()
        self.session = session
        self.settings = settings
        self.students_view = students_view

        main_layout = QVBoxLayout()

        form = QFormLayout()

        # School name
        self.school_name_edit = QLineEdit()
        form.addRow("School name:", self.school_name_edit)

        # Academic year
        self.academic_year_edit = QLineEdit()
        self.academic_year_edit.setPlaceholderText("e.g. 2025-2026")
        form.addRow("Academic year:", self.academic_year_edit)

        # Attendance statuses (one per line)
        self.statuses_edit = QPlainTextEdit()
        self.statuses_edit.setPlaceholderText(
            "One status per line, for example:\n"
            "Present\n"
            "Absent\n"
            "Tardy\n"
            "Excused"
        )
        form.addRow(QLabel("Attendance statuses:"), self.statuses_edit)

        # Export base directory
        export_layout = QHBoxLayout()
        self.export_dir_edit = QLineEdit()
        self.export_dir_edit.setPlaceholderText("Default export folder")
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self.choose_export_dir)
        export_layout.addWidget(self.export_dir_edit)
        export_layout.addWidget(browse_button)
        form.addRow("Default export folder:", export_layout)

        # Grade range (starting and graduating grades)
        self.starting_grade_combo = QComboBox()
        self.starting_grade_combo.addItems(GRADE_SCALE)

        self.graduating_grade_combo = QComboBox()
        self.graduating_grade_combo.addItems(GRADE_SCALE)

        form.addRow("Starting grade:", self.starting_grade_combo)
        form.addRow("Graduating grade:", self.graduating_grade_combo)

        # Attendance auto-save toggle (stored for future behavior)
        self.auto_save_checkbox = QCheckBox("Enable auto-save for attendance")
        form.addRow("Attendance auto-save:", self.auto_save_checkbox)

        main_layout.addLayout(form)

        # --- Academic Year Tools (Promotion) ---
        promotion_group = QGroupBox("Academic Year Tools")
        promotion_layout = QVBoxLayout()

        promo_desc = QLabel(
            "Use this action at the start of a new academic year.\n"
            "All ACTIVE students will be promoted by one grade level.\n"
            "Students in the top grade will be marked as Graduated."
        )
        promo_desc.setWordWrap(True)
        promotion_layout.addWidget(promo_desc)

        promo_button_layout = QHBoxLayout()
        self.promote_button = QPushButton("Promote All Students to Next Grade")
        self.promote_button.clicked.connect(self.on_promote_students_clicked)
        promo_button_layout.addWidget(self.promote_button)
        promo_button_layout.addStretch()
        promotion_layout.addLayout(promo_button_layout)

        promotion_group.setLayout(promotion_layout)
        main_layout.addWidget(promotion_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.reset_statuses_button = QPushButton("Reset statuses to defaults")
        self.reset_statuses_button.clicked.connect(self.reset_statuses)
        button_layout.addWidget(self.reset_statuses_button)

        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_button)

        main_layout.addLayout(button_layout)
        main_layout.addStretch()

        self.setLayout(main_layout)

        # Populate UI from DB row
        self.load_from_model()

    # ------------------------------------------------------------------
    # Load / Save helpers
    # ------------------------------------------------------------------
    def load_from_model(self):
        # Basic text fields
        self.school_name_edit.setText(self.settings.school_name or "")
        self.academic_year_edit.setText(self.settings.academic_year or "")

        # Attendance statuses
        try:
            raw = self.settings.attendance_statuses_json or "[]"
            statuses = json.loads(raw)
        except Exception:
            statuses = self.DEFAULT_STATUSES

        if not isinstance(statuses, list) or not statuses:
            statuses = self.DEFAULT_STATUSES

        self.statuses_edit.setPlainText("\n".join(statuses))

        # Export folder
        if self.settings.export_base_dir:
            base_dir = self.settings.export_base_dir
        else:
            base_dir = str(Path("exports").resolve())
        self.export_dir_edit.setText(base_dir)

        # Grade range from settings
        start_grade = (self.settings.starting_grade or "K").strip()
        grad_grade = (self.settings.graduating_grade or "12th").strip()

        # Fall back if not in our canonical list
        if start_grade not in GRADE_SCALE:
            start_grade = "K"
        if grad_grade not in GRADE_SCALE:
            grad_grade = "12th"

        start_index = GRADE_SCALE.index(start_grade)
        grad_index = GRADE_SCALE.index(grad_grade)

        self.starting_grade_combo.setCurrentIndex(start_index)
        self.graduating_grade_combo.setCurrentIndex(grad_index)

        # Auto-save flag
        self.auto_save_checkbox.setChecked(bool(self.settings.attendance_auto_save))

    def reset_statuses(self):
        self.statuses_edit.setPlainText("\n".join(self.DEFAULT_STATUSES))

    def choose_export_dir(self):
        current = self.export_dir_edit.text().strip() or str(Path.cwd())
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose export folder",
            current,
        )
        if directory:
            self.export_dir_edit.setText(directory)

    def save_settings(self):
        # Parse statuses
        raw_lines = self.statuses_edit.toPlainText().splitlines()
        statuses = [line.strip() for line in raw_lines if line.strip()]

        if not statuses:
            QMessageBox.warning(
                self,
                "Settings",
                "Please specify at least one attendance status.",
            )
            return

        # Validate / prepare export directory
        export_dir = self.export_dir_edit.text().strip()
        if export_dir:
            try:
                Path(export_dir).mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "Settings",
                    f"Could not create export directory:\n{export_dir}\n\n{exc}",
                )
                return

        # Validate and save grade range
        start_index = self.starting_grade_combo.currentIndex()
        grad_index = self.graduating_grade_combo.currentIndex()

        if start_index > grad_index:
            QMessageBox.warning(
                self,
                "Settings",
                "Starting grade must be earlier than or equal to the graduating grade.",
            )
            return

        self.settings.starting_grade = GRADE_SCALE[start_index]
        self.settings.graduating_grade = GRADE_SCALE[grad_index]

        # Write values back into the Settings row
        self.settings.school_name = self.school_name_edit.text().strip() or None
        self.settings.academic_year = self.academic_year_edit.text().strip() or None
        self.settings.attendance_statuses_json = json.dumps(statuses)
        self.settings.export_base_dir = export_dir or None
        self.settings.attendance_auto_save = self.auto_save_checkbox.isChecked()

        self.session.add(self.settings)
        self.session.commit()

        # Notify StudentsView that grade range has changed
        if self.students_view is not None:
            # Make sure it sees the latest settings object
            self.students_view.settings = self.settings
            # Rebuild the grade_choices list for Add/Edit dialogs
            if hasattr(self.students_view, "refresh_grade_choices"):
                self.students_view.refresh_grade_choices()

        QMessageBox.information(self, "Settings", "Settings saved.")

    def on_promote_students_clicked(self):
        """
        Ask the admin for their password, then run the global promotion
        using the StudentsView logic.
        """
        if self.students_view is None:
            QMessageBox.warning(
                self,
                "Promote Students",
                "Students view is not available. Cannot run promotion.",
            )
            return

        # Step 1: Confirm the action itself
        reply = QMessageBox.question(
            self,
            "Promote All Students",
            "This will promote ALL ACTIVE students to the next grade level.\n"
            "Students in the top grade will be marked as Graduated.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Step 2: Require admin password
        admin = self.session.query(AdminUser).first()
        if admin is None:
            QMessageBox.warning(
                self,
                "Promote Students",
                "No admin user found. Cannot verify password.",
            )
            return

        login_dialog = LoginDialog(
            verify_func=verify_password,
            stored_hash=admin.password_hash,
        )
        result = login_dialog.exec()
        if result != LoginDialog.Accepted:
            # Wrong password or cancelled
            QMessageBox.information(
                self,
                "Promote Students",
                "Promotion cancelled or password was incorrect.",
            )
            return

        # Step 3: Run the existing promotion logic on StudentsView
        self.students_view.promote_all_students()