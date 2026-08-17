"""Application styles."""


def _build_theme(p: dict[str, str]) -> str:
    return r"""
QWidget {{
    font-size: 10pt;
    color: {text};
}}
QMainWindow, QWidget#appRoot {{ background: {window}; }}
QScrollArea#overviewScroll {{ background: {window}; border: none; }}
QScrollArea#overviewScroll > QWidget > QWidget {{ background: {window}; }}
QWidget#overviewContent {{ background: {window}; }}
QFrame#topBar {{ background: {panel}; border-bottom: 1px solid {border}; }}
QFrame#sidebar {{ background: {sidebar}; border-right: 1px solid {border}; }}
QFrame#formatStrip {{ background: {strip}; border-bottom: 1px solid {border}; }}
QLabel#brandTitle {{ font-size: 13pt; font-weight: 700; color: {strong}; }}
QLabel#fileState {{ color: {muted}; font-size: 9pt; }}
QLabel#sidebarLabel {{ color: {muted}; font-size: 8pt; font-weight: 700; }}
QLabel#pageTitle {{ font-size: 17pt; font-weight: 700; color: {strong}; }}
QLabel#dialogTitle {{ font-size: 15pt; font-weight: 700; color: {strong}; }}
QLabel#pageSubtitle, QLabel#muted, QLabel#mutedText {{ color: {muted}; }}
QLabel#sectionTitle {{ font-size: 10.5pt; font-weight: 700; color: {strong}; }}
QLabel#sourceFormatPill {{ color: {text}; padding: 2px 4px; font-weight: 600; }}
QLabel#contextLabel {{ color: {muted}; font-size: 9pt; font-weight: 600; }}
QLabel#statusGood, QLabel#integrityGood {{ color: {good}; font-weight: 600; }}
QLabel#integrityIdle {{ color: {muted}; }}
QLabel#warningText {{ color: {warning}; }}

QLabel#stateBadge {{
    color: {muted};
    border: 1px solid {borderStrong};
    border-radius: 4px;
    padding: 3px 7px;
    font-size: 8.5pt;
    font-weight: 600;
}}
QLabel#stateBadge[state="ready"] {{ color: {good}; border-color: {goodBorder}; }}
QLabel#stateBadge[state="edited"] {{ color: {warning}; border-color: {warningBorder}; }}
QLabel#stateBadge[state="readonly"] {{ color: {warning}; border-color: {warningBorder}; }}

QComboBox#formatCombo {{
    background: {field};
    color: {text};
    border: 1px solid {accent};
    border-radius: 4px;
    padding: 5px 8px;
    font-weight: 600;
}}
QComboBox#formatCombo:disabled {{ color: {disabledText}; border-color: {border}; background: {disabled}; }}

QFrame#conversionNotice {{ background: {warningBg}; border-bottom: 1px solid {warningBorder}; }}
QLabel#conversionNoticeText {{ color: {warning}; font-size: 9pt; font-weight: 600; }}

QListWidget#navigation {{ background: transparent; border: 0; outline: none; padding: 0 5px; }}
QListWidget#navigation::item {{
    color: {navText};
    padding: 7px 9px;
    margin: 1px 0;
    border-radius: 4px;
}}
QListWidget#navigation::item:hover {{ background: {hover}; color: {strong}; }}
QListWidget#navigation::item:selected {{ background: {selected}; color: {selectedText}; font-weight: 600; }}
QListWidget#navigation::item:disabled {{ color: {disabledText}; }}
QListWidget#navigation:focus {{ border: 1px solid {accent}; border-radius: 4px; }}

QGroupBox, QFrame#card {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 4px;
}}
QGroupBox {{
    font-weight: 600;
    margin-top: 10px;
    padding: 12px 11px 10px 11px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 9px; padding: 0 4px; color: {strong}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {field};
    color: {text};
    border: 1px solid {fieldBorder};
    border-radius: 4px;
    padding: 5px 7px;
    min-height: 18px;
    selection-background-color: {accent};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {borderStrong}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {focus}; }}
QComboBox::drop-down {{
    width: 28px;
    border: 0;
    border-left: 1px solid {fieldBorder};
    background: {button};
}}
QComboBox QAbstractItemView {{
    background: {panel};
    color: {text};
    border: 1px solid {borderStrong};
    selection-background-color: {selected};
    selection-color: {selectedText};
    outline: 0;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 20px;
    background: {button};
    border-left: 1px solid {fieldBorder};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ border-bottom: 1px solid {fieldBorder}; }}
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; }}

QPushButton {{
    background: {button};
    color: {text};
    border: 1px solid {borderStrong};
    border-radius: 4px;
    padding: 6px 11px;
    min-height: 20px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {pressed}; }}
QPushButton:disabled {{ color: {disabledText}; background: {disabled}; border-color: {border}; }}
QPushButton#primary {{ background: {accent}; color: {accentText}; border-color: {accent}; }}
QPushButton#primary:hover {{ background: {accentHover}; border-color: {accentHover}; }}
QPushButton#ghostButton {{ background: transparent; color: {muted}; }}
QPushButton#sectionToggle {{ text-align: left; background: transparent; border-color: {border}; }}
QPushButton#sectionToggle:checked {{ background: {hover}; }}

QProgressBar {{
    background: {field};
    color: {text};
    border: 1px solid {border};
    border-radius: 3px;
    min-height: 17px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {accent}; }}

QTableWidget {{
    background: {table};
    alternate-background-color: {tableAlt};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    gridline-color: transparent;
    selection-background-color: {selected};
    selection-color: {selectedText};
}}
QHeaderView {{ background: {table}; }}
QHeaderView::section {{
    background: {header};
    color: {muted};
    padding: 6px 7px;
    border: 0;
    border-bottom: 1px solid {border};
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {header}; border: 0; }}
QTableWidget::item:focus {{ border: 1px solid {focus}; }}

QTabWidget#workspace::pane {{ border: 0; background: {window}; }}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 4px; background: {panel}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {muted}; padding: 7px 12px; border-bottom: 2px solid transparent; }}
QTabBar::tab:hover {{ color: {strong}; }}
QTabBar::tab:selected {{ color: {selectedText}; border-bottom: 2px solid {accent}; font-weight: 600; }}

QMenuBar {{ background: {panel}; color: {text}; border-bottom: 1px solid {border}; }}
QMenuBar::item:selected {{ background: {hover}; }}
QMenu {{ background: {panel}; color: {text}; border: 1px solid {borderStrong}; }}
QMenu::item {{ padding: 5px 24px 5px 10px; }}
QMenu::item:selected {{ background: {selected}; color: {selectedText}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 5px 8px; }}
QStatusBar {{ background: {sidebar}; color: {muted}; border-top: 1px solid {border}; }}
QToolTip {{ background: {tooltip}; color: {tooltipText}; border: 1px solid {borderStrong}; padding: 4px; }}
QMessageBox {{ background: {panel}; }}
QSplitter::handle {{ background: transparent; width: 5px; }}
QSplitter::handle:hover {{ background: {borderStrong}; }}
QPushButton:focus {{ border: 1px solid {focus}; }}
""".format_map(p)


DARK = _build_theme({
    "window": "#101419",
    "panel": "#171c22",
    "sidebar": "#14191f",
    "strip": "#121820",
    "table": "#11171d",
    "tableAlt": "#151b22",
    "header": "#1b222a",
    "field": "#10161c",
    "button": "#20272f",
    "hover": "#27313b",
    "pressed": "#1a2128",
    "disabled": "#181d23",
    "border": "#2b343e",
    "borderStrong": "#465463",
    "fieldBorder": "#56697a",
    "text": "#e4e8ed",
    "strong": "#f4f6f8",
    "muted": "#9aa6b2",
    "navText": "#adb7c1",
    "disabledText": "#626d78",
    "accent": "#3b78bd",
    "accentHover": "#4786cc",
    "accentText": "#ffffff",
    "focus": "#78aef0",
    "selected": "#233d5b",
    "selectedText": "#d9eaff",
    "good": "#75c7a2",
    "goodBorder": "#315642",
    "warning": "#dfb769",
    "warningBg": "#251f15",
    "warningBorder": "#5a4827",
    "tooltip": "#20262d",
    "tooltipText": "#f5f6f7",
})


LIGHT = _build_theme({
    "window": "#f4f5f7",
    "panel": "#ffffff",
    "sidebar": "#f8f9fb",
    "strip": "#f2f5f8",
    "table": "#ffffff",
    "tableAlt": "#f8f9fb",
    "header": "#f0f2f5",
    "field": "#ffffff",
    "button": "#eef1f4",
    "hover": "#e5eaf0",
    "pressed": "#dce2e8",
    "disabled": "#f2f3f5",
    "border": "#d8dee5",
    "borderStrong": "#aeb8c3",
    "fieldBorder": "#7f8b98",
    "text": "#242b33",
    "strong": "#161c23",
    "muted": "#667382",
    "navText": "#4f5c69",
    "disabledText": "#a4adb7",
    "accent": "#2f70b7",
    "accentHover": "#397cc4",
    "accentText": "#ffffff",
    "focus": "#1767bd",
    "selected": "#dceafb",
    "selectedText": "#174f8f",
    "good": "#267654",
    "goodBorder": "#acd0bd",
    "warning": "#875c16",
    "warningBg": "#fff8e9",
    "warningBorder": "#d8bd80",
    "tooltip": "#26323d",
    "tooltipText": "#ffffff",
})
