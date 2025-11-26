from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
    QMessageBox,
)
from PySide6.QtCore import Qt


class SetupAdminDialog(QDialog):
    """
    First-time setup dialog to create an admin password.
    Username is fixed as 'admin' for now.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Admin Password")
        self._password = None

        layout = QVBoxLayout()

        form = QFormLayout()

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)

        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.Password)

        form.addRow("Admin Password:", self.password_edit)
        form.addRow("Confirm Password:", self.confirm_edit)

        layout.addLayout(form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.handle_accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)

        self.setLayout(layout)

    def handle_accept(self):
        pw = self.password_edit.text().strip()
        confirm = self.confirm_edit.text().strip()

        if not pw:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Password cannot be empty.",
            )
            return

        if pw != confirm:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Passwords do not match.",
            )
            return

        self._password = pw
        self.accept()

    def get_password(self) -> str:
        return self._password or ""


class LoginDialog(QDialog):
    """
    Login dialog for existing admin.
    We only ask for the password; username is assumed 'admin' for now.
    """

    def __init__(self, verify_func, stored_hash: str, parent=None):
        """
        verify_func: a function like verify_password(password, stored_hash) -> bool
        stored_hash: bcrypt hash string from the database.
        """
        super().__init__(parent)
        self.setWindowTitle("Admin Login")

        self.verify_func = verify_func
        self.stored_hash = stored_hash

        layout = QVBoxLayout()
        form = QFormLayout()

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)

        form.addRow("Admin Password:", self.password_edit)
        layout.addLayout(form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.handle_accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)

        self.setLayout(layout)

    def handle_accept(self):
        pw = self.password_edit.text().strip()

        if not pw:
            QMessageBox.warning(
                self,
                "Login Error",
                "Password cannot be empty.",
            )
            return

        if not self.verify_func(pw, self.stored_hash):
            QMessageBox.warning(
                self,
                "Login Error",
                "Incorrect password.",
            )
            return

        # Password correct
        self.accept()

class ChangePasswordDialog(QDialog):
    """
    Dialog to change the admin password.
    Asks for current password, then new password + confirmation.
    Uses verify_func to verify the current password.
    """

    def __init__(self, verify_func, stored_hash: str, parent=None):
        """
        verify_func: function like verify_password(password, stored_hash) -> bool
        stored_hash: bcrypt hash string from the database.
        """
        super().__init__(parent)
        self.setWindowTitle("Change Admin Password")

        self.verify_func = verify_func
        self.stored_hash = stored_hash
        self._new_password = None

        layout = QVBoxLayout()
        form = QFormLayout()

        self.current_edit = QLineEdit()
        self.current_edit.setEchoMode(QLineEdit.Password)

        self.new_edit = QLineEdit()
        self.new_edit.setEchoMode(QLineEdit.Password)

        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.Password)

        form.addRow("Current Password:", self.current_edit)
        form.addRow("New Password:", self.new_edit)
        form.addRow("Confirm New Password:", self.confirm_edit)

        layout.addLayout(form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.handle_accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)

        self.setLayout(layout)

    def handle_accept(self):
        current = self.current_edit.text().strip()
        new_pw = self.new_edit.text().strip()
        confirm = self.confirm_edit.text().strip()

        if not current or not new_pw or not confirm:
            QMessageBox.warning(
                self,
                "Validation Error",
                "All fields are required.",
            )
            return

        # Verify current password
        if not self.verify_func(current, self.stored_hash):
            QMessageBox.warning(
                self,
                "Change Password",
                "Current password is incorrect.",
            )
            return

        if new_pw != confirm:
            QMessageBox.warning(
                self,
                "Change Password",
                "New passwords do not match.",
            )
            return

        if new_pw == current:
            QMessageBox.warning(
                self,
                "Change Password",
                "New password must be different from the current password.",
            )
            return

        self._new_password = new_pw
        self.accept()

    def get_new_password(self) -> str:
        return self._new_password or ""
