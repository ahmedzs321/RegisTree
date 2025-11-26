# RegisTree main window with security + tabs

import sys
import os

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QDialog

from data.db import init_db, SessionLocal
from data.models import AdminUser
from data.security import hash_password, verify_password

from ui.students_view import StudentsView
from ui.classes_view import ClassesView
from ui.attendance_view import AttendanceView
from ui.exports_view import ExportsView
from ui.dashboard_view import DashboardView
from ui.auth_dialogs import SetupAdminDialog, LoginDialog


class MainWindow(QMainWindow):
    def __init__(self, session):
        super().__init__()
        self.setWindowTitle("RegisTree")
        self.session = session

        self.tabs = QTabWidget()

        # Dashboard as first tab
        self.dashboard_view = DashboardView(self.session)
        self.tabs.addTab(self.dashboard_view, "Dashboard")

        # Other tabs
        self.tabs.addTab(StudentsView(self.session), "Students")
        self.tabs.addTab(ClassesView(self.session), "Classes")
        self.tabs.addTab(AttendanceView(self.session), "Attendance")
        self.tabs.addTab(ExportsView(self.session), "Exports")

        # When user switches tabs, refresh dashboard if selected
        self.tabs.currentChanged.connect(self.handle_tab_changed)

        self.setCentralWidget(self.tabs)

    def handle_tab_changed(self, index: int):
        # If Dashboard tab (index 0) is selected, refresh stats
        if index == 0 and self.dashboard_view is not None:
            self.dashboard_view.refresh_stats()

    def closeEvent(self, event):
        # Close DB session cleanly on window close
        self.session.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)

    # Initialize DB schema (creates tables if needed)
    init_db()

    # Create DB session
    session = SessionLocal()

    # ----- SECURITY START -----
    # Check if an admin user already exists
    admin = session.query(AdminUser).first()

    if admin is None:
        # No admin user yet → first-time setup
        setup_dialog = SetupAdminDialog()
        result = setup_dialog.exec()

        if result != QDialog.Accepted:
            # User cancelled setup, exit app
            sys.exit(0)

        password = setup_dialog.get_password()

        # Create the admin user
        admin = AdminUser(
            username="admin",
            password_hash=hash_password(password)
        )
        session.add(admin)
        session.commit()

    else:
        # Admin exists → require login
        login_dialog = LoginDialog(
            verify_func=verify_password,
            stored_hash=admin.password_hash
        )
        result = login_dialog.exec()

        if result != QDialog.Accepted:
            # Wrong password or user cancelled
            sys.exit(0)
    # ----- SECURITY END -----

    # Launch main app window
    win = MainWindow(session)
    win.resize(1100, 700)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
