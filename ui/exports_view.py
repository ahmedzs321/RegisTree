from PySide6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QMessageBox
from datetime import date
from pathlib import Path

class ExportsView(QWidget):
    def __init__(self, session):
        super().__init__()
        self.session = session

        layout = QVBoxLayout()

        export_button = QPushButton("Export Today")
        export_button.clicked.connect(self.export_today)
        layout.addWidget(export_button)

        self.setLayout(layout)

    def export_today(self):
        today = date.today()
        out_dir = Path("exports")
        out_dir.mkdir(exist_ok=True)

        # Placeholder export until we wire real data:
        file = out_dir / f"export_{today}.txt"
        file.write_text(
            f"RegisTree export for {today}\n"
            "(Placeholder file — models and real data coming next.)",
            encoding="utf-8"
        )

        QMessageBox.information(self, "Export", f"Export saved to {file}")
