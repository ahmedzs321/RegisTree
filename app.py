# RegisTree main window with security + tabs
import sys
import json
import traceback
from PySide6.QtGui import QIcon

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QDialog,
    QMessageBox,
)

from data.db import init_db, SessionLocal
from data.models import Settings  # AdminUser no longer needed here

from ui.students_view import StudentsView
from ui.classes_view import ClassesView
from ui.attendance_view import AttendanceView
from ui.exports_view import ExportsView
from ui.dashboard_view import DashboardView
from ui.settings_view import SettingsView
from ui.teachers_view import TeachersView
from ui.undo_manager import UndoManager
from ui.calendar_view import CalendarView
from ui.teacher_tracker_view import TeacherTrackerView
from ui.startup_dialog import StartupDialog  # <-- startup dialog

# 🔹 NEW: central paths (handles frozen / non-frozen cases)
from data.paths import ICON_PATH, LOGS_DIR, EXPORTS_DIR

# ----------------------------------------------------------
# Application version
# ----------------------------------------------------------
__version__ = "0.1.0-beta.1"


# ----------------------------------------------------------
# Global unhandled-exception logger for bug reports
# ----------------------------------------------------------
def log_unhandled_exception(exctype, value, tb):
    """
    Global hook to log unhandled exceptions to logs/last_traceback.txt.

    This is used by the 'Report a Bug' button in Settings so the
    traceback can be attached to the email body.
    """
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOGS_DIR / "last_traceback.txt"

        with log_path.open("w", encoding="utf-8") as f:
            f.write("Unhandled exception in RegisTree:\n\n")
            traceback.print_exception(exctype, value, tb, file=f)

        # Also print to stderr (useful during development)
        traceback.print_exception(exctype, value, tb)
    except Exception:
        # As a last resort, don't let logging failure crash the app
        traceback.print_exception(exctype, value, tb)


# Install the hook so Python calls this whenever an exception bubbles
# all the way up and would normally crash the program.
sys.excepthook = log_unhandled_exception


# ----------------------------------------------------------
# Theme support (Light / Dark)
# ----------------------------------------------------------
DARK_STYLESHEET = """
QWidget {
    background-color: #202124;
    color: #f1f3f4;
}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDateEdit,
QTableView, QTableWidget {
    background-color: #303134;
    color: #f1f3f4;
    border: 1px solid #5f6368;
}
QHeaderView::section {
    background-color: #303134;
    color: #f1f3f4;
}
QPushButton {
    background-color: #3c4043;
    color: #f1f3f4;
    border: 1px solid #5f6368;
    padding: 4px 8px;
}
QPushButton:hover {
    background-color: #4a4f54;
}
QGroupBox {
    border: 1px solid #5f6368;
    margin-top: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
"""


def apply_theme(theme: str | None):
    """
    Apply the requested theme ("Light" or "Dark") to the whole application.
    """
    app = QApplication.instance()
    if app is None:
        return

    theme = (theme or "Light").strip()
    if theme.lower() == "dark":
        app.setStyleSheet(DARK_STYLESHEET)
    else:
        # Reset to default Qt style
        app.setStyleSheet("")


class MainWindow(QMainWindow):
    def __init__(self, session, settings, version: str):
        super().__init__()
        # 🔹 Use ICON_PATH from data.paths
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setWindowTitle(f"RegisTree {version}")
        self.session = session
        self.settings = settings
        self.tabs = QTabWidget()

        # NEW: one global undo manager
        self.undo_manager = UndoManager()

        # Tab instances
        self.dashboard_view = DashboardView(self.session, self.settings)
        self.students_view = StudentsView(self.session, self.settings, self.undo_manager)
        self.teachers_view = TeachersView(self.session, self.settings, self.undo_manager)
        self.teacher_tracker_view = TeacherTrackerView(self.session, self.settings)
        self.classes_view = ClassesView(self.session, self.undo_manager)
        self.attendance_view = AttendanceView(self.session, self.settings)
        self.calendar_view = CalendarView(self.session, self.settings, self.attendance_view)
        self.exports_view = ExportsView(self.session, self.settings)
        # Pass apply_theme so SettingsView can switch theme live
        self.settings_view = SettingsView(
            self.session,
            self.settings,
            self.students_view,
            apply_theme_func=apply_theme,
        )

        self.tabs.addTab(self.dashboard_view, "Dashboard")
        self.tabs.addTab(self.students_view, "Students")
        self.tabs.addTab(self.teachers_view, "Teachers")
        self.tabs.addTab(self.teacher_tracker_view, "Teacher Tracker")
        self.tabs.addTab(self.classes_view, "Classes")
        self.tabs.addTab(self.attendance_view, "Attendance")
        self.tabs.addTab(self.calendar_view, "Calendar")
        self.tabs.addTab(self.exports_view, "Exports")
        self.tabs.addTab(self.settings_view, "Settings")

        # When user switches tabs, refresh dashboard if selected
        self.tabs.currentChanged.connect(self.handle_tab_changed)

        self.setCentralWidget(self.tabs)

        # --------------------------------------------------------------
        # Edit → Undo / Redo menu
        # --------------------------------------------------------------
        menubar = self.menuBar()
        edit_menu = menubar.addMenu("&Edit")

        self.undo_action = edit_menu.addAction("Undo")
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.triggered.connect(self.handle_undo)

        self.redo_action = edit_menu.addAction("Redo")
        self.redo_action.setShortcut("Ctrl+Y")
        self.redo_action.triggered.connect(self.handle_redo)

    # ----------------------------------------------------------
    # Tab change behaviour
    # ----------------------------------------------------------
    def handle_tab_changed(self, index: int):
        widget = self.tabs.widget(index)

        if widget is self.dashboard_view:
            self.dashboard_view.refresh_stats()

        if widget is self.attendance_view:
            # Refresh class list every time we enter the Attendance tab
            self.attendance_view.load_classes()
            # Auto-load roster silently (no warnings)
            self.attendance_view.load_roster(show_warnings=False)

        if widget is self.teacher_tracker_view:
            # Auto-load teacher list silently (no warnings)
            self.teacher_tracker_view.load_teachers_for_date(show_warnings=False)

    # ----------------------------------------------------------
    # Undo / Redo handlers
    # ----------------------------------------------------------
    def handle_undo(self):
        if not self.undo_manager.undo():
            QMessageBox.information(self, "Undo", "Nothing to undo.")

    def handle_redo(self):
        if not self.undo_manager.redo():
            QMessageBox.information(self, "Redo", "Nothing to redo.")

    # ----------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------
    def closeEvent(self, event):
        # Close DB session cleanly on window close
        self.session.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)

    # 🔹 Global application icon uses ICON_PATH as well
    app.setWindowIcon(QIcon(str(ICON_PATH)))

    # Initialize DB schema (creates tables if needed)
    init_db()

    # Create DB session
    session = SessionLocal()

    # ----- STARTUP + SECURITY (combined splash + setup/login) -----
    startup_dialog = StartupDialog(session, version=__version__)
    result = startup_dialog.exec()
    if result != QDialog.Accepted:
        # User cancelled or closed the startup window
        sys.exit(0)
    # ----- END STARTUP + SECURITY -----

    # Load or create the global Settings row
    settings = session.query(Settings).first()
    if settings is None:
        default_statuses = ["Present", "Absent", "Tardy", "Excused", "No School"]
        settings = Settings(
            school_name="",
            academic_year="",
            attendance_statuses_json=json.dumps(default_statuses),
            # 🔹 Default export dir uses EXPORTS_DIR from data.paths
            export_base_dir=str(EXPORTS_DIR),
            attendance_auto_save=False,
            starting_grade="K",
            graduating_grade="12th",
        )
        session.add(settings)
        session.commit()

    # Apply theme from settings at startup
    apply_theme(getattr(settings, "theme", "Light"))

    # Launch main app window
    win = MainWindow(session, settings, __version__)
    win.resize(1100, 700)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
