# ui/startup_dialog.py

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QGroupBox,
    QProgressBar,
    QMessageBox,
    QSizePolicy,
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

from data.models import AdminUser
from data.security import hash_password, verify_password
from data.paths import ICON_PATH  # 🔹 central icon path


class StartupDialog(QDialog):
    """
    Splash/loading + first-time admin setup / login dialog.

    - Left pane: logo, welcome text, contact, version.
    - Right pane: loading bar + password creation/login.
    """

    def __init__(self, session, version: str, parent=None):
        super().__init__(parent)
        self.session = session
        self.version = version

        self.setWindowTitle(f"RegisTree {self.version} - Starting up…")
        self.resize(700, 350)

        main_layout = QHBoxLayout()
        self.setLayout(main_layout)

        # ==========================
        # LEFT PANE (Logo + Welcome)
        # ==========================
        left_layout = QVBoxLayout()

        # Top stretch → pushes content downward
        left_layout.addStretch()

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)

        # Use bundled icon path from data.paths (PyInstaller-safe)
        if ICON_PATH.is_file():
            pix = QPixmap(str(ICON_PATH))
            if not pix.isNull():
                scaled = pix.scaled(
                    160,
                    160,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.icon_label.setPixmap(scaled)
        else:
            self.icon_label.setText("RegisTree")

        left_layout.addWidget(self.icon_label, alignment=Qt.AlignHCenter)

        welcome_label = QLabel("Welcome!")
        welcome_label.setAlignment(Qt.AlignCenter)
        font = welcome_label.font()
        font.setPointSize(18)
        font.setBold(True)
        welcome_label.setFont(font)
        left_layout.addWidget(welcome_label, alignment=Qt.AlignHCenter)

        # Version label
        version_label = QLabel(f"Version {self.version}")
        version_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(version_label, alignment=Qt.AlignHCenter)

        contact_label = QLabel(
            "Questions? Concerns?<br>"
            "Reach out at:<br>"
            "<b>registree.novofia@gmail.com</b>"
        )
        contact_label.setAlignment(Qt.AlignCenter)
        contact_label.setWordWrap(True)
        contact_label.setTextFormat(Qt.RichText)
        left_layout.addWidget(contact_label, alignment=Qt.AlignHCenter)

        # Bottom stretch → pushes content upward
        left_layout.addStretch()

        main_layout.addLayout(left_layout, 1)

        # ==========================
        # RIGHT PANE (Progress + Auth)
        # ==========================
        right_col = QVBoxLayout()
        right_col.addStretch()

        # Progress bar (indeterminate at startup)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)        # indeterminate / busy
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumWidth(320)
        self.progress_bar.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        right_col.addWidget(self.progress_bar)

        # Decide whether to show first-time setup or login
        admin_exists = self.session.query(AdminUser).first() is not None
        if admin_exists:
            group = self._build_login_group()
        else:
            group = self._build_first_time_setup_group()

        right_col.addWidget(group)
        right_col.addStretch()

        main_layout.addLayout(right_col, 1)

    # -----------------------------------------
    # First-time setup (create admin password)
    # -----------------------------------------
    def _build_first_time_setup_group(self) -> QGroupBox:
        group = QGroupBox("First-time Setup")

        layout = QVBoxLayout()

        info = QLabel(
            "It looks like this is your first time running RegisTree.\n"
            "Please create an admin password for this computer."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form_layout = QVBoxLayout()

        self.setup_password_edit = QLineEdit()
        self.setup_password_edit.setEchoMode(QLineEdit.Password)
        self.setup_password_edit.setPlaceholderText("Admin password")

        self.setup_confirm_edit = QLineEdit()
        self.setup_confirm_edit.setEchoMode(QLineEdit.Password)
        self.setup_confirm_edit.setPlaceholderText("Confirm password")

        form_layout.addWidget(self.setup_password_edit)
        form_layout.addWidget(self.setup_confirm_edit)

        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        create_btn = QPushButton("Create Admin and Continue")
        create_btn.clicked.connect(self._handle_first_time_setup)
        btn_layout.addWidget(create_btn)
        layout.addLayout(btn_layout)

        group.setLayout(layout)
        return group

    def _handle_first_time_setup(self):
        pwd = self.setup_password_edit.text().strip()
        confirm = self.setup_confirm_edit.text().strip()

        if not pwd:
            QMessageBox.warning(self, "Setup", "Password cannot be empty.")
            return

        if pwd != confirm:
            QMessageBox.warning(self, "Setup", "Passwords do not match.")
            return

        # Create admin user
        admin = AdminUser(
            username="admin",
            password_hash=hash_password(pwd),
        )
        self.session.add(admin)
        self.session.commit()

        # Mark progress complete and close
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

        self.accept()  # Close dialog with Accepted

    # -----------------------------------------
    # Login for existing admin
    # -----------------------------------------
    def _build_login_group(self) -> QGroupBox:
        group = QGroupBox("Admin Login")

        layout = QVBoxLayout()

        info = QLabel("Please enter the admin password to open RegisTree.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.login_password_edit = QLineEdit()
        self.login_password_edit.setEchoMode(QLineEdit.Password)
        self.login_password_edit.setPlaceholderText("Admin password")
        layout.addWidget(self.login_password_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        login_btn = QPushButton("Login")
        login_btn.clicked.connect(self._handle_login)
        btn_layout.addWidget(login_btn)
        layout.addLayout(btn_layout)

        group.setLayout(layout)
        return group

    def _handle_login(self):
        pwd = self.login_password_edit.text().strip()

        admin = self.session.query(AdminUser).first()
        if admin is None:
            QMessageBox.critical(
                self,
                "Login",
                "No admin user was found in the database.\n"
                "Please restart and run first-time setup.",
            )
            return

        if not verify_password(pwd, admin.password_hash):
            QMessageBox.warning(self, "Login", "Incorrect password.")
            return

        # Mark progress complete and close
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

        self.accept()
