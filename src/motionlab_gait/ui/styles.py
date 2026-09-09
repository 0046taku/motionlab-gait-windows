APP_STYLESHEET = """
QMainWindow, QWidget {
    background: #F4F7F9;
    color: #17242D;
    font-family: "Yu Gothic", "Meiryo", "Segoe UI";
    font-size: 13px;
}
QFrame#sidebar, QFrame#contentCard {
    background: #FFFFFF;
    border: 1px solid #DDE5EA;
    border-radius: 10px;
}
QFrame#resultCard {
    background: #EFF8F5;
    border: 1px solid #C8E4DC;
    border-radius: 8px;
}
QLabel#qualityGrade {
    color: #176B63;
    font-size: 24px;
    font-weight: 700;
}
QLabel#warningBox {
    background: #FFF7E8;
    color: #704C13;
    border: 1px solid #E8D09B;
    border-radius: 7px;
    padding: 9px;
}
QLabel#hypothesisBox {
    background: #EEF3FA;
    color: #284B70;
    border: 1px solid #C8D7E8;
    border-radius: 7px;
    padding: 9px;
}
QLabel#appTitle {
    color: #123B4A;
    font-size: 22px;
    font-weight: 700;
}
QLabel#sectionTitle {
    color: #123B4A;
    font-size: 17px;
    font-weight: 700;
}
QLabel#muted {
    color: #647985;
}
QListWidget {
    background: #FFFFFF;
    border: 1px solid #DDE5EA;
    border-radius: 7px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    border-radius: 5px;
    padding: 9px 8px;
}
QListWidget::item:selected {
    background: #DDF4ED;
    color: #123B4A;
}
QPushButton {
    background: #FFFFFF;
    border: 1px solid #B9C7CE;
    border-radius: 7px;
    min-height: 34px;
    padding: 0 14px;
}
QPushButton:hover { background: #EDF5F6; }
QPushButton:pressed { background: #DCE9EB; }
QPushButton:disabled { color: #98A7AE; background: #EEF1F3; }
QPushButton#primaryButton {
    background: #176B63;
    border: 1px solid #176B63;
    color: #FFFFFF;
    font-weight: 600;
}
QPushButton#primaryButton:hover { background: #105A54; }
QLineEdit, QTextEdit {
    background: #FFFFFF;
    border: 1px solid #B9C7CE;
    border-radius: 6px;
    padding: 7px;
}
QSlider::groove:horizontal {
    height: 5px;
    background: #CFDADF;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #176B63;
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
}
QProgressBar {
    border: 1px solid #D0DADE;
    border-radius: 5px;
    text-align: center;
    background: #EEF2F4;
}
QProgressBar::chunk { background: #2A968A; border-radius: 4px; }
"""
