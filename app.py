# RegisTree main window with 4 tabs (placeholders for now)

import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget
from data.db import init_db, SessionLocal
from ui.students_view import StudentsView
from ui.classes_view import ClassesView
from ui.attendance_view import AttendanceView
from ui.exports_view import ExportsView

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RegisTree")
        self.session = SessionLocal()

        tabs = QTabWidget()
        tabs.addTab(StudentsView(self.session), "Students")
        tabs.addTab(ClassesView(self.session), "Classes")
        tabs.addTab(AttendanceView(self.session), "Attendance")
        tabs.addTab(ExportsView(self.session), "Exports")

        self.setCentralWidget(tabs)

    def closeEvent(self, event):
        # Close DB session cleanly on window close
        self.session.close()
        super().closeEvent(event)

if __name__ == "__main__":
    # Create the SQLite DB file (registree.db) on first run
    init_db()

    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1100, 700)
    win.show()
    sys.exit(app.exec())
