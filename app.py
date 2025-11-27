# RegisTree main window with security + tabs
import sys
import os
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QDialog

from data.db import init_db, SessionLocal
from data.models import AdminUser, Settings
from data.security import hash_password, verify_password

from ui.students_view import StudentsView
from ui.classes_view import ClassesView
from ui.attendance_view import AttendanceView
from ui.exports_view import ExportsView
from ui.dashboard_view import DashboardView
from ui.auth_dialogs import SetupAdminDialog, LoginDialog
from ui.settings_view import SettingsView


class MainWindow(QMainWindow):
    def __init__(self, session, settings):
        super().__init__()
        self.setWindowTitle("RegisTree")
        self.session = session
        self.settings = settings
        self.tabs = QTabWidget()

        # Tab instances
        self.dashboard_view = DashboardView(self.session, self.settings)
        self.students_view = StudentsView(self.session, self.settings)
        self.classes_view = ClassesView(self.session)
        self.attendance_view = AttendanceView(self.session, self.settings)
        self.exports_view = ExportsView(self.session, self.settings)
        self.settings_view = SettingsView(self.session, self.settings, self.students_view)

        self.tabs.addTab(self.dashboard_view, "Dashboard")
        self.tabs.addTab(self.students_view, "Students")
        self.tabs.addTab(self.classes_view, "Classes")
        self.tabs.addTab(self.attendance_view, "Attendance")
        self.tabs.addTab(self.exports_view, "Exports")
        self.tabs.addTab(self.settings_view, "Settings")

        # When user switches tabs, refresh dashboard if selected
        self.tabs.currentChanged.connect(self.handle_tab_changed)

        self.setCentralWidget(self.tabs)

    def handle_tab_changed(self, index: int):
        widget = self.tabs.widget(index)

        if widget is self.dashboard_view:
            self.dashboard_view.refresh_stats()

        if widget is self.attendance_view:
            # Refresh class list every time we enter the Attendance tab
            self.attendance_view.load_classes()
            # Auto-load roster silently (no warnings)
            self.attendance_view.load_roster(show_warnings=False)

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

    # Load or create the global Settings row
    settings = session.query(Settings).first()
    if settings is None:
        default_statuses = ["Present", "Absent", "Tardy", "Excused"]
        settings = Settings(
            school_name="",
            academic_year="",
            attendance_statuses_json=json.dumps(default_statuses),
            export_base_dir=str(Path("exports").resolve()),
            attendance_auto_save=False,
            starting_grade="K",
            graduating_grade="12th",
        )
        session.add(settings)
        session.commit()

    # Launch main app window
    win = MainWindow(session, settings)
    win.resize(1100, 700)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
