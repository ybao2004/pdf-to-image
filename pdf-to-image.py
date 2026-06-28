"""
Chuyển đổi PDF sang ảnh
Tác giả : @ybao
"""

# ======================================================================
# IMPORTS
# ======================================================================
import os, sys, json, time, zipfile, platform, subprocess, queue, threading, io, psutil, multiprocessing
from datetime import datetime
from pathlib import Path
from threading import Thread

import fitz
from PIL import Image, ImageDraw, ImageFont

from PyQt6.QtCore import (
    Qt, QThread, QObject, QRunnable, QThreadPool,
    pyqtSignal, pyqtSlot,
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel,
    QSize, QRect, QRectF, QPoint, QPointF, QTimer, QPropertyAnimation,
    QEasingCurve, QVariantAnimation, QAbstractAnimation, QSharedMemory
)
from PyQt6.QtGui import (
    QDragEnterEvent, QDropEvent, QPixmap, QImage,
    QPainter, QColor, QFont, QPen, QBrush, QCursor, QAction,
    QFontMetrics, QIntValidator, QLinearGradient, QPainterPath
)

import argparse
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QSystemTrayIcon
import concurrent.futures
import threading
from threading import Lock
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QSplitter,
    QLabel, QPushButton, QLineEdit, QComboBox, QSlider,
    QCheckBox, QProgressBar, QTextEdit,
    QScrollArea, QFrame, QFileDialog, QMessageBox,
    QMenu, QSizePolicy, QStackedWidget,
    QTableView, QHeaderView, QAbstractItemView,
    QStyledItemDelegate, QStyleOptionViewItem,
    QTabWidget, QDialog, QDialogButtonBox,
    QToolBar, QStatusBar, QToolButton, QSpinBox,
    QListWidget, QListWidgetItem, QInputDialog, QSplashScreen, QRadioButton
)

import ctypes
import winreg

def set_autostart(enable: bool):
    try:
        exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
        if enable:
            cmd = f'"{exe_path}" --action background'
            winreg.SetValueEx(key, "PDFtoImageService", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, "PDFtoImageService")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass

def get_os_full_version() -> str:
    import platform
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        product_name = winreg.QueryValueEx(key, "ProductName")[0]
        # Sửa lỗi Windows 11 hiển thị là Windows 10
        build_str = platform.version().split('.')[2] if '.' in platform.version() else winreg.QueryValueEx(key, "CurrentBuild")[0]
        if int(build_str) >= 22000 and "Windows 10" in product_name:
            product_name = product_name.replace("Windows 10", "Windows 11")
        try:
            display_ver = winreg.QueryValueEx(key, "DisplayVersion")[0]
        except:
            display_ver = winreg.QueryValueEx(key, "ReleaseId")[0]
        current_build = winreg.QueryValueEx(key, "CurrentBuild")[0]
        try:
            ubr = winreg.QueryValueEx(key, "UBR")[0]
            build_info = f"{current_build}.{ubr}"
        except:
            build_info = current_build
        winreg.CloseKey(key)
        return f"{product_name}, {display_ver}, {build_info}"
    except Exception:
        return f"{platform.system()} {platform.release()} ({platform.version()})"

def is_autostart_enabled() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, "PDFtoImageService")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False

def set_titlebar_theme(hwnd, dark: bool):
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        value = ctypes.c_int(1 if dark else 0)
        set_window_attribute(int(hwnd), DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


# ======================================================================
# CONSTANTS
# ======================================================================
APP_NAME    = "Chuyển đổi PDF sang ảnh"
APP_VERSION = "0.0.10"
UPDATE_ANY_DIFFERENT_VERSION = True  # Nếu True, cập nhật nếu phiên bản khác hiện tại; Nếu False, chỉ cập nhật nếu phiên bản lớn hơn.
UPDATE_CHECK_INTERVAL_MINUTES = 60   # Thời gian (phút) giữa mỗi lần kiểm tra ngầm phiên bản mới
APP_AUTHOR  = "@ybao"
CONFIG_PATH = Path.home() / "pdf_img_config.json"

FORMATS     = ["PNG", "JPG", "WebP", "TIFF"]
DPI_OPTIONS = [
    ("72 — Màn hình",  72),
    ("96 — Office",    96),
    ("150 — Web",     150),
    ("300 — In ấn",   300),
    ("600 — Archive", 600),
]
SIZE_LIMITS = [
    ("Không giới hạn", 0),
    ("100 KB", 100),
    ("250 KB", 250),
    ("500 KB", 500),
    ("1 MB",  1024),
    ("2 MB",  2048),
    ("3 MB",  3072),
    ("5 MB",  5120),
    ("10 MB", 10240),
]

# Queue column indices
COL_NAME   = 0
COL_STATUS = 1
COL_PROG   = 2
COL_COUNT  = 3

STATUS_PENDING    = "Chờ"
STATUS_PROCESSING = "Đang xử lý"
STATUS_DONE       = "Xong"
STATUS_ERROR      = "Lỗi"
STATUS_CANCELLED  = "Huỷ"

THUMB_W, THUMB_H = 132, 176

DEFAULT_CFG = {
    "theme":        "light", # light, dark
    "format":       "PNG",
    "color_mode":   "color",
    "dpi":          300,
    "quality":      100,
    "size_limit":   0,
    "output_path":  "",
    "watermark":    "",
    "watermark_on": False,
    "zip_output":   False,
    "auto_open":    False,
    "show_time":    True,
    "name_pattern": "{pdf} - trang {page:01d}",
    "history":      [],
    "win_w":        1300,
    "win_h":        800,
    "splitter":     [300, 1000],
    "performance":  1,
    "cm_format":    "PNG",
    "cm_color_mode":"color",
    "cm_dpi":       300,
    "cm_quality":   100,
    "smart_color":  True,
    "update_status":        "unknown",
    "update_latest_version":"",
    "update_url":           "",
    "update_published_at": "",
    "update_release_notes":"",
}


# ======================================================================
# QSS
# ======================================================================
def build_qss(dark: bool) -> str:
    if dark:
        c = dict(
            bg="#0f1117", bg2="#161922", bg3="#1c2030",
            border="#252a38", border2="#2e3450",
            fg="#e4e6eb", fg2="#9ca3b0", fg3="#4a5268",
            accent="#3b7fef", accent_h="#5a9af5", accent_fg="#ffffff",
            success="#2dbe7a", error="#f06060", warn="#f5a623", info="#60b0f5",
            input_bg="#1a1f2e", sel_bg="#1e3060",
            scroll="#252a38", scroll_h="#3b4060",
            drop_bg="#12151e", drop_bd="#2e3450", drop_act="#1a2644",
            sep="#1e2438", tag_run_fg="#60b0f5", tag_run_bg="#0d1e3a",
            tag_done_fg="#2dbe7a", tag_done_bg="#0e2a1a",
            tag_err_fg="#f06060", tag_err_bg="#2a0e0e",
            tag_wait_fg="#4a5268", tag_wait_bg="#1c2030",
            tag_cancel_fg="#f5a623", tag_cancel_bg="#2a1e0a",
            tb_bg="#161922", tb_border="#252a38",
            hdr_bg="#161922",
        )
    else:
        c = dict(
            bg="#f0f2f7", bg2="#ffffff", bg3="#f7f8fc",
            border="#e2e5ed", border2="#cbd0dc",
            fg="#111827", fg2="#4a5568", fg3="#9aa3b5",
            accent="#2563eb", accent_h="#1d4ed8", accent_fg="#ffffff",
            success="#059669", error="#dc2626", warn="#d97706", info="#2563eb",
            input_bg="#f3f5f9", sel_bg="#dbeafe",
            scroll="#d1d5db", scroll_h="#9ca3af",
            drop_bg="#f8faff", drop_bd="#c7d2fe", drop_act="#eff6ff",
            sep="#e5e7eb", tag_run_fg="#1e40af", tag_run_bg="#dbeafe",
            tag_done_fg="#065f46", tag_done_bg="#d1fae5",
            tag_err_fg="#991b1b", tag_err_bg="#fee2e2",
            tag_wait_fg="#6b7280", tag_wait_bg="#f3f4f6",
            tag_cancel_fg="#92400e", tag_cancel_bg="#fef3c7",
            tb_bg="#ffffff", tb_border="#e2e5ed",
            hdr_bg="#ffffff",
        )
    return f"""
QWidget {{
    background:{c['bg']}; color:{c['fg']};
    font-family:"Segoe UI","SF Pro Display",sans-serif;
    font-size:13px;
    selection-background-color:{c['sel_bg']};
    selection-color:{c['fg']};
}}
QMainWindow, QDialog {{ background:{c['bg']}; }}

/* ── Toolbar ── */
QToolBar {{
    background:{c['tb_bg']}; border:none;
    border-bottom:1px solid {c['tb_border']};
    spacing:2px; padding:4px 10px;
}}
QToolBar QToolButton {{
    background:transparent; color:{c['fg2']};
    border:none; border-radius:5px;
    padding:5px 10px; font-size:12px;
    min-width:0;
}}
QToolBar QToolButton:hover {{ background:{c['bg3']}; color:{c['fg']}; }}
QToolBar QToolButton:pressed {{ background:{c['border']}; }}
QToolBar QToolButton:disabled {{ color:{c['fg3']}; }}
QToolBar QToolButton#act_start {{
    background:{c['accent']}; color:{c['accent_fg']};
    font-weight:600; padding:5px 18px; border-radius:5px;
}}
QToolBar QToolButton#act_start:hover {{ background:{c['accent_h']}; }}
QToolBar QToolButton#act_start:disabled {{
    background:{c['border']}; color:{c['fg3']};
}}
QToolBar QToolButton#act_stop {{
    color:{c['error']}; border:1px solid {c['error']};
    border-radius:5px; padding:4px 12px;
}}
QToolBar QToolButton#act_stop:hover {{ background:{c['tag_err_bg']}; }}
QToolBar QToolButton#act_stop:disabled {{
    color:{c['fg3']}; border-color:{c['fg3']};
}}
QToolBar::separator {{ background:{c['border']}; width:1px; margin:4px 6px; }}

/* Inline toolbar widgets */
QToolBar QLabel {{ color:{c['fg3']}; font-size:11px; background:transparent; }}
QToolBar QComboBox {{
    background:{c['input_bg']}; color:{c['fg']};
    border:1px solid {c['border']}; border-radius:5px;
    padding:3px 6px; font-size:12px; min-width:80px;
}}
QToolBar QComboBox:focus {{ border-color:{c['accent']}; }}
QToolBar QComboBox::drop-down {{ border:none; width:18px; }}
QToolBar QComboBox::down-arrow {{
    border-left:4px solid transparent;
    border-right:4px solid transparent;
    border-top:5px solid {c['fg2']};
    margin-right:5px;
}}
QToolBar QSlider::groove:horizontal {{
    height:3px; background:{c['border']}; border-radius:2px;
}}
QToolBar QSlider::handle:horizontal {{
    background:{c['accent']}; width:12px; height:12px;
    margin:-5px 0; border-radius:6px;
}}
QToolBar QSlider::sub-page:horizontal {{
    background:{c['accent']}; border-radius:2px;
}}
QToolBar QLabel#qual_val {{
    color:{c['fg2']}; font-size:11px; min-width:28px;
}}

/* ── Sidebar ── */
#sidebar {{
    background:{c['bg2']};
    border-right:1px solid {c['border']};
}}

/* ── Drop zone ── */
QFrame#drop_zone {{
    background:{c['drop_bg']};
    border:1.5px dashed {c['drop_bd']};
    border-radius:8px;
}}
QFrame#drop_zone:hover {{
    border-color:{c['accent']}; background:{c['drop_act']};
}}

/* ── Queue table ── */
QTableView#queue_table {{
    background:{c['bg2']}; color:{c['fg']};
    border:none; outline:none;
    gridline-color:{c['sep']};
    selection-background-color:{c['sel_bg']};
    selection-color:{c['fg']};
    font-size:12px;
}}
QTableView#queue_table::item {{ padding:0 4px; border:none; }}
QTableView#queue_table::item:selected {{ background:{c['sel_bg']}; }}
QHeaderView::section {{
    background:{c['bg3']}; color:{c['fg3']};
    border:none; border-bottom:1px solid {c['border']};
    border-right:1px solid {c['border']};
    padding:4px 8px; font-size:11px; font-weight:600;
}}

/* ── Tab bar ── */
QTabWidget::pane {{ border:none; background:{c['bg']}; }}
QTabBar {{ background:{c['bg2']}; border-bottom:1px solid {c['border']}; }}
QTabBar::tab {{
    background:transparent; color:{c['fg3']};
    padding:7px 16px; border:none;
    border-bottom:2px solid transparent;
    font-size:12px; font-weight:500;
}}
QTabBar::tab:selected {{
    color:{c['accent']}; border-bottom-color:{c['accent']};
}}
QTabBar::tab:hover:!selected {{ color:{c['fg']}; background:{c['bg3']}; }}

/* ── Buttons ── */
QPushButton {{
    background:{c['bg3']}; color:{c['fg']};
    border:1px solid {c['border']};
    border-radius:5px; padding:5px 12px; font-size:12px;
}}
QPushButton:hover {{ background:{c['border']}; border-color:{c['border2']}; }}
QPushButton:pressed {{ background:{c['border2']}; }}
QPushButton:disabled {{ color:{c['fg3']}; background:{c['bg3']}; }}
QPushButton#btn_accent {{
    background:{c['accent']}; color:{c['accent_fg']};
    border:none; font-weight:600;
}}
QPushButton#btn_accent:hover {{ background:{c['accent_h']}; }}
QPushButton#btn_accent:disabled {{ background:{c['border']}; color:{c['fg3']}; }}
QPushButton#btn_danger {{
    color:{c['error']}; border-color:{c['error']};
}}
QPushButton#btn_danger:hover {{ background:{c['tag_err_bg']}; }}

/* ── Inputs ── */
QLineEdit, QSpinBox, QComboBox {{
    background:{c['input_bg']}; color:{c['fg']};
    border:1px solid {c['border']}; border-radius:5px;
    padding:4px 8px; font-size:12px;
    selection-background-color:{c['sel_bg']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color:{c['accent']};
}}
QComboBox::drop-down {{ border:none; width:20px; }}
QComboBox::down-arrow {{
    border-left:4px solid transparent;
    border-right:4px solid transparent;
    border-top:5px solid {c['fg2']};
    margin-right:6px;
}}
QComboBox QAbstractItemView {{
    background:{c['bg2']}; border:1px solid {c['border2']};
    border-radius:5px; selection-background-color:{c['sel_bg']};
    outline:none; padding:2px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width:14px; border:none; background:transparent;
}}

/* ── Slider (settings dialog) ── */
QSlider::groove:horizontal {{
    height:4px; background:{c['border']}; border-radius:2px;
}}
QSlider::handle:horizontal {{
    background:{c['accent']}; width:14px; height:14px;
    margin:-5px 0; border-radius:7px;
}}
QSlider::handle:horizontal:hover {{ background:{c['accent_h']}; }}
QSlider::sub-page:horizontal {{ background:{c['accent']}; border-radius:2px; }}

/* ── Checkbox & RadioButton ── */
QCheckBox, QRadioButton {{ spacing:6px; font-size:12px; color:{c['fg2']}; }}
QCheckBox::indicator {{
    width:15px; height:15px; border-radius:3px;
    border:1px solid {c['border2']}; background:{c['input_bg']};
}}
QCheckBox::indicator:checked {{
    background:{c['accent']}; border-color:{c['accent']};
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path fill='white' d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>");
}}
QCheckBox::indicator:hover {{ border-color:{c['accent']}; }}

QRadioButton::indicator {{
    width: 14px; height: 14px; border-radius: 7px;
    border: 1px solid {c['border2']}; background: {c['input_bg']};
}}
QRadioButton::indicator:checked {{
    background: {c['accent']}; border-color: {c['accent']};
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><circle cx='12' cy='12' r='6' fill='white'/></svg>");
}}
QRadioButton::indicator:hover {{ border-color: {c['accent']}; }}

/* ── Progress bar ── */
QProgressBar {{
    background:{c['border']}; border:none; border-radius:3px;
    text-align:center; color:transparent;
}}
QProgressBar::chunk {{ background:{c['accent']}; border-radius:3px; }}

/* ── Status bar ── */
QStatusBar {{
    background:{c['bg2']}; border-top:1px solid {c['border']};
    color:{c['fg2']}; font-size:11px; padding:0 8px;
}}
QStatusBar::item {{ border:none; }}

/* ── Scrollbar ── */
QScrollBar:vertical {{
    background:transparent; width:7px; margin:0;
}}
QScrollBar::handle:vertical {{
    background:{c['scroll']}; border-radius:3px; min-height:24px;
}}
QScrollBar::handle:vertical:hover {{ background:{c['scroll_h']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar:horizontal {{
    background:transparent; height:7px;
}}
QScrollBar::handle:horizontal {{
    background:{c['scroll']}; border-radius:3px; min-width:24px;
}}
QScrollBar::handle:horizontal:hover {{ background:{c['scroll_h']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}

/* ── Log ── */
QTextEdit#log_view {{
    background:{c['bg']}; color:{c['fg2']}; border:none;
    font-family:"Cascadia Code","Consolas","JetBrains Mono",monospace;
    font-size:12px; padding:10px 14px;
}}

/* ── Separator ── */
QFrame[frameShape="4"] {{
    border:none; border-top:1px solid {c['sep']}; max-height:1px;
}}

/* ── Thumbnail viewer ── */
QScrollArea#thumb_scroll {{
    background:{c['bg']}; border:none;
}}
#thumb_scroll > QWidget > QWidget {{ background:{c['bg']}; }}

/* ── Zoom overlay ── */
#zoom_overlay {{
    background:rgba(0,0,0,200);
}}

/* ── Settings dialog ── */
QDialog {{ background:{c['bg']}; }}
QGroupBox {{
    border:1px solid {c['border']}; border-radius:6px;
    margin-top:8px; padding:10px 10px 6px;
    font-weight:600; color:{c['fg2']};
}}
QGroupBox::title {{
    subcontrol-origin:margin; subcontrol-position:top left;
    padding:0 6px; left:10px; top:-1px;
}}

/* ── Tooltip ── */
QToolTip {{
    background:{c['bg2']}; color:{c['fg']};
    border:1px solid {c['border2']};
    border-radius:4px; padding:4px 8px; font-size:12px;
}}

/* ── Splitter ── */
QSplitter::handle {{ background:{c['border']}; width:1px; height:1px; }}

/* ── Section label ── */
QLabel#sec_lbl {{
    color:{c['fg3']}; font-size:10px; font-weight:700;
    letter-spacing:0.07em;
}}
"""


# ======================================================================
# DATA MODELS
# ======================================================================
class QueueItem:
    __slots__ = ("path","name","parent_dir","group_name","size_mb","pages","status","progress",
                 "error_msg","out_folder","elapsed", "excluded_pages")
    def __init__(self, path: str, group_name: str = None):
        self.path      = path
        self.name      = Path(path).name
        self.parent_dir = str(Path(path).parent)
        self.group_name = group_name
        self.size_mb   = round(os.path.getsize(path) / 1048576, 1) if os.path.isfile(path) else 0.0
        self.pages     = 0
        self.status    = STATUS_PENDING
        self.progress  = 0
        self.error_msg = ""
        self.out_folder = ""
        self.elapsed   = 0.0
        self.excluded_pages = set()


class QueueTableModel(QAbstractTableModel):
    """
    Virtual model cho QTableView — chỉ render rows hiển thị,
    không quan tâm số lượng.  Thread-safe update qua slot.
    """
    HEADERS = ["Tên file", "Trạng thái", "Tiến độ"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[QueueItem] = []

    # ── Qt overrides ──────────────────────────────────────────────────
    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def columnCount(self, parent=QModelIndex()):
        return COL_COUNT

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        col  = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_NAME:   return item.name
            if col == COL_STATUS: return item.status
            if col == COL_PROG:   return ""          # delegate vẽ bar
        if role == Qt.ItemDataRole.UserRole:
            return item
        if role == Qt.ItemDataRole.ToolTipRole and col == COL_NAME:
            return item.path
        return None

    # ── Data mutations ────────────────────────────────────────────────
    def add_items(self, items: list[QueueItem]):
        if not items:
            return
        r0 = len(self._items)
        self.beginInsertRows(QModelIndex(), r0, r0 + len(items) - 1)
        self._items.extend(items)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def update_row(self, idx: int):
        if 0 <= idx < len(self._items):
            self.dataChanged.emit(
                self.index(idx, 0), self.index(idx, COL_COUNT - 1)
            )

    def get_item(self, row: int) -> QueueItem | None:
        return self._items[row] if 0 <= row < len(self._items) else None

    def all_items(self) -> list[QueueItem]:
        return self._items

    def pending_items(self) -> list[tuple[int, QueueItem]]:
        return [
            (i, it) for i, it in enumerate(self._items)
            if it.status in (STATUS_PENDING, STATUS_ERROR, STATUS_CANCELLED, STATUS_PROCESSING)
        ]

    def remove_done(self):
        to_remove = [i for i, it in enumerate(self._items) if it.status == STATUS_DONE]
        for i in reversed(to_remove):
            self.beginRemoveRows(QModelIndex(), i, i)
            self._items.pop(i)
            self.endRemoveRows()

    def existing_paths(self) -> set[str]:
        return {it.path for it in self._items}


class QueueDelegate(QStyledItemDelegate):
    """Vẽ toàn bộ nội dung ô bằng QPainter — không tạo widget con."""
    ROW_H = 28

    def __init__(self, dark_fn, parent=None):
        super().__init__(parent)
        self._dark = dark_fn

    def sizeHint(self, option, index):
        return QSize(0, self.ROW_H)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        item: QueueItem | None = index.data(Qt.ItemDataRole.UserRole)
        if item is None:
            return

        dark = self._dark()
        r    = option.rect
        col  = index.column()
        sel  = bool(option.state & option.state.State_Selected)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Nền
        if sel:
            bg = "#1e3060" if dark else "#dbeafe"
        else:
            bg = "#161922" if dark else "#ffffff"
        painter.fillRect(r, QColor(bg))

        # Màu chữ chính
        fg  = "#e4e6eb" if dark else "#111827"
        fg2 = "#5a6278" if dark else "#9ca3af"

        pad = 8

        # ── Cột: Tên file ──
        if col == COL_NAME:
            painter.setFont(QFont("Segoe UI", 10))
            painter.setPen(QColor(fg))
            metrics = QFontMetrics(painter.font())
            txt = metrics.elidedText(item.name, Qt.TextElideMode.ElideMiddle, r.width() - pad * 2)
            painter.drawText(r.adjusted(pad, 0, -pad, 0),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, txt)

        # ── Cột: Trạng thái (badge) ──
        elif col == COL_STATUS:
            STATUS_COLORS = {
                STATUS_DONE:       ("#0e2a1a","#2dbe7a") if dark else ("#d1fae5","#065f46"),
                STATUS_PROCESSING: ("#0d1e3a","#60b0f5") if dark else ("#dbeafe","#1e40af"),
                STATUS_ERROR:      ("#2a0e0e","#f06060") if dark else ("#fee2e2","#991b1b"),
                STATUS_CANCELLED:  ("#2a1e0a","#f5a623") if dark else ("#fef3c7","#92400e"),
                STATUS_PENDING:    ("#1c2030","#4a5268") if dark else ("#f3f4f6","#6b7280"),
            }
            bbg, bfg = STATUS_COLORS.get(item.status, STATUS_COLORS[STATUS_PENDING])
            bw, bh = 76, 20
            bx = r.x() + (r.width() - bw) // 2
            by = r.y() + (r.height() - bh) // 2
            painter.setBrush(QBrush(QColor(bbg)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRect(bx, by, bw, bh), 4, 4)
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
            painter.setPen(QColor(bfg))
            painter.drawText(QRect(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, item.status)

        # ── Cột: Tiến độ (progress bar) ──
        elif col == COL_PROG:
            track_c = "#252a38" if dark else "#e2e5ed"
            fill_c  = "#3b7fef" if dark else "#2563eb"
            bh, by_off = 5, (self.ROW_H - 5) // 2
            bx = r.x() + pad
            bw = r.width() - pad * 2
            by = r.y() + by_off
            painter.setBrush(QBrush(QColor(track_c)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRect(bx, by, bw, bh), 2, 2)
            if item.progress > 0:
                fw = int(bw * item.progress / 100)
                painter.setBrush(QBrush(QColor(fill_c)))
                painter.drawRoundedRect(QRect(bx, by, fw, bh), 2, 2)
            # Phần trăm nếu đang xử lý
            if item.status == STATUS_PROCESSING and item.progress > 0:
                painter.setFont(QFont("Segoe UI", 7))
                painter.setPen(QColor(fg2))
                painter.drawText(
                    QRect(bx, by + 6, bw, 14),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{item.progress}%"
                )

        painter.restore()


# ======================================================================
class ThumbRendererThread(QThread):
    ready = pyqtSignal(int, QImage, str)
    ready_highres = pyqtSignal(int, QImage, str)
    error = pyqtSignal(int)

    def __init__(self, pdf_path: str, w: int, h: int, gray: bool = False, dpi: int = 72, quality: int = 100, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.w, self.h = w, h
        self.gray = gray
        self.dpi = dpi
        self.quality = quality
        self._pages_to_load = []
        self._highres_queue = []
        self._lock = threading.Lock()
        self._cancelled = False

    def add_pages(self, pages: list[int]):
        with self._lock:
            self._pages_to_load.extend(pages)

    def request_high_res(self, page_idx: int):
        with self._lock:
            if page_idx not in self._highres_queue:
                self._highres_queue.insert(0, page_idx) # Ưu tiên xử lý ngay lập tức

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            doc  = fitz.open(self.pdf_path)
        except Exception:
            return
            
        while not self._cancelled:
            page_idx = -1
            is_highres = False
            with self._lock:
                if self._highres_queue:
                    page_idx = self._highres_queue.pop(0)
                    is_highres = True
                elif self._pages_to_load:
                    page_idx = self._pages_to_load.pop(0)

            if page_idx == -1:
                time.sleep(0.02)
                continue

            try:
                page = doc.load_page(page_idx)
                
                if is_highres:
                    zoom = self.dpi / 72.0
                else:
                    zoom = 2.0 * min(self.w / page.rect.width, self.h / page.rect.height)
                    
                if self.gray:
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY, alpha=False)
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_Grayscale8).copy()
                else:
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                
                orig_w, orig_h = int(page.rect.width * zoom), int(page.rect.height * zoom)
                color_txt = "Trắng đen" if self.gray else "Màu (RGB)"
                
                if is_highres:
                    info = f"{orig_w}×{orig_h} · {self.dpi} DPI · {self.quality}% · {color_txt}"
                    self.ready_highres.emit(page_idx, qimg, info)
                else:
                    info = f"{orig_w}×{orig_h} · Bản xem trước"
                    self.ready.emit(page_idx, qimg, info)
            except Exception as e:
                if not is_highres:
                    self.error.emit(page_idx)
                    
            if not is_highres:
                time.sleep(0.005)
                
        doc.close()


# ======================================================================
# THUMBNAIL CARD
# ======================================================================
class ThumbCard(QWidget):
    single_click  = pyqtSignal(int)   # page_idx
    double_click  = pyqtSignal(int, QPixmap, str)

    def __init__(self, page_idx: int, dark_fn, excluded: bool = False, parent=None):
        super().__init__(parent)
        self.page_idx  = page_idx
        self._dark     = dark_fn
        self._excluded = excluded
        self._pixmap   = None
        self._info     = ""
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._emit_single)
        self._pending_click = False
        self.setFixedSize(THUMB_W + 8, THUMB_H + 30)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(f"Trang {page_idx + 1}\nDouble-click để phóng to")

    def set_pixmap(self, px: QPixmap, info: str = ""):
        self._pixmap = px
        self._info   = info
        self.update()

    def set_excluded(self, val: bool):
        if self._excluded != val:
            self._excluded = val
            self.update()

    def is_excluded(self) -> bool:
        return self._excluded

    def _emit_single(self):
        if self._pending_click:
            self._pending_click = False
            self.single_click.emit(self.page_idx)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self._click_timer.isActive():
                # double-click
                self._click_timer.stop()
                self._pending_click = False
                if self._pixmap:
                    self.double_click.emit(self.page_idx, self._pixmap, self._info)
            else:
                self._pending_click = True
                self._click_timer.start(220)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = self._dark()
        w, h = self.width(), self.height()

        card = QRect(2, 2, THUMB_W + 4, THUMB_H + 24)
        bd   = "#f06060" if self._excluded else ("#252a38" if dark else "#e2e5ed")
        bg   = "#1c2030" if dark else "#ffffff"

        painter.setBrush(QBrush(QColor(bg)))
        painter.setPen(QPen(QColor(bd), 2.0 if self._excluded else 0.7))
        painter.drawRoundedRect(card, 6, 6)

        img_r = QRect(4, 4, THUMB_W, THUMB_H)
        if self._pixmap:
            scaled = self._pixmap.scaled(
                THUMB_W, THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            ox = 4 + (THUMB_W - scaled.width())  // 2
            oy = 4 + (THUMB_H - scaled.height()) // 2
            
            painter.setOpacity(0.5 if self._excluded else 1.0)
            painter.setClipRect(img_r)
            painter.drawPixmap(ox, oy, scaled)
            painter.setClipping(False)
            painter.setOpacity(1.0)
            
            # Badge Overlay (Số trang góc dưới phải giống bản Web)
            badge_text = str(self.page_idx + 1)
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(badge_text)
            th = fm.height()
            bx = 4 + THUMB_W - tw - 12
            by = 4 + THUMB_H - th - 6
            badge_r = QRectF(bx, by, tw + 8, th + 2)
            
            painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_r, 8, 8)
            
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(badge_r, Qt.AlignmentFlag.AlignCenter, badge_text)
            
        else:
            painter.setBrush(QBrush(QColor("#252a38" if dark else "#f0f2f7")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(img_r)
            painter.setPen(QColor("#5a6278" if dark else "#9ca3af"))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(img_r, Qt.AlignmentFlag.AlignCenter,
                             f"Trang {self.page_idx + 1}\nĐang tải...")

        if self._excluded:
            cx, cy, cr = THUMB_W - 4, 10, 9
            painter.setBrush(QBrush(QColor("#f06060")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(cx, cy), cr, cr)
            pen = QPen(QColor("white"), 1.8, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(cx - 3, cy - 3, cx + 3, cy + 3)
            painter.drawLine(cx + 3, cy - 3, cx - 3, cy + 3)

        # Footer
        foot = QRect(4, THUMB_H + 7, THUMB_W, 16)
        painter.setPen(QColor("#5a6278" if dark else "#9ca3af"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(foot, Qt.AlignmentFlag.AlignCenter,
                         f"Trang {self.page_idx + 1}")
        painter.end()


# ======================================================================
# ZOOM OVERLAY — double-click mở to với animation
# ======================================================================
class ZoomOverlay(QWidget):
    """Widget toàn màn hình hiện ảnh phóng to, hỗ trợ zoom, pan, và điều hướng."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("zoom_overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._pixmap = None
        self._info = ""
        self._idx = -1
        self._opacity = 0.0
        self._scale   = 0.7
        self._zoom_level = 1.0
        self._target_zoom = 1.0
        self._pan = QPointF(0, 0)
        self._target_pan = QPointF(0, 0)
        self._dragging = False
        self._last_pos = QPoint()
        self.hide()

        self._anim_opacity = QVariantAnimation(self)
        self._anim_opacity.setDuration(220)
        self._anim_opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_opacity.valueChanged.connect(self._on_anim)

        self._anim_scale = QVariantAnimation(self)
        self._anim_scale.setDuration(220)
        self._anim_scale.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_scale.valueChanged.connect(lambda _: self.update())

        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(16)
        self._fps_timer.timeout.connect(self._on_fps_tick)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._setup_ui()

    def _setup_ui(self):
        self.btn_prev = QPushButton("◀", self)
        self.btn_prev.setFixedSize(40, 40)
        self.btn_prev.clicked.connect(lambda: self._navigate_rel(-1))

        self.btn_next = QPushButton("▶", self)
        self.btn_next.setFixedSize(40, 40)
        self.btn_next.clicked.connect(lambda: self._navigate_rel(1))

        self.btn_zin = QPushButton("+", self)
        self.btn_zin.setFixedSize(32, 32)
        self.btn_zin.clicked.connect(lambda: self._change_zoom(1.2))

        self.btn_zout = QPushButton("-", self)
        self.btn_zout.setFixedSize(32, 32)
        self.btn_zout.clicked.connect(lambda: self._change_zoom(1/1.2))

        self.btn_close = QPushButton("✕", self)
        self.btn_close.setFixedSize(40, 40)
        self.btn_close.clicked.connect(self.close_overlay)

        self.update_theme()

    def update_theme(self):
        dark = self.parent()._dark()
        bg = "rgba(30, 30, 30, 180)" if dark else "rgba(220, 220, 220, 180)"
        fg = "white" if dark else "black"
        bd = "rgba(255,255,255,50)" if dark else "rgba(0,0,0,50)"
        hov = "rgba(60, 120, 240, 200)"
        
        btn_style = f"""
            QPushButton {{
                background: {bg}; color: {fg};
                border: 1px solid {bd}; border-radius: 20px;
                font-size: 18px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {hov}; color: white; }}
        """
        small_btn_style = btn_style.replace("border-radius: 20px", "border-radius: 16px").replace("18px", "16px")
        
        self.btn_prev.setStyleSheet(btn_style)
        self.btn_next.setStyleSheet(btn_style)
        self.btn_zin.setStyleSheet(small_btn_style)
        self.btn_zout.setStyleSheet(small_btn_style)
        self.btn_close.setStyleSheet(btn_style.replace("border-radius: 20px", "border-radius: 8px"))

    def _navigate_rel(self, d: int):
        if hasattr(self.parent(), "_navigate"):
            self.parent()._navigate(self._idx + d)

    def _change_zoom(self, factor: float, center_pos=None):
        old_zoom = getattr(self, '_target_zoom', self._zoom_level)
        new_target_zoom = max(0.2, min(50.0, old_zoom * factor))
        
        if center_pos and new_target_zoom != old_zoom:
            ratio = new_target_zoom / old_zoom
            dx = center_pos.x() - self.width() / 2
            dy = center_pos.y() - self.height() / 2
            old_pan = getattr(self, '_target_pan', self._pan)
            new_target_pan = QPointF(
                dx - (dx - old_pan.x()) * ratio,
                dy - (dy - old_pan.y()) * ratio
            )
        else:
            new_target_pan = getattr(self, '_target_pan', self._pan)
            
        self._target_zoom = new_target_zoom
        self._target_pan = new_target_pan
        
        if not self._fps_timer.isActive():
            self._fps_timer.start()

    def _on_fps_tick(self):
        dz = self._target_zoom - self._zoom_level
        dpx = self._target_pan.x() - self._pan.x()
        dpy = self._target_pan.y() - self._pan.y()
        
        if abs(dz) < 0.001 and abs(dpx) < 0.1 and abs(dpy) < 0.1:
            self._zoom_level = self._target_zoom
            self._pan = QPointF(self._target_pan)
            self._fps_timer.stop()
        else:
            sf = 0.25 # smooth factor
            self._zoom_level += dz * sf
            self._pan.setX(self._pan.x() + dpx * sf)
            self._pan.setY(self._pan.y() + dpy * sf)
            
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w, h = self.width(), self.height()
        self.btn_prev.move(20, h // 2 - 20)
        self.btn_next.move(w - 60, h // 2 - 20)
        self.btn_close.move(w - 60, 20)
        self.btn_zin.move(w // 2 + 10, h - 60)
        self.btn_zout.move(w // 2 - 42, h - 60)

    def show_image(self, idx: int, px: QPixmap, info: str):
        self._idx = idx
        self._pixmap = px
        self._info = info
        self._opacity = 0.0
        self._zoom_level = 1.0
        self._target_zoom = 1.0
        self._pan = QPointF(0, 0)
        self._target_pan = QPointF(0, 0)
        self._fps_timer.stop()
        
        self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self.setFocus()

        self._anim_opacity.setStartValue(0.0)
        self._anim_opacity.setEndValue(1.0)
        self._anim_opacity.start()

        self._anim_scale.setStartValue(0.82)
        self._anim_scale.setEndValue(1.0)
        self._anim_scale.start()
        
    def _on_anim(self, val):
        self._opacity = val
        self.update()

    def update_highres(self, px: QPixmap, info: str):
        self._pixmap = px
        self._info = info
        self.update()

    def close_overlay(self):
        self._anim_opacity.setStartValue(self._opacity)
        self._anim_opacity.setEndValue(0.0)
        self._anim_opacity.start()
        
        self._anim_scale.setStartValue(
            self._anim_scale.currentValue() if self._anim_scale.currentValue() else 1.0
        )
        self._anim_scale.setEndValue(0.82)
        self._anim_scale.start()
        QTimer.singleShot(230, self._hide_and_clear)
        
    def _hide_and_clear(self):
        self.hide()
        self._pixmap = None

    def paintEvent(self, _):
        if not self._pixmap or self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Nền tối mờ
        alpha = int(self._opacity * 220)
        dark = self.parent()._dark()
        painter.fillRect(self.rect(), QColor(0, 0, 0, alpha) if dark else QColor(240, 240, 240, alpha))

        if self._opacity < 0.05:
            return

        scale = (self._anim_scale.currentValue() if self._anim_scale.currentValue() else 1.0) * self._zoom_level
        max_w = int(self.width()  * 0.88)
        max_h = int(self.height() * 0.88)
        
        # Base scale to fit screen
        fit_scale = min(max_w / self._pixmap.width(), max_h / self._pixmap.height(), 1.0)
        final_scale = fit_scale * scale

        scaled_w = int(self._pixmap.width() * final_scale)
        scaled_h = int(self._pixmap.height() * final_scale)
        x = (self.width()  - scaled_w) // 2 + self._pan.x()
        y = (self.height() - scaled_h) // 2 + self._pan.y()
        
        # Shadow
        painter.setBrush(QBrush(QColor(0, 0, 0, int(self._opacity * 80))))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(int(x) + 6, int(y) + 6, scaled_w, scaled_h, 6, 6)

        # Ảnh
        painter.setOpacity(self._opacity)
        painter.drawPixmap(int(x), int(y), scaled_w, scaled_h, self._pixmap)
        
        # Hint & Info text
        if self._opacity > 0.7:
            font = QFont("Segoe UI", 11)
            painter.setFont(font)
            info_txt = f"Trang {self._idx + 1}  ·  {self._info}" if self._info else f"Trang {self._idx + 1}"
            full_txt = f"{info_txt}   (Lăn chuột để Zoom, Click đúp để đóng)"
            
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(full_txt)
            
            # Vẽ nền mờ
            painter.setOpacity(self._opacity * 0.8)
            painter.setPen(Qt.PenStyle.NoPen)
            dark = self.parent()._dark()
            painter.setBrush(QColor(0, 0, 0, 180) if dark else QColor(255, 255, 255, 200))
            bg_rect = QRect((self.width() - tw) // 2 - 16, self.height() - 40, tw + 32, 30)
            painter.drawRoundedRect(bg_rect, 6, 6)
            
            # Vẽ chữ
            painter.setOpacity(self._opacity)
            painter.setPen(QColor("white") if dark else QColor("black"))
            painter.drawText(
                QRect(0, self.height() - 40, self.width(), 30),
                Qt.AlignmentFlag.AlignCenter,
                full_txt
            )
        painter.end()

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if delta != 0:
            self._change_zoom(1.15 if delta > 0 else 1/1.15, center_pos=e.position())
        e.accept()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self._fps_timer.isActive():
                self._fps_timer.stop()
                self._target_zoom = self._zoom_level
                self._target_pan = QPointF(self._pan)
            self._dragging = True
            self._last_pos = e.pos()

    def mouseMoveEvent(self, e):
        if self._dragging:
            delta = e.pos() - self._last_pos
            self._pan += QPointF(delta.x(), delta.y())
            self._target_pan += QPointF(delta.x(), delta.y())
            self._last_pos = e.pos()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def mouseDoubleClickEvent(self, _):
        self.close_overlay()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close_overlay()
        elif e.key() == Qt.Key.Key_Left:
            self._navigate_rel(-1)
        elif e.key() == Qt.Key.Key_Right:
            self._navigate_rel(1)
        elif e.key() == Qt.Key.Key_Equal or e.key() == Qt.Key.Key_Plus:
            self._change_zoom(1.2)
        elif e.key() == Qt.Key.Key_Minus:
            self._change_zoom(1/1.2)
        else:
            super().keyPressEvent(e)


# ======================================================================
# PREVIEW PANEL
# ======================================================================
class PreviewPanel(QWidget):
    pages_selection_changed = pyqtSignal(list)   # list of 0-indexed page nums

    def __init__(self, dark_fn, parent=None):
        super().__init__(parent)
        self._dark      = dark_fn
        self._pdf       = ""
        self._current_item = None
        self._cards: list[ThumbCard] = []
        self._render_thread = None
        self._zoom      = None
        self._click_mode = "none"
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(40)
        hl  = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0); hl.setSpacing(8)

        self.lbl_file  = QLabel("Chọn file PDF trong hàng chờ để xem trước")
        self.lbl_file.setStyleSheet("font-size:12px; font-weight:500;")
        self.lbl_pages = QLabel("")
        self.lbl_pages.setStyleSheet("font-size:11px; color:#5a6278;")

        # Thanh công cụ lọc
        self.btn_mode_include = QPushButton("Chế độ Chọn")
        self.btn_mode_exclude = QPushButton("Chế độ Loại bỏ")
        self.btn_mode_include.setCheckable(True)
        self.btn_mode_exclude.setCheckable(True)
        self.btn_mode_include.setFixedHeight(26)
        self.btn_mode_exclude.setFixedHeight(26)

        self.btn_all = QPushButton("Khôi phục (Chọn hết)")
        self.btn_none = QPushButton("Loại tất cả")
        self.btn_all.setFixedHeight(26)
        self.btn_none.setFixedHeight(26)

        self.btn_mode_include.clicked.connect(self._toggle_include)
        self.btn_mode_exclude.clicked.connect(self._toggle_exclude)
        self.btn_all.clicked.connect(self._clear_filter)
        self.btn_none.clicked.connect(self._exclude_all)

        hl.addWidget(self.lbl_file)
        hl.addWidget(self.lbl_pages)
        hl.addStretch()
        hl.addWidget(self.btn_mode_include)
        hl.addWidget(self.btn_mode_exclude)
        hl.addWidget(self.btn_all)
        hl.addWidget(self.btn_none)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)

        # Scroll area
        self.scroll = QScrollArea()
        self.scroll.setObjectName("thumb_scroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.container = QWidget()
        self.flow_lay  = FlowLayout(self.container, margin=12, spacing=8)
        self.scroll.setWidget(self.container)

        lay.addWidget(hdr)
        lay.addWidget(sep)
        lay.addWidget(self.scroll, 1)

        # Zoom overlay (lazy create)
        self._zoom = ZoomOverlay(self)
        self._update_buttons()

    def _update_buttons(self):
        dark = self._dark()
        bg_base = "#252a38" if dark else "#e2e5ed"
        bg_hov  = "#2d3345" if dark else "#d1d5db"
        text_col= "white" if dark else "black"
        bd_col  = "#3c445c" if dark else "#cbd5e1"
        
        inc_bg = "#3b82f6" if self._click_mode == "include" else bg_base
        inc_fg = "white" if self._click_mode == "include" else text_col
        inc_w  = "bold" if self._click_mode == "include" else "normal"
        self.btn_mode_include.setStyleSheet(f"QPushButton {{ background: {inc_bg}; color: {inc_fg}; font-weight: {inc_w}; border-radius: 4px; border: 1px solid {bd_col}; }} QPushButton:hover {{ background: {'#2563eb' if self._click_mode == 'include' else bg_hov}; }}")
        
        exc_bg = "#ef4444" if self._click_mode == "exclude" else bg_base
        exc_fg = "white" if self._click_mode == "exclude" else text_col
        exc_w  = "bold" if self._click_mode == "exclude" else "normal"
        self.btn_mode_exclude.setStyleSheet(f"QPushButton {{ background: {exc_bg}; color: {exc_fg}; font-weight: {exc_w}; border-radius: 4px; border: 1px solid {bd_col}; }} QPushButton:hover {{ background: {'#dc2626' if self._click_mode == 'exclude' else bg_hov}; }}")

    def update_theme(self):
        self._update_buttons()
        if self._zoom:
            self._zoom.update_theme()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._zoom:
            self._zoom.setGeometry(self.rect())

    def load_pdf(self, item):
        path = item.path
        if self._pdf == path:
            return
        self._cancel_workers()
        self._clear_cards()
        self._pdf = path
        self._current_item = item

        total = item.pages
        if total == 0:
            try:
                doc   = fitz.open(path)
                total = len(doc)
                item.pages = total
                doc.close()
            except Exception:
                self.lbl_file.setText("Không thể đọc file PDF")
                return

        self.lbl_file.setText(item.name)
        self.lbl_pages.setText(f"  {total} trang  |  {item.size_mb} MB")

        for i in range(total):
            is_ex = (i in item.excluded_pages)
            card = ThumbCard(i, self._dark, excluded=is_ex, parent=self.container)
            card.single_click.connect(self._on_card_click)
            card.double_click.connect(self._on_card_dblclick)
            self._cards.append(card)
            self.flow_lay.addWidget(card)
            card.show()
            
            # Giải phóng vòng lặp chính mỗi 15 thẻ để chống đơ UI
            if i % 15 == 0:
                QApplication.processEvents()

        # Lấy thuộc tính cài đặt từ MainWindow (cha)
        is_gray = False
        dpi = 72
        quality = 100
        mw = self.window()
        if hasattr(mw, "cb_color"):
            is_gray = mw.cb_color.currentData() == "grayscale"
        if hasattr(mw, "cb_dpi"):
            try:
                dpi = int(mw.cb_dpi.currentText().split()[0])
            except:
                dpi = 300
        if hasattr(mw, "spin_qual"):
            quality = mw.spin_qual.value()

        self._render_thread = ThumbRendererThread(path, THUMB_W, THUMB_H, gray=is_gray, dpi=dpi, quality=quality, parent=self)
        self._render_thread.ready.connect(self._on_thumb_ready)
        self._render_thread.ready_highres.connect(self._on_highres_ready)
        self._render_thread.add_pages(list(range(total)))
        self._render_thread.start()

    @pyqtSlot(int, QImage, str)
    def _on_thumb_ready(self, idx: int, img: QImage, info: str):
        if idx < len(self._cards):
            self._cards[idx].set_pixmap(QPixmap.fromImage(img), info)

    @pyqtSlot(int, QImage, str)
    def _on_highres_ready(self, idx: int, img: QImage, info: str):
        if self._zoom and self._zoom.isVisible() and self._zoom._idx == idx:
            self._zoom.update_highres(QPixmap.fromImage(img), info)

    def _on_card_click(self, idx: int):
        if self._click_mode == "none":
            return
        card = self._cards[idx]
        if self._click_mode == "exclude":
            card.set_excluded(True)
            if self._current_item: self._current_item.excluded_pages.add(idx)
        elif self._click_mode == "include":
            card.set_excluded(False)
            if self._current_item: self._current_item.excluded_pages.discard(idx)

    def _on_card_dblclick(self, idx: int, px: QPixmap, info: str):
        self._zoom.show_image(idx, px, info)
        if self._render_thread:
            self._render_thread.request_high_res(idx)

    def _navigate(self, new_idx: int):
        if 0 <= new_idx < len(self._cards):
            card = self._cards[new_idx]
            if card._pixmap:
                self._zoom.show_image(new_idx, card._pixmap, card._info)
                if self._render_thread:
                    self._render_thread.request_high_res(new_idx)

    def _toggle_include(self, checked):
        if checked:
            self._click_mode = "include"
            self.btn_mode_exclude.setChecked(False)
        else:
            self._click_mode = "none"
        self._update_buttons()

    def _toggle_exclude(self, checked):
        if checked:
            self._click_mode = "exclude"
            self.btn_mode_include.setChecked(False)
        else:
            self._click_mode = "none"
        self._update_buttons()

    def _clear_filter(self):
        if self._current_item:
            self._current_item.excluded_pages.clear()
        for c in self._cards:
            c.set_excluded(False)

    def _exclude_all(self):
        if self._current_item:
            self._current_item.excluded_pages.update(range(self._current_item.pages))
        for c in self._cards:
            c.set_excluded(True)

    def selected_pages(self) -> list[int]:
        return [c.page_idx for c in self._cards if c.is_selected()]

    def _cancel_workers(self):
        if self._render_thread:
            self._render_thread.cancel()
            self._render_thread = None

    def _clear_cards(self):
        for c in self._cards:
            self.flow_lay.removeWidget(c)
            c.deleteLater()
        self._cards.clear()
        self._pdf = ""

    def clear(self):
        self._cancel_workers()
        self._clear_cards()
        self.lbl_file.setText("Chọn file PDF trong hàng chờ để xem trước")
        self.lbl_pages.setText("")

    def set_page_done(self, page_idx: int):
        if page_idx < len(self._cards):
            self._cards[page_idx].update()


# ======================================================================
# FLOW LAYOUT — tự động xuống hàng như flex-wrap
# ======================================================================
from PyQt6.QtWidgets import QLayout, QLayoutItem

class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing
        if parent:
            self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item: QLayoutItem):
        self._items.append(item)
        self.invalidate()

    def addWidget(self, w: QWidget):
        from PyQt6.QtWidgets import QWidgetItem
        self.addItem(QWidgetItem(w))

    def removeWidget(self, w: QWidget):
        self._items = [it for it in self._items if it.widget() is not w]
        self.invalidate()

    def count(self): return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self): return True

    def heightForWidth(self, w: int) -> int:
        return self._do_layout(QRect(0, 0, w, 0), test=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def sizeHint(self): return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect: QRect, test: bool) -> int:
        m   = self.contentsMargins()
        x   = rect.x() + m.left()
        y   = rect.y() + m.top()
        row_h = 0
        line_x = x

        for it in self._items:
            sh = it.sizeHint()
            next_x = line_x + sh.width() + self._spacing
            if next_x > rect.right() - m.right() and row_h > 0:
                line_x = x
                y     += row_h + self._spacing
                next_x = line_x + sh.width() + self._spacing
                row_h  = 0
            if not test:
                it.setGeometry(QRect(QPoint(line_x, y), sh))
            line_x = next_x
            row_h  = max(row_h, sh.height())

        return y + row_h + m.bottom() - rect.y()


# ======================================================================
# LOG PANEL
# ======================================================================
class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        hdr = QWidget(); hdr.setFixedHeight(36)
        hl  = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0); hl.setSpacing(6)

        lbl = QLabel("NHẬT KÝ"); lbl.setObjectName("sec_lbl")
        btn_copy  = QPushButton("Sao chép"); btn_copy.setFixedHeight(24)
        btn_clear = QPushButton("Xoá");      btn_clear.setFixedHeight(24)
        btn_copy.clicked.connect(self._copy)
        btn_clear.clicked.connect(self.clear)
        btn_copy.setToolTip("Sao chép toàn bộ log")
        btn_clear.setToolTip("Xoá log")

        hl.addWidget(lbl); hl.addStretch()
        hl.addWidget(btn_copy); hl.addWidget(btn_clear)

        self.view = QTextEdit()
        self.view.setObjectName("log_view")
        self.view.setReadOnly(True)
        self.view.setAcceptRichText(True)
        self.view.document().setMaximumBlockCount(2000)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(hdr); lay.addWidget(sep); lay.addWidget(self.view, 1)

        self._buffer = []
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._flush_buffer)
        self._timer.start()

    def update_theme(self, is_dark: bool):
        css = """
        .ts { color: %s; }
        .fname { color: %s; }
        .ok { color: %s; }
        .err { color: %s; }
        .info { color: %s; }
        .summary { color: %s; font-weight: 600; }
        .sep { color: %s; }
        """ % (
            "#4a5268" if is_dark else "#6e7781",
            "#e4e6eb" if is_dark else "#24292f",
            "#2dbe7a" if is_dark else "#1a7f37",
            "#f06060" if is_dark else "#cf222e",
            "#4a5268" if is_dark else "#6e7781",
            "#60b0f5" if is_dark else "#0969da",
            "#252a38" if is_dark else "#d0d7de"
        )
        self.view.document().setDefaultStyleSheet(css)

    def append(self, html: str):
        self._buffer.append(html)

    def append_batch(self, html_list: list):
        self._buffer.extend(html_list)

    def _flush_buffer(self):
        if not self._buffer:
            return
        
        self.view.setUpdatesEnabled(False)
        self.view.append("<br>".join(self._buffer))
        self._buffer.clear()
        self.view.setUpdatesEnabled(True)
        
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def append_summary(self, html: str):
        sep_line = '<span class="sep">────────────────────────────────────────────</span>'
        self._buffer.append(sep_line)
        self._buffer.append(f'<span class="summary">{html}</span>')
        self._flush_buffer()

    def clear(self):
        self.view.clear()

    def _copy(self):
        QApplication.clipboard().setText(self.view.toPlainText())


# ======================================================================
# HISTORY PANEL
# ======================================================================
class HistoryItem:
    def __init__(self, name, pages, fmt, dpi, out, elapsed, ts, color="màu RGB"):
        self.name, self.pages, self.fmt = name, pages, fmt
        self.dpi, self.out, self.elapsed, self.ts, self.color = dpi, out, elapsed, ts, color


class HistoryPanel(QWidget):
    open_folder = pyqtSignal(str)
    delete_output = pyqtSignal(str) # Dùng nếu cần gọi MainWindow xử lý xóa file thực

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[HistoryItem] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(8)

        hdr = QHBoxLayout()
        lbl = QLabel("LỊCH SỬ"); lbl.setObjectName("sec_lbl")
        self.btn_clear = QPushButton("Xoá lịch sử"); self.btn_clear.setFixedHeight(26)
        self.btn_clear.clicked.connect(self._clear)
        hdr.addWidget(lbl); hdr.addStretch(); hdr.addWidget(self.btn_clear)

        self.list_w = QListWidget()
        self.list_w.setFrameShape(QFrame.Shape.NoFrame)
        self.list_w.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list_w.setFont(QFont("Segoe UI", 10))
        self.list_w.setStyleSheet("""
            QListWidget { background: transparent; }
            QListWidget::item {
                padding: 6px 4px;
                border-bottom: 1px solid rgba(128, 128, 128, 0.15);
            }
            QListWidget::item:hover {
                background: rgba(128, 128, 128, 0.1);
            }
        """)
        self.list_w.itemDoubleClicked.connect(self._on_double_click)
        self.list_w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_w.customContextMenuRequested.connect(self._on_context_menu)

        lay.addLayout(hdr); lay.addWidget(self.list_w, 1)

    def add(self, it: HistoryItem):
        self._items.insert(0, it)
        mins, secs = divmod(int(it.elapsed), 60)
        ts_str = f"{mins}p {secs}s" if mins else f"{secs}s"
        txt = f"📄 {it.name}  -  {it.pages} trang • {it.fmt} • {it.dpi} dpi • {it.color} • {ts_str}"
        
        lw_item = QListWidgetItem(txt)
        lw_item.setData(Qt.ItemDataRole.UserRole, it)
        self.list_w.insertItem(0, lw_item)

    def _on_double_click(self, lw_item):
        it: HistoryItem = lw_item.data(Qt.ItemDataRole.UserRole)
        if it and it.out:
            self.open_folder.emit(it.out)

    def _on_context_menu(self, pos):
        lw_item = self.list_w.itemAt(pos)
        if not lw_item:
            return
        
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        it: HistoryItem = lw_item.data(Qt.ItemDataRole.UserRole)
        
        menu.addAction("Mở trực tiếp", lambda: self._open_direct(it))
        menu.addAction("Mở vị trí lưu", lambda: self.open_folder.emit(it.out))
        menu.addAction("Xóa file này", lambda: self._delete_output(lw_item, it))
        menu.addAction("Xóa khỏi lịch sử", lambda: self._remove_history_item(lw_item))
        
        menu.exec(self.list_w.viewport().mapToGlobal(pos))

    def _open_direct(self, it: HistoryItem):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        import os
        if os.path.exists(it.out):
            QDesktopServices.openUrl(QUrl.fromLocalFile(it.out))

    def _delete_output(self, lw_item, it: HistoryItem):
        import shutil, os
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(self, "Xác nhận", f"Bạn có chắc muốn xóa vĩnh viễn thư mục/file đầu ra này không?\n{it.out}", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.isfile(it.out):
                    os.remove(it.out)
                elif os.path.isdir(it.out):
                    shutil.rmtree(it.out)
                self._remove_history_item(lw_item)
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", f"Không thể xóa: {e}")

    def _remove_history_item(self, lw_item):
        it = lw_item.data(Qt.ItemDataRole.UserRole)
        if it in self._items:
            self._items.remove(it)
        self.list_w.takeItem(self.list_w.row(lw_item))

    def _clear(self):
        self._items.clear()
        self.list_w.clear()

    def load(self, data: list):
        for d in reversed(data): # Reversed to insert at top in correct order
            try:
                it = HistoryItem(**d)
                self.add(it)
            except Exception:
                pass

    def dump(self) -> list:
        return [vars(it) for it in self._items]


# ======================================================================
# BADGE TOOL BUTTON — nút với dấu chấm đỏ thông báo
# ======================================================================
class BadgeToolButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._badge_visible = False

    def setBadgeVisible(self, visible: bool):
        self._badge_visible = visible
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._badge_visible:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            dot_size = 8
            x = self.width() - dot_size - 3
            y = 3
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#ff3b30")))
            painter.drawEllipse(x, y, dot_size, dot_size)
            painter.end()


# ======================================================================
# SETTINGS DIALOG — tất cả cài đặt nâng cao
# ======================================================================
class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cài đặt nâng cao")
        self.setMinimumWidth(550)
        self.cfg = dict(cfg)   # bản sao để cancel

        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        tab_main = QWidget()
        lay_main = QVBoxLayout(tab_main)

        # ── Xuất ──
        grp_out = QGroupBox("Xuất file")
        gl = QGridLayout(grp_out)
        gl.setSpacing(8)

        gl.addWidget(QLabel("Giới hạn size:"), 1, 0)
        self.cb_size = QComboBox()
        for lbl, val in SIZE_LIMITS:
            self.cb_size.addItem(lbl, val)
        idx = self.cb_size.findData(cfg.get("size_limit", 0))
        if idx >= 0: self.cb_size.setCurrentIndex(idx)
        gl.addWidget(self.cb_size, 1, 1)

        gl.addWidget(QLabel("Pattern tên file:"), 2, 0)
        self.inp_pattern = QComboBox()
        self.inp_pattern.setEditable(True)
        self.inp_pattern.addItems([
            "{pdf} - trang {page:01d}",
            "{pdf}_{page:03d}",
            "{pdf}_{page}"
        ])
        current_pattern = cfg.get("name_pattern", "{pdf} - trang {page:01d}")
        self.inp_pattern.setCurrentText(current_pattern)
        self.inp_pattern.setToolTip(
            "{pdf} = tên PDF gốc\n"
            "{page:01d} = số trang (VD: 1, 2, 3)\n"
            "{page:03d} = số trang 3 chữ số (VD: 001, 002)\n"
            "Ví dụ: {pdf}_{page:03d} → file_001.png"
        )
        gl.addWidget(self.inp_pattern, 2, 1)

        gl.addWidget(QLabel("Hiệu năng xử lý:"), 3, 0)
        self.cb_perf = QComboBox()
        self.cb_perf.addItem("Bình thường - 1 luồng)", 1)
        self.cb_perf.addItem("2 luồng", 2)
        self.cb_perf.addItem("4 luồng", 4)
        self.cb_perf.addItem("6 luồng", 6)
        self.cb_perf.addItem("8 luồng", 8)
        self.cb_perf.addItem("Nhanh nhất - 10 luồng", 10)
        idx = self.cb_perf.findData(cfg.get("performance", 1))
        if idx >= 0: self.cb_perf.setCurrentIndex(idx)
        gl.addWidget(self.cb_perf, 3, 1)

        lay_main.addWidget(grp_out)

        # ── Watermark ──
        grp_wm = QGroupBox("Watermark")
        wl = QVBoxLayout(grp_wm)
        self.chk_wm = QCheckBox("Bật watermark")
        self.chk_wm.setChecked(cfg.get("watermark_on", False))
        self.inp_wm = QLineEdit(cfg.get("watermark",""))
        self.inp_wm.setPlaceholderText("Nhập text watermark...")
        self.inp_wm.setEnabled(self.chk_wm.isChecked())
        self.chk_wm.toggled.connect(self.inp_wm.setEnabled)
        wl.addWidget(self.chk_wm); wl.addWidget(self.inp_wm)
        lay_main.addWidget(grp_wm)

        # ── Sau khi xong ──
        grp_post = QGroupBox("Sau khi hoàn thành")
        pl = QVBoxLayout(grp_post)
        self.chk_zip  = QCheckBox("Nén ảnh đầu ra thành file ZIP")
        self.chk_auto = QCheckBox("Tự động mở thư mục đầu ra")
        self.chk_zip.setChecked(cfg.get("zip_output", False))
        self.chk_auto.setChecked(cfg.get("auto_open", False))
        pl.addWidget(self.chk_zip); pl.addWidget(self.chk_auto)
        lay_main.addWidget(grp_post)

        # ── Giao diện ──
        grp_ui = QGroupBox("Giao diện")
        ul = QVBoxLayout(grp_ui)
        self.chk_time = QCheckBox("Hiện timestamp trong nhật ký")
        self.chk_time.setChecked(cfg.get("show_time", True))
        ul.addWidget(self.chk_time)
        lay_main.addWidget(grp_ui)

        # ── Nhận diện thông minh ──
        grp_smart = QGroupBox("Nhận diện thông minh")
        gl_smart = QVBoxLayout(grp_smart)
        self.chk_smart_color = QCheckBox("Tự động xuất ảnh Trắng/Đen nếu PDF không có màu")
        self.chk_smart_color.setChecked(cfg.get("smart_color", True))
        gl_smart.addWidget(self.chk_smart_color)
        lbl_smart = QLabel("<i>Áp dụng cho cả phần mềm và Context Menu. Giúp tiết kiệm dung lượng.</i>")
        lbl_smart.setStyleSheet("color: #888888; font-size: 11px;")
        gl_smart.addWidget(lbl_smart)
        lay_main.addWidget(grp_smart)

        lay_main.addStretch()
        self.tabs.addTab(tab_main, "Cài đặt chung")

        # ── Tab 2: Context Menu ──
        tab_cm = QWidget()
        lay_cm = QVBoxLayout(tab_cm)

        grp_cm = QGroupBox("Thông số Context Menu (Chuột phải)")
        gl_cm = QGridLayout(grp_cm)
        gl_cm.setSpacing(8)

        gl_cm.addWidget(QLabel("Định dạng:"), 0, 0)
        self.cb_cm_format = QComboBox()
        self.cb_cm_format.addItems(FORMATS)
        idx = self.cb_cm_format.findText(cfg.get("cm_format", "PNG"))
        if idx >= 0: self.cb_cm_format.setCurrentIndex(idx)
        gl_cm.addWidget(self.cb_cm_format, 0, 1)

        gl_cm.addWidget(QLabel("Chế độ màu:"), 1, 0)
        self.cb_cm_color = QComboBox()
        self.cb_cm_color.addItem("Màu sắc (RGB)", "color")
        self.cb_cm_color.addItem("Trắng đen (Grayscale)", "gray")
        idx_c = self.cb_cm_color.findData(cfg.get("cm_color_mode", "color"))
        if idx_c >= 0: self.cb_cm_color.setCurrentIndex(idx_c)
        gl_cm.addWidget(self.cb_cm_color, 1, 1)

        gl_cm.addWidget(QLabel("Độ phân giải:"), 2, 0)
        self.cb_cm_dpi = QComboBox()
        for lbl, val in DPI_OPTIONS:
            self.cb_cm_dpi.addItem(lbl, val)
        idx_dpi = self.cb_cm_dpi.findData(cfg.get("cm_dpi", 300))
        if idx_dpi >= 0: self.cb_cm_dpi.setCurrentIndex(idx_dpi)
        gl_cm.addWidget(self.cb_cm_dpi, 2, 1)
        
        self.chk_cm_notify = QCheckBox("Hiển thị thông báo (Notification)")
        self.chk_cm_notify.setChecked(cfg.get("cm_notify", True))
        gl_cm.addWidget(self.chk_cm_notify, 3, 0, 1, 2)

        lay_cm.addWidget(grp_cm)
        lay_cm.addStretch()
        self.tabs.addTab(tab_cm, "Context menu")

        # ── Tab 3: Hệ thống ──
        tab_sys = QWidget()
        lay_sys = QVBoxLayout(tab_sys)

        self.chk_autostart = QCheckBox("Khởi động cùng Windows (để dùng context menu)")
        self.chk_autostart.setChecked(is_autostart_enabled())
        self.chk_autostart.toggled.connect(self._on_autostart_toggled)
        lay_sys.addWidget(self.chk_autostart)

        # Cập nhật
        grp_update = QGroupBox("Cập nhật phần mềm")
        lay_upd = QVBoxLayout(grp_update)
        
        self.chk_auto_update = QCheckBox("Tự động kiểm tra bản cập nhật")
        self.chk_auto_update.setChecked(cfg.get("auto_check_update", True))
        lay_upd.addWidget(self.chk_auto_update)

        h_upd = QHBoxLayout()
        # Hiển thị trạng thái từ config
        self._cfg_ref = cfg
        auto_check = cfg.get("auto_check_update", True)
        update_status = cfg.get("update_status", "unknown")
        update_ver = cfg.get("update_latest_version", "")
        update_pub = cfg.get("update_published_at", "")
        
        if not auto_check:
            status_text = "Chưa kiểm tra"
            status_color = "#888888"
            show_download = False
        elif update_status == "available" and update_ver:
            status_text = f"Có bản cập nhật mới v{update_ver}!"
            if update_pub:
                status_text += f" (Phát hành: {update_pub})"
            status_color = "#dc3545"
            show_download = True
        elif update_status == "latest":
            status_text = "Bạn đang dùng bản mới nhất."
            status_color = "#28a745"
            show_download = False
        elif update_status == "error":
            status_text = "Lỗi kiểm tra cập nhật."
            status_color = "#dc3545"
            show_download = False
        else:
            status_text = "Đang chờ kiểm tra..."
            status_color = "#888888"
            show_download = False
        
        self.lbl_update_status = QLabel(status_text)
        self.lbl_update_status.setStyleSheet(f"color: {status_color};")
        self.lbl_update_status.setWordWrap(True)
        self.lbl_update_status.setMinimumWidth(180)
        self.btn_check_update = QPushButton("Kiểm tra")
        self.btn_check_update.clicked.connect(self._manual_check_update)
        
        self.btn_download_update = QPushButton("Cập nhật ngay")
        self.btn_download_update.setStyleSheet("background-color: #28a745; color: white;")
        self.btn_download_update.setVisible(show_download)
        if show_download:
            self.update_url = cfg.get("update_url", "")
        self.btn_download_update.clicked.connect(self._start_download)
        
        h_upd.addWidget(self.lbl_update_status)
        h_upd.addStretch()
        h_upd.addWidget(self.btn_check_update)
        h_upd.addWidget(self.btn_download_update)
        lay_upd.addLayout(h_upd)
        
        # Vùng hiển thị Release notes
        self.txt_release_notes = QTextEdit()
        self.txt_release_notes.setReadOnly(True)
        self.txt_release_notes.setVisible(show_download)
        self.txt_release_notes.setMaximumHeight(100)
        self.txt_release_notes.setStyleSheet("font-size: 11px; color: #888; background: transparent; border: 1px solid #444; border-radius: 4px; padding: 4px;")
        if show_download:
            notes = cfg.get("update_release_notes", "")
            if notes:
                self.txt_release_notes.setPlainText(notes)
        lay_upd.addWidget(self.txt_release_notes)
        
        lay_sys.addWidget(grp_update)

        # Thông tin
        grp_info = QGroupBox("Thông tin phần mềm")
        il = QVBoxLayout(grp_info)
        lbl_info = QLabel(f"<b>{APP_NAME}</b> <br>Phiên bản: {APP_VERSION}<br>Tác giả: <b>{APP_AUTHOR}</b><br>Bị rảnh nên làm ra cái này.")
        lbl_info.setTextFormat(Qt.TextFormat.RichText)
        lbl_info.setStyleSheet("font-size: 11px; color: #888888;")
        il.addWidget(lbl_info)
        lay_sys.addWidget(grp_info)

        lay_sys.addStretch()
        has_update = getattr(parent, 'has_update', False)
        sys_name = "Hệ thống 🔴" if has_update else "Hệ thống"
        self.tabs.addTab(tab_sys, sys_name)

        # ── Tab 4: Báo lỗi / Góp ý ──
        tab_fb = QWidget()
        lay_fb = QVBoxLayout(tab_fb)
        
        grp_fb = QGroupBox("Gửi Góp ý / Báo lỗi")
        lay_gfb = QVBoxLayout(grp_fb)
        
        # Email
        lay_em = QHBoxLayout()
        lay_em.addWidget(QLabel("Email của bạn (không bắt buộc):"))
        self.inp_fb_email = QLineEdit()
        self.inp_fb_email.setPlaceholderText("Để lại email nếu bạn muốn nhận phản hồi")
        lay_em.addWidget(self.inp_fb_email)
        lay_gfb.addLayout(lay_em)
        
        # Loại báo cáo
        lay_type = QHBoxLayout()
        lay_type.addWidget(QLabel("Loại báo cáo:"))
        self.rad_fb_gopy = QRadioButton("Góp ý")
        self.rad_fb_baoloi = QRadioButton("Báo lỗi")
        self.rad_fb_ca2 = QRadioButton("Cả 2")
        self.rad_fb_ca2.setChecked(True)
        lay_type.addWidget(self.rad_fb_gopy)
        lay_type.addWidget(self.rad_fb_baoloi)
        lay_type.addWidget(self.rad_fb_ca2)
        lay_type.addStretch()
        lay_gfb.addLayout(lay_type)
        
        # Nội dung
        lay_gfb.addWidget(QLabel("Nội dung (Bắt buộc):"))
        self.txt_fb_content = QTextEdit()
        self.txt_fb_content.setPlaceholderText("Vui lòng mô tả chi tiết lỗi bạn gặp phải hoặc ý kiến đóng góp của bạn...")
        lay_gfb.addWidget(self.txt_fb_content)
        
        # Thông tin đi kèm
        import platform
        os_info_str = get_os_full_version()
        sys_info = f"Thông tin đính kèm: {platform.node()} | HĐH: {os_info_str}"
        lbl_sys_info = QLabel(sys_info)
        lbl_sys_info.setStyleSheet("color: #888; font-size: 11px;")
        lay_gfb.addWidget(lbl_sys_info)
        
        # Nút Gửi
        self.btn_fb_submit = QPushButton("Gửi báo cáo")
        self.btn_fb_submit.setStyleSheet("background-color: #007bff; color: white; padding: 5px 15px;")
        self.btn_fb_submit.clicked.connect(self._submit_feedback)
        lay_btn_fb = QHBoxLayout()
        lay_btn_fb.addStretch()
        lay_btn_fb.addWidget(self.btn_fb_submit)
        lay_gfb.addLayout(lay_btn_fb)
        
        lay_fb.addWidget(grp_fb)
        self.tabs.addTab(tab_fb, "Báo lỗi / Góp ý")

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_reset = btns.addButton("Khôi phục mặc định", QDialogButtonBox.ButtonRole.ResetRole)
        btn_reset.clicked.connect(self._restore_defaults)
        
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _restore_defaults(self):
        main = self.parent()
        cfg = DEFAULT_CFG

        idx_size = self.cb_size.findData(cfg.get("size_limit", 0))
        if idx_size >= 0: self.cb_size.setCurrentIndex(idx_size)
        
        self.inp_pattern.setCurrentText(cfg.get("name_pattern", "{pdf} - trang {page:01d}"))
        self.chk_wm.setChecked(cfg.get("watermark_on", False))
        self.inp_wm.setText(cfg.get("watermark", ""))
        self.chk_zip.setChecked(cfg.get("zip_output", False))
        self.chk_auto.setChecked(cfg.get("auto_open", False))
        self.chk_time.setChecked(cfg.get("show_time", True))
        self.chk_smart_color.setChecked(cfg.get("smart_color", True))
        self.chk_auto_update.setChecked(True)
        self.chk_autostart.setChecked(True)
        
        idx_perf = self.cb_perf.findData(cfg.get("performance", 1))
        if idx_perf >= 0: self.cb_perf.setCurrentIndex(idx_perf)
        
        idx_cm_fmt = self.cb_cm_format.findText(cfg.get("cm_format", "PNG"))
        if idx_cm_fmt >= 0: self.cb_cm_format.setCurrentIndex(idx_cm_fmt)
        
        idx_cm_c = self.cb_cm_color.findData(cfg.get("cm_color_mode", "color"))
        if idx_cm_c >= 0: self.cb_cm_color.setCurrentIndex(idx_cm_c)
        
        idx_cm_dpi = self.cb_cm_dpi.findData(cfg.get("cm_dpi", 300))
        if idx_cm_dpi >= 0: self.cb_cm_dpi.setCurrentIndex(idx_cm_dpi)
        
        self.chk_cm_notify.setChecked(cfg.get("cm_notify", True))

        # Cập nhật cả thông số trên thanh công cụ của cửa sổ chính
        if main and hasattr(main, "cb_format"):
            idx_color = main.cb_color.findData(cfg.get("color_mode", "color"))
            if idx_color >= 0: main.cb_color.setCurrentIndex(idx_color)
            
            idx_fmt = main.cb_format.findText(cfg.get("format", "JPG"))
            if idx_fmt >= 0: main.cb_format.setCurrentIndex(idx_fmt)
            
            dpi = cfg.get("dpi", 300)
            idx = main.cb_dpi.findData(dpi)
            if idx >= 0:
                main.cb_dpi.setCurrentIndex(idx)
            else:
                custom_idx = main.cb_dpi.findData(-1)
                if custom_idx < 0: custom_idx = main.cb_dpi.count()
                main.cb_dpi.insertItem(custom_idx, f"{dpi} — Tùy chỉnh", dpi)
                while main.cb_dpi.count() > len(DPI_OPTIONS) + 4:
                    main.cb_dpi.removeItem(len(DPI_OPTIONS))
                main.cb_dpi.setCurrentIndex(main.cb_dpi.findData(dpi))
                    
            main.sld_qual.setValue(cfg.get("quality", 100))
            main.spin_qual.setValue(cfg.get("quality", 100))

    def _manual_check_update(self):
        self.btn_check_update.setEnabled(False)
        self.lbl_update_status.setText("Trạng thái: Đang kiểm tra...")
        self.lbl_update_status.setStyleSheet("color: #007bff;")
        self.btn_download_update.setVisible(False)
        self.txt_release_notes.setVisible(False)
        
        self.checker = UpdateCheckerThread()
        self.checker.update_result.connect(self._on_check_result)
        self.checker.start()

    def _on_check_result(self, has_update, version, url, published_at, body):
        self.btn_check_update.setEnabled(True)
        # Lưu kết quả vào config
        main_win = self.parent()
        if has_update:
            msg = f"Có bản cập nhật mới v{version}!"
            if published_at:
                msg += f" (Phát hành: {published_at})"
            self.lbl_update_status.setText(msg)
            self.lbl_update_status.setStyleSheet("color: #dc3545; font-weight: bold;")
            self.btn_download_update.setVisible(True)
            self.update_url = url
            if body:
                self.txt_release_notes.setPlainText(body)
                self.txt_release_notes.setVisible(True)
            if main_win and hasattr(main_win, 'cfg'):
                main_win.cfg.update({
                    "update_status": "available",
                    "update_latest_version": version,
                    "update_url": url,
                    "update_published_at": published_at,
                    "update_release_notes": body,
                })
        elif version:
            self.lbl_update_status.setText("Bạn đang dùng bản mới nhất.")
            self.lbl_update_status.setStyleSheet("color: #28a745;")
            if body:
                self.txt_release_notes.setPlainText(body)
                self.txt_release_notes.setVisible(True)
            if main_win and hasattr(main_win, 'hide_update_indicator'):
                main_win.hide_update_indicator()
            if main_win and hasattr(main_win, 'cfg'):
                main_win.cfg.update({
                    "update_status": "latest",
                    "update_latest_version": version,
                    "update_url": url,
                    "update_published_at": published_at,
                    "update_release_notes": body,
                })
        else:
            self.lbl_update_status.setText("Lỗi kiểm tra cập nhật.")
            self.lbl_update_status.setStyleSheet("color: #dc3545;")
            if main_win and hasattr(main_win, 'cfg'):
                main_win.cfg.update({"update_status": "error"})

    def _start_download(self):
        if not hasattr(self, 'update_url') or not self.update_url.endswith('.exe'):
            if hasattr(self, 'update_url'):
                from PyQt6.QtGui import QDesktopServices
                from PyQt6.QtCore import QUrl
                QDesktopServices.openUrl(QUrl(self.update_url))
            return
            
        self.btn_download_update.setEnabled(False)
        self.btn_download_update.setText("Đang tải... 0%")
        
        self.downloader = DownloadUpdateThread(self.update_url)
        self.downloader.progress.connect(self._on_download_progress)
        self.downloader.finished.connect(self._on_download_finished)
        self.downloader.start()
        
    def _on_download_progress(self, pct):
        self.btn_download_update.setText(f"Đang tải... {pct}%")
        
    def _on_download_finished(self, success, result):
        if success:
            self.btn_download_update.setText("Đang khởi chạy bộ cài đặt...")
            is_busy = False
            main_win = self.parent()
            if main_win and hasattr(main_win, 'service') and main_win.service:
                is_busy = main_win.service.is_busy()
                
            if is_busy:
                from PyQt6.QtWidgets import QMessageBox
                ans = QMessageBox.question(self, "Đang xử lý", 
                    "Phần mềm đang xử lý PDF. Cài đặt bản cập nhật ngay bây giờ sẽ hủy tiến trình hiện tại. Bạn có muốn bắt buộc cài đặt ngay không?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if ans == QMessageBox.StandardButton.No:
                    self.btn_download_update.setText("Cài đặt thủ công")
                    self.btn_download_update.setEnabled(True)
                    try:
                        self.btn_download_update.clicked.disconnect()
                    except:
                        pass
                    def _open_exe():
                        import os
                        os.startfile(result)
                    self.btn_download_update.clicked.connect(_open_exe)
                    return
            
            # Lưu đường dẫn file cài đặt để dùng sau khi delay
            self._installer_path = result
            
            # Dùng QTimer delay 500ms để Qt event loop kịp xử lý trước khi chạy bộ cài đặt
            QTimer.singleShot(500, self._launch_installer_and_exit)
        else:
            self.btn_download_update.setText("Lỗi tải xuống")
            self.btn_download_update.setEnabled(True)

    def _launch_installer_and_exit(self):
        import ctypes
        import sys
        import os
        
        installer_path = getattr(self, '_installer_path', '')
        if not installer_path or not os.path.isfile(installer_path):
            self.btn_download_update.setText("Lỗi: Không tìm thấy file cài đặt")
            self.btn_download_update.setEnabled(True)
            return
        
        # Sử dụng ShellExecuteW với verb "runas" để yêu cầu quyền Admin trực tiếp
        # Hàm này trả về giá trị > 32 nếu thành công
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,           # hwnd
            "runas",        # lpOperation - yêu cầu quyền Admin
            installer_path, # lpFile
            "",             # lpParameters
            None,           # lpDirectory
            1               # nShowCmd = SW_SHOWNORMAL
        )
        
        if ret <= 32:
            # ShellExecute thất bại (ví dụ: người dùng từ chối UAC)
            self.btn_download_update.setText("Cài đặt thủ công")
            self.btn_download_update.setEnabled(True)
            try:
                self.btn_download_update.clicked.disconnect()
            except:
                pass
            path = installer_path
            def _open_exe():
                os.startfile(path)
            self.btn_download_update.clicked.connect(_open_exe)
            return
        
        # Bộ cài đặt đã khởi chạy thành công, đợi 3 giây rồi thoát ứng dụng
        # Dùng QTimer thay vì time.sleep để không block Qt event loop
        self.btn_download_update.setText("Đang thoát để cài đặt...")
        QTimer.singleShot(3000, self._exit_for_update)
    
    def _exit_for_update(self):
        from PyQt6.QtCore import QCoreApplication
        import psutil
        import sys
        import os
        try:
            current_pid = os.getpid()
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['pid'] == current_pid: continue
                    if getattr(sys, 'frozen', False):
                        if proc.info['name'] == 'PDF to Image.exe': proc.kill()
                    else:
                        cmd = proc.info.get('cmdline', [])
                        if cmd and 'pdf-to-image.py' in ' '.join(cmd): proc.kill()
                except:
                    pass
        except:
            pass
        QCoreApplication.quit()
        sys.exit(0)

    def _submit_feedback(self):
        content = self.txt_fb_content.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập nội dung báo lỗi hoặc góp ý.")
            return
            
        self.btn_fb_submit.setEnabled(False)
        self.btn_fb_submit.setText("Đang gửi...")
        
        email = self.inp_fb_email.text().strip()
        if self.rad_fb_gopy.isChecked():
            report_type = "Góp ý"
        elif self.rad_fb_baoloi.isChecked():
            report_type = "Báo lỗi"
        else:
            report_type = "Cả 2"
        
        import platform
        sys_os = get_os_full_version()
        sys_node = platform.node()
        
        # Thread để gửi ngầm
        def send_task():
            import urllib.request
            import urllib.parse
            
            url = "https://docs.google.com/forms/d/e/1FAIpQLSeK1nFpaCWVIXieFrA76oiCEZXySou66UzvcQ2gkx28dWlBWA/formResponse"
            data = {
                "entry.694733527": sys_os,
                "entry.534600766": sys_node,
                "entry.1814472357": email,
                "entry.624113546": report_type,
                "entry.829776351": content
            }
            try:
                encoded_data = urllib.parse.urlencode(data).encode('utf-8')
                req = urllib.request.Request(url, data=encoded_data, headers={'User-Agent': 'Mozilla/5.0'})
                urllib.request.urlopen(req, timeout=10)
                return True
            except Exception as e:
                return False
                
        self._fb_thread = Thread(target=send_task, daemon=True)
        
        def on_done():
            # Chờ thread xong rồi cập nhật UI
            self._fb_thread.join(0.1)
            if not self._fb_thread.is_alive():
                self.btn_fb_submit.setEnabled(True)
                self.btn_fb_submit.setText("Gửi báo cáo")
                self.txt_fb_content.clear()
                QMessageBox.information(self, "Thành công", "Đã gửi báo cáo thành công. Cảm ơn bạn!")
                self._fb_timer.stop()
            
        self._fb_timer = QTimer()
        self._fb_timer.timeout.connect(on_done)
        self._fb_timer.start(500)
        self._fb_thread.start()

    def _on_autostart_toggled(self, checked):
        set_autostart(checked)

    def get_values(self) -> dict:
        return {
            "auto_check_update": self.chk_auto_update.isChecked(),
            "size_limit":   self.cb_size.currentData(),
            "name_pattern": self.inp_pattern.currentText() or "{pdf} - trang {page:01d}",
            "watermark_on": self.chk_wm.isChecked(),
            "watermark":    self.inp_wm.text(),
            "zip_output":   self.chk_zip.isChecked(),
            "auto_open":    self.chk_auto.isChecked(),
            "show_time":    self.chk_time.isChecked(),
            "performance":  self.cb_perf.currentData(),
            "smart_color":  self.chk_smart_color.isChecked(),
            "cm_format":    self.cb_cm_format.currentText(),
            "cm_color_mode":self.cb_cm_color.currentData(),
            "cm_dpi":       self.cb_cm_dpi.currentData(),
            "cm_notify":    self.chk_cm_notify.isChecked(),
        }


# ======================================================================
# CONVERSION WORKER
# ======================================================================
class WorkerSignals(QObject):
    overall_progress = pyqtSignal(int, int, int)
    file_started     = pyqtSignal(int)
    file_progress    = pyqtSignal(int, int)
    file_done        = pyqtSignal(int, float)
    file_error       = pyqtSignal(int, str)
    log_message      = pyqtSignal(str)
    log_batch        = pyqtSignal(list)
    all_done         = pyqtSignal(dict)



def save_to_buf(img, buf, pil_fmt: str, quality: int, size_kb: int):
    kw = {}
    if pil_fmt == "JPEG":  kw = {"quality": quality, "optimize": True}
    elif pil_fmt == "WEBP": kw = {"quality": quality, "method": 4}
    elif pil_fmt == "TIFF": kw = {"compression": "tiff_lzw"}

    if size_kb <= 0 or pil_fmt in ("PNG","TIFF"):
        img.save(buf, pil_fmt, **kw); return

    limit = size_kb * 1024

    # Try saving at original quality first — skip compression if already under limit
    temp = io.BytesIO()
    img.save(temp, pil_fmt, **kw)
    if len(temp.getvalue()) <= limit:
        buf.write(temp.getvalue()); return

    # Binary search for highest quality that fits under the limit
    lo, hi, best_q = 10, quality - 1, None
    best_buf = None
    for _ in range(8):
        if lo > hi:
            break
        mid = (lo + hi) // 2
        kw["quality"] = mid
        temp = io.BytesIO()
        img.save(temp, pil_fmt, **kw)
        if len(temp.getvalue()) <= limit:
            best_q = mid; lo = mid + 1
            best_buf = temp
        else:
            hi = mid - 1

    if best_buf:
        buf.write(best_buf.getvalue())
        return

    # Fallback: quality=10 still too large — progressively downscale image
    for scale in (0.75, 0.5, 0.35, 0.25):
        new_w = max(1, int(img.width * scale))
        new_h = max(1, int(img.height * scale))
        from PIL import Image as _PILImage
        small = img.resize((new_w, new_h), _PILImage.LANCZOS)
        kw["quality"] = 10
        temp = io.BytesIO()
        small.save(temp, pil_fmt, **kw)
        if len(temp.getvalue()) <= limit:
            buf.write(temp.getvalue()); return

    # Last resort: save smallest version even if over limit
    kw["quality"] = 10
    new_w = max(1, int(img.width * 0.25))
    new_h = max(1, int(img.height * 0.25))
    from PIL import Image as _PILImage
    small = img.resize((new_w, new_h), _PILImage.LANCZOS)
    small.save(buf, pil_fmt, **kw)

def apply_watermark(img, text: str, gray: bool):
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(img)
    w, h = img.size
    fs   = max(20, int(min(w,h) * 0.04))
    try:    font = ImageFont.truetype("arial.ttf", fs)
    except: font = ImageFont.load_default()
    bb  = draw.textbbox((0,0), text, font=font)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    fill = 128 if gray else (160,160,160)
    draw.text(((w-tw)//2, (h-th)//2), text, font=font, fill=fill)
    return img


def is_page_colored(page: fitz.Page) -> bool:
    from PIL import ImageChops, Image
    mat = fitz.Matrix(0.1, 0.1) # 7.2 DPI is enough for color detection
    try:
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        r, g, b = img.split()
        diff1 = ImageChops.difference(r, g)
        diff2 = ImageChops.difference(r, b)
        # If max difference between channels is small, it's grayscale
        if diff1.getextrema()[1] < 5 and diff2.getextrema()[1] < 5:
            return False
        return True
    except Exception:
        return True # Default to color if error

def process_pdf_item(g_idx, item, cfg, out_base, pause_event, stop_event, io_queue, msg_queue):
    import fitz, time, io
    from PIL import Image
    from pathlib import Path
    from datetime import datetime

    msg_queue.put(("file_started", g_idx))
    t0 = time.time()
    
    fmt      = cfg["format"]
    dpi      = cfg["dpi"]
    quality  = cfg["quality"]
    gray     = cfg.get("color_mode","color") == "grayscale"
    smart    = cfg.get("smart_color", True)
    pattern  = cfg.get("name_pattern","{pdf}_{page:03d}")
    wm_text  = cfg.get("watermark","") if cfg.get("watermark_on") else ""
    size_kb  = cfg.get("size_limit", 0)
    show_ts  = cfg.get("show_time", True)

    zoom = dpi / 72.0
    doc  = fitz.open(item.path)

    if doc.needs_pass:
        doc.close()
        raise ValueError("PDF có mật khẩu — chưa hỗ trợ tự động mở")

    total_p   = len(doc)
    base_name = Path(item.path).stem

    cm_action = cfg.get("cm_action")
    if cfg.get("zip_output"):
        job_type = "zip"
        if item.group_name:
            out_path = Path(out_base) / f"{item.group_name}.zip" if out_base else Path(item.parent_dir) / f"{item.group_name}.zip"
        else:
            out_path = Path(out_base) / f"{base_name}.zip" if out_base else Path(item.parent_dir) / f"{base_name}.zip"
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        job_type = "disk"
        if cm_action == "create_here":
            out_path = Path(item.parent_dir)
        elif cm_action == "create_individual":
            out_path = Path(item.parent_dir) / base_name
        elif cm_action == "create_combined":
            out_path = Path(out_base)
        else:
            if item.group_name:
                out_path = Path(out_base) / item.group_name if out_base else Path(item.parent_dir) / f"{item.group_name}_Images"
            else:
                out_path = Path(out_base) / base_name if out_base else Path(item.parent_dir) / base_name
        out_path.mkdir(parents=True, exist_ok=True)

    out_folder_str = str(out_path)
    out_path_str = str(out_path)

    mat = fitz.Matrix(zoom, zoom)
    FMT_MAP = {"PNG":"PNG","JPG":"JPEG","WebP":"WEBP","TIFF":"TIFF"}
    pil_fmt = FMT_MAP.get(fmt, "PNG")

    pages_to_process = [p for p in range(total_p) if p not in item.excluded_pages]
    if not pages_to_process:
        doc.close()
        return 0, out_folder_str, time.time() - t0

    processed = 0
    target = len(pages_to_process)
    last_ui_time = 0
    log_batch_list = []

    for p in pages_to_process:
        while pause_event.is_set() and not stop_event.is_set():
            time.sleep(0.1)
        if stop_event.is_set():
            break
            
        page = doc.load_page(p)
        
        page_gray = gray
        if not page_gray and smart:
            page_gray = not is_page_colored(page)
            
        if page_gray:
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
            img = Image.frombytes("L", [pix.width, pix.height], pix.samples)
        else:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        if wm_text:
            img = apply_watermark(img, wm_text, page_gray)

        if target == 1:
            fname = base_name
        else:
            try:
                fname = pattern.format(pdf=base_name, page=p + 1)
            except Exception:
                fname = f"{base_name}_{p+1:03d}"
        fname += f".{fmt.lower()}"

        buf = io.BytesIO()
        save_to_buf(img, buf, pil_fmt, quality, size_kb)
        io_queue.put((job_type, out_path_str, fname, buf.getvalue()))

        ts   = (datetime.now().strftime("[%H:%M:%S] ") if show_ts else "")
        lbl  = f" — Trang {p+1}/{total_p}" if total_p > 1 else ""
        color_txt = "Trắng đen (Auto)" if (not gray and page_gray) else ("Trắng đen" if page_gray else "RGB")
        info = f"{pix.width}×{pix.height}  {fmt}  {dpi}dpi {color_txt}"
        log_batch_list.append(
            f'<span class="ts">{ts}</span>'
            f'<span class="fname">{base_name}{lbl}</span> '
            f'<span class="ok">✓</span>  '
            f'<span class="info">{info}</span>'
        )
        processed += 1
        
        now = time.time()
        if now - last_ui_time > 0.1 or processed == target:
            msg_queue.put(("file_progress", g_idx, int(processed / target * 100)))
            if log_batch_list:
                msg_queue.put(("log_batch", log_batch_list))
                log_batch_list = []
            last_ui_time = now

    doc.close()
    return target, out_folder_str, time.time() - t0

class ConversionWorker(QThread):
    def __init__(self, indexed_queue: list[tuple[int, QueueItem]], cfg: dict, out_base: str):
        super().__init__()
        self.indexed_queue = indexed_queue
        self.cfg           = cfg
        self.out_base      = out_base
        self.signals       = WorkerSignals()
        self._stop         = False
        self._pause        = False
        self._lock         = threading.Lock()
        self.max_workers   = cfg.get("performance", 1)

    def _io_worker_mp(self, io_queue):
        open_zips = {}
        while True:
            job = io_queue.get()
            if job is None: break
            try:
                job_type, path_str, fname, data = job
                if job_type == "zip":
                    if path_str not in open_zips:
                        open_zips[path_str] = zipfile.ZipFile(path_str, "a", zipfile.ZIP_DEFLATED)
                    open_zips[path_str].writestr(fname, data)
                elif job_type == "disk":
                    with open(os.path.join(path_str, fname), "wb") as f:
                        f.write(data)
            except Exception:
                pass
            finally:
                pass # no task_done needed for Process Queue if not Joinable
        
        for zf in open_zips.values():
            try: zf.close()
            except: pass

    def request_stop(self): 
        self._stop = True
        if hasattr(self, '_stop_event'): self._stop_event.set()
    def pause(self): 
        self._pause = True
        if hasattr(self, '_pause_event'): self._pause_event.set()
    def resume(self): 
        self._pause = False
        if hasattr(self, '_pause_event'): self._pause_event.clear()

    def run(self):
        total   = len(self.indexed_queue)
        done    = failed = pages = 0
        t_start = time.time()
        self._last_ui_update = 0

        with multiprocessing.Manager() as manager:
            self._pause_event = manager.Event()
            self._stop_event = manager.Event()
            if self._pause: self._pause_event.set()
            if self._stop: self._stop_event.set()
            
            io_queue = manager.Queue()
            msg_queue = manager.Queue()

            self._io_thread = threading.Thread(target=self._io_worker_mp, args=(io_queue,), daemon=True)
            self._io_thread.start()
            
            def msg_worker():
                while True:
                    msg = msg_queue.get()
                    if msg is None: break
                    mtype = msg[0]
                    if mtype == "file_progress":
                        self.signals.file_progress.emit(msg[1], msg[2])
                    elif mtype == "log_batch":
                        self.signals.log_batch.emit(msg[1])
                    elif mtype == "file_started":
                        self.signals.file_started.emit(msg[1])
                    elif mtype == "file_error":
                        self.signals.file_error.emit(msg[1], msg[2])

            self._msg_thread = threading.Thread(target=msg_worker, daemon=True)
            self._msg_thread.start()

            with concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {}
                for seq, (g_idx, item) in enumerate(self.indexed_queue):
                    f = executor.submit(process_pdf_item, g_idx, item, self.cfg, self.out_base, 
                                        self._pause_event, self._stop_event, io_queue, msg_queue)
                    futures[f] = (g_idx, item)
                
                for f in concurrent.futures.as_completed(futures):
                    g_idx, item = futures[f]
                    if self._stop_event.is_set():
                        for fut in futures:
                            fut.cancel()
                        break
                    try:
                        target_pages, out_folder_str, elapsed = f.result()
                        item.out_folder = out_folder_str
                        with self._lock:
                            pages += target_pages
                            done += 1
                        self.signals.file_done.emit(g_idx, elapsed)
                    except Exception as e:
                        with self._lock:
                            failed += 1
                        msg_queue.put(("file_error", g_idx, str(e)))
                    
                    with self._lock:
                        completed = done + failed
                        now = time.time()
                        if now - self._last_ui_update > 0.033 or completed == total:
                            pct = int((completed) / total * 100) if total else 100
                            self.signals.overall_progress.emit(completed, total, pct)
                            self._last_ui_update = now

            io_queue.put(None)
            self._io_thread.join()
            msg_queue.put(None)
            self._msg_thread.join()

            self.signals.all_done.emit({
                "done": done, "failed": failed, "pages": pages,
                "elapsed": time.time() - t_start, "stopped": self._stop_event.is_set(),
            })


# ======================================================================
# CONFIG
# ======================================================================
class Config:
    def __init__(self):
        self.d = dict(DEFAULT_CFG)
        self._load()

    def _load(self):
        first_run = not CONFIG_PATH.exists()
        if not first_run:
            try:
                with open(CONFIG_PATH,"r",encoding="utf-8") as f:
                    self.d.update(json.load(f))
            except Exception:
                pass
        else:
            if platform.system() == "Windows":
                try:
                    set_autostart(True)
                except:
                    pass
            self.save()

    def save(self):
        try:
            temp_path = CONFIG_PATH.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.d, f, ensure_ascii=False, indent=2)
            temp_path.replace(CONFIG_PATH)
        except Exception:
            pass

    def get(self, k, default=None):
        return self.d.get(k, default if default is not None else DEFAULT_CFG.get(k))

    def set(self, k, v):
        self.d[k] = v
        self.save()

    def update(self, d: dict):
        self.d.update(d)
        self.save()


# ======================================================================
# MAIN WINDOW
# ======================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Ensure Background Service is running
        from PyQt6.QtNetwork import QLocalSocket
        socket = QLocalSocket()
        socket.connectToServer("PDFToImageService_V2")
        if not socket.waitForConnected(200):
            import subprocess, sys
            env = os.environ.copy()
            env.pop("_MEIPASS2", None)
            cmd = [sys.executable, "--action", "background"] if getattr(sys, 'frozen', False) else [sys.executable, os.path.abspath(__file__), "--action", "background"]
            subprocess.Popen(cmd, env=env)
        else:
            socket.disconnectFromServer()
        self.cfg     = Config()
        self._dark   = self.cfg.get("theme","dark") == "dark"
        self._worker: ConversionWorker | None = None
        self._model  = QueueTableModel()

        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
        
        # Đọc trạng thái cập nhật từ config (do BackgroundService kiểm tra)
        if self.cfg.get("update_status") == "available" and self.cfg.get("update_latest_version"):
            self.update_url = self.cfg.get("update_url", "")
            self.latest_version = self.cfg.get("update_latest_version", "")
        
        # --- ICON CHO PHẦN MỀM ---
        def resource_path(relative_path):
            import sys, os
            if hasattr(sys, '_MEIPASS'):
                return os.path.join(sys._MEIPASS, relative_path)
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)
        
        try:
            from PyQt6.QtGui import QIcon
            self.setWindowIcon(QIcon(resource_path("app_icon.ico")))
        except Exception:
            pass
        
        # Get available screen geometry to prevent overflow
        screen = QApplication.primaryScreen()
        av_geom = screen.availableGeometry() if screen else QRect(0, 0, 1366, 768)
        
        w = min(self.cfg.get("win_w", 1300), int(av_geom.width() * 0.9))
        h = min(self.cfg.get("win_h", 800), int(av_geom.height() * 0.85))
        self.resize(w, h)
        
        min_w = min(800, int(av_geom.width() * 0.8))
        min_h = min(500, int(av_geom.height() * 0.7))
        self.setMinimumSize(min_w, min_h)
        
        self.setAcceptDrops(True)

        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(min(4, os.cpu_count() or 2))

        self._setup_ui()
        self._apply_theme()
        self._load_state()
        self._state_loaded = True

        # Thống kê hệ thống thời gian thực (CPU/RAM)
        self._main_proc = psutil.Process(os.getpid())
        self._child_procs = {}
        self._last_stats_txt = "  "
        self._last_progress_info = (0, 0, 0)
        
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(500)
        self._update_stats()

    # ── UI BUILD ──────────────────────────────────────────────────────
    def _setup_ui(self):
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        
        # Hiện dấu chấm đỏ nếu có bản cập nhật
        if self.cfg.get("update_status") == "available":
            self.show_update_indicator()

    # ── TOOLBAR (cài đặt nhanh + actions) ────────────────────────────
    def _build_toolbar(self):
        tb = QToolBar("main_toolbar")
        tb.setMovable(False)
        tb.setFloatable(False)
        self.addToolBar(tb)
        self._tb = tb

        def sep(): tb.addSeparator()

        # ── Thêm file / thư mục
        self._act_add_file   = self._tb_btn(tb, "📄 Thêm file",    self._add_files,  "Thêm file PDF vào hàng chờ (Ctrl+O)")
        self._act_add_folder = self._tb_btn(tb, "📁 Thêm thư mục", self._add_folder, "Thêm toàn bộ PDF trong thư mục")
        
        # ── Định dạng
        lbl_fmt = QLabel(" Định dạng:")
        tb.addWidget(lbl_fmt)
        self.cb_format = QComboBox()
        for f in FORMATS:
            self.cb_format.addItem(f)
        self.cb_format.setToolTip("Định dạng ảnh đầu ra")
        self.cb_format.setFixedWidth(72)
        self.cb_format.currentTextChanged.connect(self._on_fmt_changed)
        tb.addWidget(self.cb_format)

        # ── DPI
        lbl_dpi = QLabel("  DPI:")
        tb.addWidget(lbl_dpi)
        self.cb_dpi = QComboBox()
        self.cb_dpi.setEditable(False)
        self.cb_dpi.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for lbl, val in DPI_OPTIONS:
            self.cb_dpi.addItem(lbl, val)
        self.cb_dpi.addItem("Tùy chỉnh...", -1)
        self.cb_dpi.setToolTip("Độ phân giải xuất ảnh")
        self.cb_dpi.setFixedWidth(120)
        self.cb_dpi.activated.connect(self._on_dpi_activated)
        tb.addWidget(self.cb_dpi)

        # ── Quality slider
        self.lbl_qual = QLabel("  Chất lượng:")
        tb.addWidget(self.lbl_qual)
        self.sld_qual = QSlider(Qt.Orientation.Horizontal)
        self.sld_qual.setRange(10, 100)
        self.sld_qual.setFixedWidth(90)
        self.sld_qual.setToolTip("Chất lượng nén (chỉ JPG/WebP)")
        self.sld_qual.setSingleStep(5)
        self.sld_qual.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.sld_qual.setTickInterval(5)
        tb.addWidget(self.sld_qual)

        self.spin_qual = QSpinBox()
        self.spin_qual.setRange(10, 100)
        self.spin_qual.setSingleStep(5)
        self.spin_qual.setFixedWidth(65)
        self.spin_qual.setObjectName("qual_spin")
        tb.addWidget(self.spin_qual)

        def _sync_quality(v):
            val = round(v / 5) * 5
            self.sld_qual.blockSignals(True)
            self.sld_qual.setValue(val)
            self.sld_qual.blockSignals(False)
            if self.spin_qual.value() != val:
                self.spin_qual.setValue(val)
            self._on_quality_changed(val)

        self.sld_qual.valueChanged.connect(_sync_quality)
        self.spin_qual.valueChanged.connect(self.sld_qual.setValue)

        def _trigger_preview_reload():
            self._save_quick_cfg()
            if hasattr(self, "preview_panel") and self.preview_panel._current_item:
                self.preview_panel._pdf = "" # Force reload
                self.preview_panel.load_pdf(self.preview_panel._current_item)

        # ── Format (Doesn't affect rendering but we sync it)
        self.cb_format.currentTextChanged.connect(lambda _: _trigger_preview_reload())
        
        # ── DPI
        self.cb_dpi.currentIndexChanged.connect(lambda _: _trigger_preview_reload())

        # ── Quality
        self.sld_qual.sliderReleased.connect(_trigger_preview_reload)
        self.spin_qual.editingFinished.connect(_trigger_preview_reload)

        # ── Color Mode
        lbl_color = QLabel("  Màu sắc:")
        tb.addWidget(lbl_color)
        self.cb_color = QComboBox()
        self.cb_color.addItem("Màu (RGB)", "color")
        self.cb_color.addItem("Trắng đen", "grayscale")
        self.cb_color.setToolTip("Chế độ màu của ảnh xuất ra")
        self.cb_color.setFixedWidth(120)
        self.cb_color.currentIndexChanged.connect(lambda _: _trigger_preview_reload())
        tb.addWidget(self.cb_color)

        self.addToolBarBreak()
        
        tb2 = QToolBar("settings_toolbar")
        tb2.setMovable(False)
        tb2.setFloatable(False)
        self.addToolBar(tb2)
        def sep2(): tb2.addSeparator()

        # ── Output path (inline)
        lbl_out = QLabel(" Lưu vào:")
        tb2.addWidget(lbl_out)
        self.inp_out = QLineEdit()
        self.inp_out.setPlaceholderText("Tự động (cùng thư mục PDF)")
        self.inp_out.setFixedWidth(200)
        self.inp_out.setToolTip("Thư mục lưu ảnh. Để trống = tạo thư mục 'PDF to Image' cạnh file PDF")
        self.inp_out.editingFinished.connect(self._save_quick_cfg)
        tb2.addWidget(self.inp_out)
        self._act_pick_out = self._tb_btn(tb2, "📂", self._pick_output, "Chọn thư mục lưu ảnh")
        self._act_default_out = self._tb_btn(tb2, "🔄", self._reset_output, "Khôi phục mặc định")

        # ── Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb2.addWidget(spacer)

        # ── Start / Stop
        self._act_start = self._tb_btn(tb2, "▶  Bắt đầu", self._start_or_pause, "Bắt đầu chuyển đổi (Ctrl+Enter)")
        self._act_stop  = self._tb_btn(tb2, "■  Dừng lại", self._stop_worker, "Dừng sau trang hiện tại (Ctrl+.)")
        tb2.widgetForAction(self._act_start).setObjectName("act_start")
        tb2.widgetForAction(self._act_stop).setObjectName("act_stop")
        self._act_stop.setEnabled(False)

        sep2()

        # ── Cài đặt nâng cao (dùng BadgeToolButton để hiển thị dấu chấm đỏ)
        self._act_settings = QAction("⚙", self)
        self._act_settings.setToolTip("Cài đặt nâng cao")
        self._act_settings.triggered.connect(self._open_settings)
        self._badge_btn = BadgeToolButton()
        self._badge_btn.setDefaultAction(self._act_settings)
        tb2.addWidget(self._badge_btn)

        # ── Theme toggle
        self._act_theme = self._tb_btn(tb2, "🌙", self._toggle_theme, "Chuyển Dark/Light")

    def _tb_btn(self, tb: QToolBar, text: str, slot, tip: str = "") -> QAction:
        act = QAction(text, self)
        if tip: act.setToolTip(tip)
        act.triggered.connect(slot)
        tb.addAction(act)
        return act

    # ── CENTRAL ──────────────────────────────────────────────────────
    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # ── Sidebar (queue + drop zone) ──
        sidebar = QWidget(); sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(320); sidebar.setMaximumWidth(520)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0,0,0,0); sl.setSpacing(0)
        sidebar.setAcceptDrops(True)

        # Queue header
        qhdr = QWidget(); qhdr.setFixedHeight(30)
        qhl  = QHBoxLayout(qhdr); qhl.setContentsMargins(10, 0, 6, 0); qhl.setSpacing(4)
        self.lbl_queue = QLabel("HÀNG CHỜ (0)"); self.lbl_queue.setObjectName("sec_lbl")
        
        btn_remove_done = QPushButton("Xóa xong"); btn_remove_done.setFixedHeight(24)
        btn_remove_done.setToolTip("Xoá các file đã chuyển đổi xong khỏi danh sách")
        btn_remove_done.clicked.connect(self._remove_done)
        btn_remove_done.setStyleSheet("padding: 2px 6px; font-size: 11px;")
        
        btn_clear_all = QPushButton("Xóa tất cả"); btn_clear_all.setFixedHeight(24)
        btn_clear_all.setToolTip("Xoá toàn bộ hàng chờ")
        btn_clear_all.clicked.connect(self._clear_queue)
        btn_clear_all.setStyleSheet("padding: 2px 6px; font-size: 11px;")
        
        qhl.addWidget(self.lbl_queue); qhl.addStretch()
        qhl.addWidget(btn_remove_done); qhl.addWidget(btn_clear_all)
        sl.addWidget(qhdr)

        # Queue table
        self.table = QTableView()
        self.table.setObjectName("queue_table")
        self.table.setModel(self._model)
        self.table.setItemDelegate(QueueDelegate(lambda: self._dark, self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setHighlightSections(False)

        # Cột widths
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(COL_NAME,   QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_PROG,   QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(COL_STATUS, 100)
        self.table.setColumnWidth(COL_PROG,   90)
        self.table.verticalHeader().setDefaultSectionSize(QueueDelegate.ROW_H)

        self.table.selectionModel().selectionChanged.connect(self._on_table_selection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._queue_context_menu)
        sl.addWidget(self.table, 1)

        # ── Main right (tabs) ──
        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True)

        self.preview_panel = PreviewPanel(lambda: self._dark)
        self.log_panel     = LogPanel()
        self.history_panel = HistoryPanel()
        self.history_panel.open_folder.connect(self._open_folder)

        self.tabs.addTab(self.preview_panel, "🔍  Xem trước")
        self.tabs.addTab(self.log_panel,     "📋  Nhật ký")
        self.tabs.addTab(self.history_panel, "🕐  Lịch sử")

        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(sidebar)
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setHandleWidth(1)
        sizes = self.cfg.get("splitter", [300, 1000])
        self.splitter.setSizes(sizes)

        root.addWidget(self.splitter)

    # ── STATUSBAR ─────────────────────────────────────────────────────
    def _build_statusbar(self):
        sb = QStatusBar(); self.setStatusBar(sb)
        self.sb_msg  = QLabel("Sẵn sàng.")
        self.sb_info = QLabel("  Đã xử lý 0/0 file - 0%  ")
        self.sb_info.setToolTip("Hiển thị tổng lượng CPU và RAM phần mềm đang tiêu thụ (bao gồm tất cả tiến trình con)")
        self.sb_pbar = QProgressBar()
        self.sb_pbar.setFixedSize(160, 5)
        self.sb_pbar.setTextVisible(False)
        self.sb_pbar.setValue(0)
        sb.addWidget(self.sb_msg)
        sb.addPermanentWidget(self.sb_info)
        sb.addPermanentWidget(self.sb_pbar)

    # ── THEME ─────────────────────────────────────────────────────────
    def _apply_theme(self):
        qss = build_qss(self._dark)
        self.setStyleSheet(qss)
        lbl = "Sáng" if self._dark else "Tối"
        self._act_theme.setText(lbl)
        self.log_panel.update_theme(self._dark)
        self.preview_panel.update_theme()
        set_titlebar_theme(self.winId(), self._dark)

    def _toggle_theme(self):
        self._dark = not self._dark
        self.cfg.set("theme", "dark" if self._dark else "light")
        self._apply_theme()

    # ── LOAD / SAVE ───────────────────────────────────────────────────
    def _load_state(self):
        c = self.cfg
        
        self.cb_format.blockSignals(True)
        self.cb_dpi.blockSignals(True)
        self.sld_qual.blockSignals(True)
        self.spin_qual.blockSignals(True)
        self.inp_out.blockSignals(True)

        self.cb_color.blockSignals(True)

        # toolbar widgets
        fmt = c.get("format","PNG")
        idx = self.cb_format.findText(fmt)
        if idx >= 0: self.cb_format.setCurrentIndex(idx)
        self._on_fmt_changed(fmt)  # manual call

        c_mode = c.get("color_mode","color")
        idx = self.cb_color.findData(c_mode)
        if idx >= 0: self.cb_color.setCurrentIndex(idx)

        dpi = c.get("dpi", 300)
        idx = self.cb_dpi.findData(dpi)
        if idx >= 0:
            self.cb_dpi.setCurrentIndex(idx)
        else:
            custom_idx = self.cb_dpi.findData(-1)
            if custom_idx < 0: custom_idx = self.cb_dpi.count()
            self.cb_dpi.insertItem(custom_idx, f"{dpi} — Tùy chỉnh", dpi)
            while self.cb_dpi.count() > len(DPI_OPTIONS) + 4:
                self.cb_dpi.removeItem(len(DPI_OPTIONS))
            self.cb_dpi.setCurrentIndex(self.cb_dpi.findData(dpi))

        qual = c.get("quality", 100)
        self.sld_qual.setValue(qual)
        self.spin_qual.setValue(qual)
        # self.inp_out.setText(c.get("output_path",""))

        self.cb_format.blockSignals(False)
        self.cb_dpi.blockSignals(False)
        self.sld_qual.blockSignals(False)
        self.spin_qual.blockSignals(False)
        self.inp_out.blockSignals(False)
        self.cb_color.blockSignals(False)

        # history
        self.history_panel.load(c.get("history", []))
        self._update_queue_label()

    def _save_state(self):
        self.cfg.d["history"] = self.history_panel.dump()
        self.cfg.d["splitter"] = self.splitter.sizes()
        self.cfg.d["win_w"]   = self.width()
        self.cfg.d["win_h"]   = self.height()
        self.cfg.save()

    def _save_quick_cfg(self):
        if not getattr(self, '_state_loaded', False):
            return
        try:
            dpi_val = int(self.cb_dpi.currentText().split()[0])
        except:
            dpi_val = 300
            
        self.cfg.d["format"]     = self.cb_format.currentText()
        self.cfg.d["dpi"]        = dpi_val
        self.cfg.d["quality"]    = self.sld_qual.value()
        self.cfg.d["color_mode"] = self.cb_color.currentData()
        # output_path is intentionally NOT saved to config so it defaults to empty on next launch
        self.cfg.save()

    def _get_conversion_cfg(self) -> dict:
        adv = {k: self.cfg.get(k) for k in (
            "size_limit","name_pattern",
            "watermark_on","watermark","zip_output","auto_open","show_time",
            "performance",
        )}
        try:
            dpi_val = int(self.cb_dpi.currentText().split()[0])
        except:
            dpi_val = 300
            
        adv.update({
            "format":     self.cb_format.currentText(),
            "dpi":        dpi_val,
            "quality":    self.sld_qual.value(),
            "color_mode": self.cb_color.currentData(),
        })
        return adv

    # ── QUICK CFG CALLBACKS ───────────────────────────────────────────

    def _on_dpi_activated(self, idx: int):
        if self.cb_dpi.itemData(idx) == -1:
            self.cb_dpi.setEditable(True)
            le = self.cb_dpi.lineEdit()
            le.setCompleter(None)
            le.setInputMethodHints(Qt.InputMethodHint.ImhDigitsOnly)
            le.setValidator(QIntValidator(0, 999999, self))
            le.setPlaceholderText("1 - 2400")
            le.setText("")
            le.setFocus()
            try: le.editingFinished.disconnect()
            except: pass
            le.editingFinished.connect(self._on_dpi_editing_finished)
        else:
            self.cb_dpi.setEditable(False)

    def _on_dpi_editing_finished(self):
        le = self.cb_dpi.lineEdit()
        if not le: return
        txt = le.text().strip()
        self.cb_dpi.setEditable(False)
        if not txt:
            self.cb_dpi.setCurrentIndex(3)
            return
            
        try:
            val = int(txt)
        except:
            self.cb_dpi.setCurrentIndex(3)
            return

        if val <= 0:
            QMessageBox.warning(self, "Lỗi nhập liệu", "Mức DPI không được nhỏ hơn 1!\n\nPhần mềm sẽ tự động chọn mức mặc định là 300 DPI.")
            self.cb_dpi.setCurrentIndex(3)
            return

        if val > 2400:
            QMessageBox.warning(self, "Vượt quá giới hạn phần cứng", 
                f"Mức DPI {val} là quá lớn và có thể gây tràn bộ nhớ!\n\n"
                "Giải thích kỹ thuật: Ở mức DPI này, một trang PDF thông thường sẽ tạo ra bức ảnh có kích thước lên tới hàng trăm nghìn pixel, "
                "tiêu tốn hàng chục Gigabyte RAM chỉ cho một trang duy nhất. Hệ thống sẽ ngay lập tức bị treo hoặc thoát đột ngột (MemoryError).\n\n"
                "Phần mềm sẽ tự động điều chỉnh về giới hạn an toàn tối đa là 2400 DPI.")
            val = 2400
            
        lbl = f"{val} — Tùy chỉnh"
        exist = self.cb_dpi.findData(val)
        if exist >= 0 and exist != self.cb_dpi.count() - 1:
            self.cb_dpi.setCurrentIndex(exist)
        else:
            custom_idx = self.cb_dpi.findData(-1)
            if custom_idx < 0: custom_idx = self.cb_dpi.count()
            self.cb_dpi.insertItem(custom_idx, lbl, val)
            while self.cb_dpi.count() > len(DPI_OPTIONS) + 4:
                self.cb_dpi.removeItem(len(DPI_OPTIONS))
            self.cb_dpi.setCurrentIndex(self.cb_dpi.findData(val))

    def _on_fmt_changed(self, fmt: str):
        enabled = fmt in ("JPG","WebP")
        self.sld_qual.setEnabled(enabled)
        self.spin_qual.setEnabled(enabled)
        self.lbl_qual.setEnabled(enabled)

    def _on_quality_changed(self, v: int):
        self._save_quick_cfg()

    def _reset_output(self):
        self.inp_out.clear()
        self._save_quick_cfg()

    def _pick_output(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu ảnh")
        if d:
            self.inp_out.setText(d)
            self._save_quick_cfg()

    def show_update_indicator(self):
        self.has_update = True
        if hasattr(self, '_act_settings'):
            self._act_settings.setText("⚙ Cài đặt")
            self._act_settings.setToolTip("Cài đặt nâng cao")
        if hasattr(self, '_badge_btn'):
            self._badge_btn.setBadgeVisible(True)

    def hide_update_indicator(self):
        self.has_update = False
        if hasattr(self, '_act_settings'):
            self._act_settings.setText("⚙")
            self._act_settings.setToolTip("Cài đặt nâng cao")
        if hasattr(self, '_badge_btn'):
            self._badge_btn.setBadgeVisible(False)

    # ── SETTINGS DIALOG ───────────────────────────────────────────────
    def _open_settings(self):
        dlg = SettingsDialog(self.cfg.d, self)
        dlg.setStyleSheet(build_qss(self._dark))
        set_titlebar_theme(dlg.winId(), self._dark)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cfg.update(dlg.get_values())

    # ── ADD FILES ─────────────────────────────────────────────────────
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Chọn file PDF", "", "PDF Files (*.pdf)"
        )
        if paths:
            self._enqueue(paths)

    def _add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa PDF")
        if d:
            self._enqueue([d])

    def _enqueue(self, paths: list[str]):
        existing = self._model.existing_paths()
        new_items = []
        for p in paths:
            p = str(Path(p))
            if os.path.isfile(p) and p.lower().endswith(".pdf"):
                if p not in existing:
                    new_items.append(QueueItem(p, group_name=None))
                    existing.add(p)
            elif os.path.isdir(p):
                group = Path(p).name
                for fn in sorted(os.listdir(p)):
                    fp = str(Path(p) / fn)
                    if fp.lower().endswith(".pdf") and fp not in existing:
                        new_items.append(QueueItem(fp, group_name=group))
                        existing.add(fp)

        if not new_items:
            return
        self._model.add_items(new_items)
        self._update_queue_label()

        # Scan page counts in background (không block UI)
        start_idx = self._model.rowCount() - len(new_items)
        def _scan():
            for i, it in enumerate(new_items):
                try:
                    doc = fitz.open(it.path)
                    it.pages = len(doc)
                    doc.close()
                except Exception:
                    pass
                QTimer.singleShot(0, lambda idx=start_idx+i: self._model.update_row(idx))
        Thread(target=_scan, daemon=True).start()

    def _clear_queue(self):
        self._model.clear()
        self.preview_panel.clear()
        self._update_queue_label()

    def _remove_done(self):
        self._model.remove_done()
        self._update_queue_label()

    def _update_queue_label(self):
        n = self._model.rowCount()
        self.lbl_queue.setText(f"HÀNG CHỜ ({n})")
        self.sb_info.setText(f"  {n} file" if n else "")

    # ── TABLE SELECTION → PREVIEW ─────────────────────────────────────
    def _on_table_selection(self, selected, deselected):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        row  = rows[0].row()
        item = self._model.get_item(row)
        if item:
            self.tabs.setCurrentIndex(0)
            self.preview_panel.load_pdf(item)
            # Auto set output path if empty
            if not self.inp_out.text().strip():
                parent_dir = str(Path(item.path).parent / "PDF to Image")
                # Don't set in inp_out, just use as default at conversion time

    # ── CONTEXT MENU ──────────────────────────────────────────────────
    def _queue_context_menu(self, pos):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        menu = QMenu(self)
        menu.addAction("🗑  Xoá khỏi hàng chờ", lambda: self._remove_selected(rows))
        menu.addAction("📂  Mở thư mục chứa file", lambda: self._open_selected_folder(rows))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _remove_selected(self, rows):
        for r in sorted([r.row() for r in rows], reverse=True):
            self._model.beginRemoveRows(QModelIndex(), r, r)
            self._model.all_items().pop(r)
            self._model.endRemoveRows()
        self._update_queue_label()

    def _open_selected_folder(self, rows):
        if rows:
            item = self._model.get_item(rows[0].row())
            if item:
                self._open_folder(str(Path(item.path).parent))

    # ── START / PAUSE / STOP ──────────────────────────────────────────
    def _start_or_pause(self):
        if self._worker and self._worker.isRunning():
            if self._worker._pause:
                # Resume
                self._worker.resume()
                self._act_start.setText("⏸  Tạm dừng")
                self.sb_msg.setText("⏳  Đang tiếp tục...")
            else:
                # Pause
                self._worker.pause()
                self._act_start.setText("▶  Tiếp tục")
                self.sb_msg.setText("⏸  Đã tạm dừng")
            return

        # Start new
        pending = self._model.pending_items()
        if not pending:
            QMessageBox.information(self, "Hàng chờ", "Không có file nào cần xử lý.")
            return

        cfg      = self._get_conversion_cfg()
        out_base = self.inp_out.text().strip()
        is_auto  = not out_base
        
        # Confirmation Dialog
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Xác nhận Bắt đầu")
        set_titlebar_theme(msg_box.winId(), self._dark)
        
        info_txt = "• File thêm lẻ sẽ được lưu ra thư mục/file nén riêng.\n"
        info_txt += "• File thêm bằng nút 'Thêm thư mục' sẽ được gộp chung.\n\n"
        info_txt += "Nhấn Enter để Bắt đầu, Esc để Hủy."

        if is_auto:
            msg_box.setText("Bạn đang chọn chế độ lưu <b>Tự động (Cùng thư mục PDF gốc)</b>.")
            msg_box.setInformativeText(info_txt)
        else:
            msg_box.setText("Bạn đang chọn vị trí lưu <b>Tùy chỉnh</b>.")
            msg_box.setInformativeText(f"Ảnh sẽ được xuất ra thư mục:\n<b>{out_base}</b>\n\n" + info_txt)
        
        btn_start = msg_box.addButton("▶ Bắt đầu", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = msg_box.addButton("Hủy", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(btn_start)
        msg_box.setEscapeButton(btn_cancel)
        msg_box.exec()
        
        if msg_box.clickedButton() != btn_start:
            return

        self.log_panel.clear()
        self.tabs.setCurrentIndex(1)
        self.sb_pbar.setValue(0)
        
        self._last_progress_info = (0, len(pending), 0)
        self.sb_pbar.show()
        self._set_running(True)

        # Reset status
        for g_idx, item in pending:
            item.status   = STATUS_PENDING
            item.progress = 0
            self._model.update_row(g_idx)

        self._worker = ConversionWorker(pending, cfg, out_base)
        sig = self._worker.signals
        sig.overall_progress.connect(self._on_overall_progress)
        sig.file_started.connect(self._on_file_started)
        sig.file_progress.connect(self._on_file_progress)
        sig.file_done.connect(self._on_file_done)
        sig.file_error.connect(self._on_file_error)
        sig.log_message.connect(self.log_panel.append)
        sig.log_batch.connect(self.log_panel.append_batch)
        sig.all_done.connect(self._on_all_done)

        self._t0 = time.time()
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._elapsed_timer.start(200)
        self._act_start.setText("⏸  Tạm dừng")
        self._worker.start()

    def _stop_worker(self):
        if self._worker:
            self._worker.request_stop()
            self._act_start.setText("▶  Bắt đầu")
            self.sb_msg.setText("⏸  Đang dừng...")

    def _set_running(self, running: bool):
        self._act_stop.setEnabled(running)
        w_stop  = self._tb.widgetForAction(self._act_stop)
        if w_stop:  w_stop.setEnabled(running)

    def _update_stats(self):
        try:
            mem = self._main_proc.memory_info().rss
            cpu = self._main_proc.cpu_percent(interval=None)
            
            current_children = self._main_proc.children(recursive=True)
            current_pids = {c.pid for c in current_children}
            self._child_procs = {pid: p for pid, p in self._child_procs.items() if pid in current_pids}
            
            for c in current_children:
                if c.pid not in self._child_procs:
                    self._child_procs[c.pid] = c
                    c.cpu_percent(interval=None)
            
            for pid, child in self._child_procs.items():
                try:
                    mem += child.memory_info().rss
                    cpu += child.cpu_percent(interval=None)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                    
            mem_mb = mem / 1048576
            total_gb = psutil.virtual_memory().total / 1073741824
            cpu_total = cpu / (psutil.cpu_count() or 1)
            
            self._last_stats_txt = f"  CPU: {cpu_total:.1f}%  |  RAM: {mem_mb:.0f} MB / {total_gb:.1f} GB  | "
        except Exception:
            self._last_stats_txt = "  "
            
        c, t, p_ct = getattr(self, '_last_progress_info', (0, 0, 0))
        prog_txt = f"  Đã xử lý {c}/{t} file - {p_ct}%  " if t > 0 else "  Đã xử lý 0/0 file - 0%  "
        self.sb_info.setText(self._last_stats_txt + prog_txt)

    def _tick_elapsed(self):
        e = int(time.time() - self._t0)
        self.sb_msg.setText(f"⏳  Đang xử lý...  {e}s")
        # _update_stats runs independently via _stats_timer, no need to update sb_info here

    # ── WORKER SLOTS ──────────────────────────────────────────────────
    @pyqtSlot(int, int, int)
    def _on_overall_progress(self, done: int, total: int, pct: int):
        self.sb_pbar.setValue(pct)
        self._last_progress_info = (done, total, pct)
        self._update_stats()

    @pyqtSlot(int)
    def _on_file_started(self, g_idx: int):
        item = self._model.get_item(g_idx)
        if item:
            item.status   = STATUS_PROCESSING
            item.progress = 0
            self._model.update_row(g_idx)
            self.sb_msg.setText(f"⏳  {item.name}")

    @pyqtSlot(int, int)
    def _on_file_progress(self, g_idx: int, pct: int):
        item = self._model.get_item(g_idx)
        if item:
            item.progress = pct
            self._model.update_row(g_idx)

    @pyqtSlot(int, float)
    def _on_file_done(self, g_idx: int, elapsed: float):
        item = self._model.get_item(g_idx)
        if item:
            item.status   = STATUS_DONE
            item.progress = 100
            item.elapsed  = elapsed
            self._model.update_row(g_idx)
            cfg = self._get_conversion_cfg()
            self.history_panel.add(HistoryItem(
                name=item.name, pages=item.pages,
                fmt=cfg["format"], dpi=cfg["dpi"],
                out=item.out_folder, elapsed=elapsed,
                ts=datetime.now().strftime("%d/%m %H:%M"),
                color="màu trắng đen" if cfg.get("color_mode") == "grayscale" else "màu RGB"
            ))

    @pyqtSlot(int, str)
    def _on_file_error(self, g_idx: int, msg: str):
        item = self._model.get_item(g_idx)
        if item:
            item.status    = STATUS_ERROR
            item.error_msg = msg
            self._model.update_row(g_idx)
        self.log_panel.append(
            f'<span class="err">✗  {item.name if item else f"File {g_idx}"}  —  {msg}</span>'
        )

    @pyqtSlot(dict)
    def _on_all_done(self, summary: dict):
        if hasattr(self, "_elapsed_timer"):
            self._elapsed_timer.stop()
        self._set_running(False)
        self._act_start.setText("▶  Bắt đầu")
        self.sb_pbar.setValue(100)

        if summary["stopped"]:
            for i, it in enumerate(self._model._items):
                if it.status == STATUS_PROCESSING:
                    it.status = STATUS_PENDING
                    it.progress = 0
                    self._model.update_row(i)

        mins, secs = divmod(int(summary["elapsed"]), 60)
        ts = f"{mins}p {secs}s" if mins else f"{secs}s"
        icon = "⏸" if summary["stopped"] else "✔"
        label = "Đã dừng" if summary["stopped"] else "Hoàn thành"
        fail_s = f", {summary['failed']} lỗi" if summary["failed"] else ""
        self.sb_msg.setText(
            f"{icon}  {label}  ·  {summary['done']} file{fail_s}  ·  {summary['pages']} trang  ·  {ts}"
        )
        self.log_panel.append_summary(
            f"{icon} {label}  —  {summary['done']} file{fail_s}  ·  "
            f"{summary['pages']} trang  ·  {ts}"
        )

        cfg = self._get_conversion_cfg()

        # Auto open
        if cfg.get("auto_open") and not summary["stopped"]:
            out_base = self.inp_out.text().strip() or ""
            if out_base:
                QTimer.singleShot(600, lambda: self._open_folder(out_base))

        self._save_state()

    # ── OPEN FOLDER ───────────────────────────────────────────────────
    def _open_folder(self, path: str):
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Không tìm thấy", f"Thư mục không tồn tại:\n{path}")
            return
        s = platform.system()
        if s == "Windows":   os.startfile(path)
        elif s == "Darwin":  subprocess.Popen(["open", path])
        else:                subprocess.Popen(["xdg-open", path])

    # ── DRAG & DROP ───────────────────────────────────────────────────
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        self._enqueue(paths)

    # ── KEYBOARD ──────────────────────────────────────────────────────
    def keyPressEvent(self, e):
        if e.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if e.key() == Qt.Key.Key_O:
                self._add_files(); return
            if e.key() == Qt.Key.Key_Return:
                self._start(); return
            if e.key() == Qt.Key.Key_Period:
                self._stop_worker(); return
        super().keyPressEvent(e)

    # ── CLOSE ─────────────────────────────────────────────────────────
    def closeEvent(self, e):
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self, "Đang xử lý", "Đang chuyển đổi. Dừng và thoát?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                e.ignore(); return
            self._worker.request_stop()
            self._worker.wait(2000)
        self._save_state()
        self.deleteLater()
        e.accept()


class AnimatedSplashScreen(QWidget):
    def __init__(self, main_win_class):
        super().__init__()
        self.main_win_class = main_win_class
        self.main_win_instance = None
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.SplashScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(540, 320)
        
        self._time = 0.0
        self._current_log = "Khởi tạo môi trường..."
        
        import time
        self._start_time = time.time()
        
        # Khởi tạo màu nền ngẫu nhiên và hạt ánh sáng
        import random
        import math
        self._glow_hue = random.randint(0, 359)
        self._is_loading_main = False
        self._main_ready = False
        self._particles = []
        for _ in range(25):
            self._particles.append({
                'angle': random.uniform(0, 2 * math.pi),
                'speed': random.uniform(40.0, 160.0),
                'size': random.uniform(2.0, 5.5),
                'delay': random.uniform(2.6, 4.0),
                'life': random.uniform(1.2, 3.0)
            })
            
        self._update_checked = False
        self._update_finished_time = 0
        self._update_result_msg = ""
        
        cfg = Config()
        if cfg.get("auto_check_update", True):
            self._bg_update_checker = UpdateCheckerThread()
            self._bg_update_checker.update_result.connect(self._on_update_result)
            self._bg_update_checker.start()
        else:
            self._update_checked = True
            self._update_finished_time = -10
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(1000 // 60)

        # Tạo MainWindow bắt đầu ở t≈5s (sau khi animation hoàn tất)
        # Vừa chạy animation, vừa tạo UI — song song hóa thực sự
        QTimer.singleShot(5000, self._start_loading_main)
        
    def _on_update_result(self, has_update, version, url, published_at, body):
        self._update_checked = True
        import time
        self._update_finished_time = time.time()
        
        cfg = Config()
        if has_update:
            self._update_result_msg = f"Đã tìm thấy bản cập nhật mới v{version}!"
            cfg.update({
                "update_status": "available",
                "update_latest_version": version,
                "update_url": url,
                "update_published_at": published_at,
                "update_release_notes": body,
            })
        elif version:
            self._update_result_msg = "Phiên bản hiện tại đã là mới nhất."
            cfg.update({
                "update_status": "latest",
                "update_latest_version": version,
                "update_url": url,
                "update_published_at": published_at,
                "update_release_notes": body,
            })
        else:
            self._update_result_msg = "Kiểm tra cập nhật thất bại."
            cfg.update({"update_status": "error"})
        
    def showEvent(self, event):
        self._start_time = time.time()
        super().showEvent(event)
    
    def _start_loading_main(self):
        """Tạo MainWindow — chạy ở t≈3s sau khi animation cốt lõi hoàn tất."""
        if self._is_loading_main:
            return
        self._is_loading_main = True
        self._current_log = "Đang nạp giao diện đồ họa..."
        self.update()
        QApplication.processEvents()
        
        # Tạo MainWindow (block UI thread ~1-2s)
        self.main_win_instance = self.main_win_class()
        
        self._main_ready = True
        self._current_log = "Sẵn sàng!"
        self.update()
        
    def _on_tick(self):
        import time
        
        current_time = time.time()
        self._time = current_time - self._start_time
        
        MIN_SPLASH_TIME = 5.0
        
        # Cập nhật log trạng thái theo tiến trình thực tế
        if not self._is_loading_main:
            # Đang chạy animation, chưa bắt đầu tạo MainWindow
            if self._update_checked and self._update_result_msg:
                self._current_log = self._update_result_msg
            elif not self._update_checked:
                self._current_log = "Đang kiểm tra phiên bản mới..."
            else:
                self._current_log = "Đang khởi tạo hệ thống..."
        elif not self._main_ready:
            self._current_log = "Đang nạp giao diện đồ họa..."
        else:
            # MainWindow đã sẵn sàng — chờ đủ thời gian tối thiểu
            if self._time < MIN_SPLASH_TIME:
                # Hiện kết quả update nếu có, trong khi chờ đủ 5s
                if self._update_checked and self._update_result_msg:
                    self._current_log = self._update_result_msg
                else:
                    self._current_log = "Sẵn sàng!"
            else:
                # Đã qua 5s VÀ MainWindow sẵn sàng → đóng splash
                self._timer.stop()
                self._current_log = "Sẵn sàng!"
                self.update()
                QTimer.singleShot(200, self._finish_splash)
                return
        
        self.update()

    def _finish_splash(self):
        self.main_win_instance.show()
        self.close()

    def _draw_pdf_icon(self, painter):
        # Kích thước: w = 54, h = 72
        # Vẽ thân tài liệu PDF dạng đường viền bo góc có cắt góc gập 3D
        path = QPainterPath()
        path.moveTo(-27, -36 + 6)
        path.quadTo(-27, -36, -27 + 6, -36)
        path.lineTo(13, -36)
        path.lineTo(27, -22)
        path.lineTo(27, 36 - 6)
        path.quadTo(27, 36, 27 - 6, 36)
        path.lineTo(-27 + 6, 36)
        path.quadTo(-27, 36, -27, 36 - 6)
        path.closeSubpath()
        
        # Đổ màu nền đỏ gradient bóng bẩy
        grad = QLinearGradient(-27, -36, 27, 36)
        grad.setColorAt(0.0, QColor("#ef4444")) # Đỏ tươi
        grad.setColorAt(1.0, QColor("#991b1b")) # Đỏ sẫm
        painter.fillPath(path, grad)
        
        # Viền sắc nét phản chiếu
        painter.strokePath(path, QPen(QColor(255, 255, 255, 80), 1.5))
        
        # Vẽ phần góc gập giấy 3D
        flap = QPainterPath()
        flap.moveTo(13, -36)
        flap.lineTo(13, -22 + 4)
        flap.quadTo(13, -22, 13 + 4, -22)
        flap.lineTo(27, -22)
        flap.closeSubpath()
        
        # Bóng của góc gập giấy
        shadow = QPainterPath()
        shadow.moveTo(13, -22)
        shadow.lineTo(13 - 4, -22)
        shadow.lineTo(13, -22 - 4)
        shadow.closeSubpath()
        painter.fillPath(shadow, QColor(0, 0, 0, 70))
        
        flap_grad = QLinearGradient(13, -36, 27, -22)
        flap_grad.setColorAt(0.0, QColor("#fee2e2"))
        flap_grad.setColorAt(1.0, QColor("#fca5a5"))
        painter.fillPath(flap, flap_grad)
        painter.strokePath(flap, QPen(QColor(255, 255, 255, 120), 1.0))
        
        # Vẽ chữ "PDF" nổi bật ở giữa
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.setPen(QColor("white"))
        painter.drawText(QRectF(-22, -10, 44, 15), Qt.AlignmentFlag.AlignCenter, "PDF")
        
        # Vẽ các vạch giả văn bản phía dưới
        painter.setPen(QPen(QColor(255, 255, 255, 160), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(-15, 10, 15, 10)
        painter.drawLine(-15, 18, 5, 18)

    def _draw_image_icon(self, painter):
        # Kích thước: w = 60, h = 60
        # Thiết kế đồng bộ với PDF icon
        w, h = 60, 60
        rect_path = QPainterPath()
        rect_path.addRoundedRect(QRectF(-w/2, -h/2, w, h), 8, 8)
        
        # Đổ màu nền xanh dương gradient
        grad = QLinearGradient(-30, -30, 30, 30)
        grad.setColorAt(0.0, QColor("#3b82f6")) # Xanh lam tươi
        grad.setColorAt(1.0, QColor("#1e3a8a")) # Xanh lam đậm
        painter.fillPath(rect_path, grad)
        
        # Viền sắc nét phản chiếu giống PDF
        painter.strokePath(rect_path, QPen(QColor(255, 255, 255, 80), 1.5))
        
        # Vẽ ông mặt trời phát sáng bằng RadialGradient
        from PyQt6.QtGui import QRadialGradient
        sun_grad = QRadialGradient(14, -14, 8)
        sun_grad.setColorAt(0.0, QColor("#fef08a")) # Vàng sáng
        sun_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(sun_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(14, -14), 8, 8)
        
        # Vẽ lõi mặt trời
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QPointF(14, -14), 4, 4)
        
        # Vẽ hai dãy núi chồng lớp (núi sau mờ hơn, núi trước rõ hơn)
        # Dãy núi 1 (phía sau)
        m1 = QPainterPath()
        m1.moveTo(-24, 24)
        m1.lineTo(-6, 2)
        m1.lineTo(12, 24)
        m1.closeSubpath()
        m1_grad = QLinearGradient(-6, 2, -6, 24)
        m1_grad.setColorAt(0.0, QColor("#60a5fa"))
        m1_grad.setColorAt(1.0, QColor("#2563eb"))
        painter.fillPath(m1, m1_grad)
        
        # Dãy núi 2 (phía trước)
        m2 = QPainterPath()
        m2.moveTo(-10, 24)
        m2.lineTo(10, -6)
        m2.lineTo(24, 24)
        m2.closeSubpath()
        m2_grad = QLinearGradient(10, -6, 10, 24)
        m2_grad.setColorAt(0.0, QColor("#93c5fd"))
        m2_grad.setColorAt(1.0, QColor("#1d4ed8"))
        painter.fillPath(m2, m2_grad)

    def _draw_arrow(self, painter):
        # Vẽ mũi tên kết nối gradient màu từ đỏ sang xanh để biểu trưng sự chuyển đổi
        arrow_pen = QPen()
        arrow_grad = QLinearGradient(-30, 0, 30, 0)
        arrow_grad.setColorAt(0.0, QColor("#fca5a5")) # Đỏ nhẹ (gần PDF)
        arrow_grad.setColorAt(0.5, QColor("#93c5fd")) # Xanh da trời
        arrow_grad.setColorAt(1.0, QColor("#60a5fa")) # Xanh sáng (gần Image)
        arrow_pen.setBrush(arrow_grad)
        arrow_pen.setWidthF(3.5)
        arrow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arrow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Thân mũi tên
        painter.drawLine(-25, 0, 20, 0)
        # Hai cánh đầu mũi tên
        painter.drawLine(10, -7, 20, 0)
        painter.drawLine(10, 7, 20, 0)
        
    def paintEvent(self, e):
        import math
        from PyQt6.QtGui import QRadialGradient
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # --- GIAI ĐOẠN 1: NỀN TỐI ĐƠN SƠ ---
        rect = QRectF(10, 10, 520, 300)
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        
        # --- HIỆU ỨNG NỀN ANIMATION (Minimalist Aurora/Gradient) ---
        t = self._time
        import math
        from PyQt6.QtGui import QRadialGradient, QLinearGradient
        
        # Tạo hiệu ứng chuyển động chậm, êm ái cho màu nền
        angle1 = t * 0.4
        angle2 = t * 0.25
        
        x1 = 270 + math.cos(angle1) * 300
        y1 = 160 + math.sin(angle1) * 200
        x2 = 270 + math.cos(angle2 + math.pi) * 300
        y2 = 160 + math.sin(angle2 + math.pi) * 200
        
        # Chuyển sắc thái nhè nhẹ (nhưng tổng thể vẫn tối giản theo tone Slate-Blue)
        hue1 = (210 + math.sin(t * 0.5) * 30) % 360 # Chuyển nhẹ quanh màu xanh
        hue2 = (240 + math.cos(t * 0.3) * 30) % 360 # Chuyển nhẹ quanh màu tím/slate
        
        bg_grad = QLinearGradient(x1, y1, x2, y2)
        bg_grad.setColorAt(0.0, QColor.fromHsv(int(hue1), 80, 80))
        bg_grad.setColorAt(1.0, QColor.fromHsv(int(hue2), 70, 50))
        
        painter.fillPath(path, bg_grad)
        
        # Tính toán màu chuyển động theo thời gian từ mã màu ngẫu nhiên ban đầu
        current_hue = (self._glow_hue + int(t * 35)) % 360
        
        # --- HIỂN THỊ CHỮ (TEXTS & LOGS) ---
        # Hiện lên sớm từ 0.5s đến 1.5s để người dùng biết app đang khởi động
        text_opacity = min(1.0, t / 0.5)
            
        painter.save()
        painter.setOpacity(text_opacity)
        # Vẽ tiêu đề phần mềm
        painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        painter.setPen(QColor("white"))
        painter.drawText(QRectF(10, 40, 520, 50), Qt.AlignmentFlag.AlignCenter, "Chuyển đổi PDF sang ảnh")
        
        # Version
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor("#94a3b8"))
        painter.drawText(QRectF(10, 75, 520, 30), Qt.AlignmentFlag.AlignCenter, f"Version {APP_VERSION}")
        
        # Khung chứa Logs nạp
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawRoundedRect(30, 265, 480, 26, 6, 6)
        
        painter.setFont(QFont("Consolas", 10))
        painter.setPen(QColor("#38bdf8"))
        painter.drawText(QRectF(40, 265, 460, 26), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"> {self._current_log}")
        painter.restore()

        # --- GIAI ĐOẠN 2: HIỆU ỨNG NỀN SÁNG ĐỘNG VÀ VIỀN SÓNG TRÒN VẼ CÙNG LÚC (t >= 2.6) ---
        # Tỏa ra từ tâm Image icon (vị trí x=335, y=150)
        if t >= 2.6:
            t_eff = t - 2.6
            
            # 1. Nền sáng động (Glow)
            glow_radius = min(420.0, t_eff * 250.0)
            base_opacity = min(0.6, t_eff / 1.0)
            pulse = math.sin(t * 3.5) * 0.04
            glow_opacity = max(0.0, min(0.7, base_opacity + pulse))
            glow_radius_dynamic = max(0.1, glow_radius * (1.0 + math.sin(t * 2.5) * 0.02))
            
            painter.save()
            painter.setClipPath(path)
            radial = QRadialGradient(335, 150, glow_radius_dynamic)
            radial.setColorAt(0.0, QColor.fromHsv(current_hue, 180, 240, int(glow_opacity * 255)))
            radial.setColorAt(0.4, QColor.fromHsv((current_hue + 30) % 360, 160, 200, int(glow_opacity * 0.4 * 255)))
            radial.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillPath(path, radial)
            painter.restore()
            
            # 2. Viền sóng tròn (Wave Blur) tán mờ nhiều
            if t_eff < 1.5:
                radius = t_eff * 380.0
                opacity = 1.0 - (t_eff / 1.5)
                painter.save()
                painter.setClipPath(path)
                
                # Vẽ nhiều vòng để tạo hiệu ứng tán mờ (blur spread)
                for i in range(5):
                    r = radius + i * 5.0
                    alpha = int(opacity * 255 * (1.0 - i / 5.0))
                    if alpha <= 0: continue
                    wave_pen = QPen(QColor.fromHsv(current_hue, 180, 255, alpha), 4.0 + i)
                    painter.setPen(wave_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QPointF(335, 150), r, r)
                    
                painter.restore()
                
        # Vẽ viền ngoài sắc nét của màn hình khởi động
        painter.setPen(QPen(QColor("#3b82f6"), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        
        # --- GIAI ĐOẠN 2: HẠT ÁNH SÁNG BAY RA (PARTICLES) ---
        if t >= 2.6:
            painter.save()
            painter.setClipPath(path)
            for p in self._particles:
                if t >= p['delay']:
                    t_age = t - p['delay']
                    if t_age < p['life']:
                        frac = t_age / p['life']
                        # Hiệu ứng bay chậm dần đều
                        ease_frac = math.sin(frac * math.pi / 2)
                        dist = ease_frac * p['speed']
                        px = 335 + math.cos(p['angle']) * dist
                        py = 150 + math.sin(p['angle']) * dist
                        
                        # Mờ dần theo thời gian sống
                        alpha = int(220 * (1.0 - frac) * (1.0 - frac))
                        p_color = QColor.fromHsv((current_hue + 15) % 360, 150, 255, alpha)
                        
                        painter.setBrush(p_color)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.drawEllipse(QPointF(px, py), p['size'], p['size'])
            painter.restore()
            
        # --- VẼ CÁC VẬT THỂ (ICONS) ---
        painter.save()
        painter.translate(270, 150) # Đặt tâm nhóm tại giữa không gian
        
        # 1. PDF Fade & Scale in (0.0s -> 0.8s)
        pdf_opacity = 0.0
        pdf_scale = 1.0
        if t < 0.8:
            prog = t / 0.8
            pdf_opacity = prog
            pdf_scale = 0.5 + 0.5 * math.sin(prog * math.pi / 2) # Pop in
        else:
            pdf_opacity = 1.0
            pdf_scale = 1.0
            
        # 2. PDF Move left (0.8s -> 1.6s)
        pdf_x = 0
        if 0.8 <= t < 1.6:
            prog = (t - 0.8) / 0.8
            ease_prog = (1 - math.cos(prog * math.pi)) / 2 # Sine ease-in-out rất mượt
            pdf_x = -65 * ease_prog
        elif t >= 1.6:
            pdf_x = -65
            
        # Vẽ PDF Icon
        painter.save()
        painter.translate(pdf_x, 0)
        painter.scale(pdf_scale, pdf_scale)
        painter.setOpacity(pdf_opacity)
        self._draw_pdf_icon(painter)
        painter.restore()
        
        # 3. Arrow Mọc dài ra (Sweep) (1.4s -> 2.2s)
        arrow_prog = 0.0
        if 1.4 <= t < 2.2:
            prog = (t - 1.4) / 0.8
            arrow_prog = math.sin(prog * math.pi / 2)
        elif t >= 2.2:
            arrow_prog = 1.0
            
        if arrow_prog > 0:
            painter.save()
            # Dùng Clip Rect để vẽ mũi tên dài dần ra từ trái sang phải
            clip_width = 45 * arrow_prog
            painter.setClipRect(QRectF(-25, -15, clip_width, 30))
            painter.setOpacity(min(1.0, arrow_prog * 3.0)) # Mờ phần mũi
            self._draw_arrow(painter)
            painter.restore()
            
        # 4. Image Icon Nảy (Spring Bounce) (2.0s -> 2.8s)
        image_prog = 0.0
        if 2.0 <= t < 2.8:
            image_prog = (t - 2.0) / 0.8
        elif t >= 2.8:
            image_prog = 1.0
            
        if image_prog > 0:
            painter.save()
            painter.translate(65, 0)
            
            # Hiệu ứng nảy lò xo (Spring Bounce)
            scale = 1.0
            if image_prog < 1.0:
                scale = 1.0 - math.cos(image_prog * math.pi * 3) * math.exp(-image_prog * 5)
            
            scale = max(0.001, scale)
            painter.scale(scale, scale)
            painter.setOpacity(min(1.0, image_prog * 2.5))
            self._draw_image_icon(painter)
            painter.restore()
            
        painter.restore()
        
        painter.end()



# ======================================================================
# BACKGROUND SERVICE & IPC
# ======================================================================
class UpdateCheckerThread(QThread):
    update_result = pyqtSignal(bool, str, str, str, str)

    def run(self):
        import urllib.request
        import json
        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/ybao2004/pdf-to-image/releases/latest",
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                latest_version = data.get("tag_name", "").replace("v", "")
                body = data.get("body", "")
                url = data.get("html_url", "https://github.com/ybao2004/pdf-to-image/releases")
                assets = data.get("assets", [])
                for asset in assets:
                    if asset.get("name", "").endswith(".exe"):
                        url = asset.get("browser_download_url", url)
                        break
                published_at = data.get("published_at", "")
                if published_at:
                    try:
                        from datetime import datetime
                        dt = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
                        published_at = dt.strftime("%d/%m/%Y")
                    except:
                        pass
                
                if latest_version:
                    if UPDATE_ANY_DIFFERENT_VERSION:
                        has_update = (latest_version != APP_VERSION)
                    else:
                        has_update = (latest_version > APP_VERSION)
                else:
                    has_update = False
                
                if has_update:
                    self.update_result.emit(True, latest_version, url, published_at, body)
                else:
                    self.update_result.emit(False, latest_version, url, published_at, body)
        except Exception:
            self.update_result.emit(False, "", "", "", "")

class DownloadUpdateThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        import urllib.request
        import os
        try:
            temp_dir = os.environ.get("TEMP", "C:\\Temp")
            self.filepath = os.path.join(temp_dir, "PDF_to_Image_Setup.exe")
            
            req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                total_size = int(response.getheader('Content-Length', 0))
                downloaded = 0
                chunk_size = 8192
                with open(self.filepath, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int(downloaded * 100 / total_size)
                            self.progress.emit(pct)
            self.finished.emit(True, self.filepath)
        except Exception as e:
            self.finished.emit(False, str(e))

class BackgroundService(QObject):
    def __init__(self):
        super().__init__()
        self.server = QLocalServer(self)
        self.server.removeServer("PDFToImageService_V2")
        self.server.listen("PDFToImageService_V2")
        self.server.newConnection.connect(self.handle_connection)
        
        self.cfg = Config()
        
        self.is_processing = False
        
        # Debounce timer
        self.batch_timer = QTimer()
        self.batch_timer.setSingleShot(True)
        self.batch_timer.timeout.connect(self.process_batch)
        self.pending_tasks = []
        
        # --- System Tray Icon ---
        from PyQt6.QtGui import QIcon
        from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
        from PyQt6.QtGui import QAction
        import sys
        
        self.tray = QSystemTrayIcon(self)
        try:
            self.tray.setIcon(QIcon(resource_path("app_icon.ico")))
        except Exception:
            pass
        self.tray.setToolTip(f"PDF to Image (Background Service)")
        
        # Menu (không dùng setContextMenu để tránh lag)
        self.tray_menu = QMenu()
        
        self.action_show = QAction("Mở giao diện chính", self)
        self.action_show.triggered.connect(self.show_main_ui_process)
        self.tray_menu.addAction(self.action_show)
        
        self.tray_menu.addSeparator()
        
        self.action_quit = QAction("Thoát hoàn toàn", self)
        self.action_quit.triggered.connect(self.quit_app)
        self.tray_menu.addAction(self.action_quit)
        
        self.tray.show()
        
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.messageClicked.connect(self.show_main_ui_process)
        
        # --- Kiểm tra cập nhật định kỳ ---
        if self.cfg.get("auto_check_update", True):
            self._check_update_now()
            
            self._update_timer = QTimer(self)
            self._update_timer.timeout.connect(self._check_update_now)
            self._update_timer.start(UPDATE_CHECK_INTERVAL_MINUTES * 60 * 1000)

    def _check_update_now(self):
        self._bg_update_checker = UpdateCheckerThread()
        self._bg_update_checker.update_result.connect(self._on_bg_update_result)
        self._bg_update_checker.start()

    def _on_bg_update_result(self, has_update, version, url, published_at, body):
        if has_update:
            self.cfg.update({
                "update_status": "available",
                "update_latest_version": version,
                "update_url": url,
                "update_published_at": published_at,
                "update_release_notes": body,
            })
            self.tray.showMessage(
                "PDF to Image - Cập nhật mới",
                f"Có bản cập nhật mới v{version}!\nMở PDF to Image → Cài đặt → Hệ thống để cập nhật.",
                QSystemTrayIcon.MessageIcon.Information,
                10000
            )
        elif version:
            self.cfg.update({
                "update_status": "latest",
                "update_latest_version": version,
                "update_url": url,
                "update_published_at": published_at,
                "update_release_notes": body,
            })
        else:
            self.cfg.update({"update_status": "error"})

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_main_ui_process()
        elif reason in (QSystemTrayIcon.ActivationReason.Trigger,
                        QSystemTrayIcon.ActivationReason.Context):
            # Hiện menu tại vị trí chuột cho cả chuột trái và phải
            self.tray_menu.popup(QCursor.pos())

    def show_main_ui_process(self):
        import subprocess, sys
        # Launch the main UI process independently
        env = os.environ.copy()
        env.pop("_MEIPASS2", None)
        cmd = [sys.executable, "--action", "show_gui"] if getattr(sys, 'frozen', False) else [sys.executable, os.path.abspath(__file__), "--action", "show_gui"]
        subprocess.Popen(cmd, env=env)

    def quit_app(self):
        from PyQt6.QtCore import QCoreApplication
        import psutil
        import os
        
        try:
            current_pid = os.getpid()
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['pid'] == current_pid:
                        continue
                    if getattr(sys, 'frozen', False):
                        if proc.info['name'] == 'PDF to Image.exe':
                            proc.kill()
                    else:
                        cmd = proc.info.get('cmdline', [])
                        if cmd and 'pdf-to-image.py' in ' '.join(cmd):
                            proc.kill()
                except:
                    pass
        except:
            pass

        self.tray.hide()
        QCoreApplication.quit()


    def handle_connection(self):
        socket = self.server.nextPendingConnection()
        if socket.waitForReadyRead(1000):
            data = socket.readAll().data().decode('utf-8')
            try:
                task = json.loads(data)
                if task.get("action") == "show_gui":
                    self.show_main_ui_process()
                else:
                    self.pending_tasks.append(task)
                    self.batch_timer.start(500) # Wait 500ms for more files
            except Exception as e:
                pass
        socket.disconnectFromServer()

    def process_batch(self):
        if not self.pending_tasks: return
        
        tasks = self.pending_tasks.copy()
        self.pending_tasks.clear()
        
        # Group tasks by action
        action = tasks[0].get("action")
        files = []
        for t in tasks:
            files.extend(t.get("files", []))
            
        if not files: return
        
        # Determine out_base
        import os
        out_base = ""
        if action == "create_individual":
            out_base = "" # Process inside PDF item logic
        elif action == "create_combined":
            out_base = os.path.join(os.path.dirname(files[0]), "#_pdf to image")
        
        # Prepare queue items
        expanded_files = []
        for f in files:
            if os.path.isdir(f):
                for fname in os.listdir(f):
                    if fname.lower().endswith(".pdf"):
                        expanded_files.append(os.path.join(f, fname))
            else:
                expanded_files.append(f)
                
        if not expanded_files: return
                
        from pathlib import Path
        items = []
        for f in expanded_files:
            qi = QueueItem(f)
            if action == "create_individual":
                qi.group_name = Path(f).stem
            items.append(qi)
            
        indexed_queue = list(enumerate(items))
        
        # Start worker
        self.is_processing = True
        if self.cfg.get("cm_notify", True):
            if len(expanded_files) == 1:
                self.tray.showMessage("PDF to Image", f"Đang tạo ảnh từ {Path(expanded_files[0]).name}.", QSystemTrayIcon.MessageIcon.Information, 2000)
            else:
                self.tray.showMessage("PDF to Image", "Đang tạo ảnh từ nhiều file .pdf.", QSystemTrayIcon.MessageIcon.Information, 2000)
        
        # override cfg with cm_ options
        cm_cfg = dict(self.cfg.d)
        cm_cfg["format"] = cm_cfg.get("cm_format", "PNG")
        cm_cfg["color_mode"] = cm_cfg.get("cm_color_mode", "color")
        cm_cfg["dpi"] = cm_cfg.get("cm_dpi", 300)
        cm_cfg["cm_action"] = action
        
        self.worker = ConversionWorker(indexed_queue, cm_cfg, out_base)
        self.worker.signals.overall_progress.connect(self.update_progress)
        self.worker.signals.all_done.connect(self.task_finished)
        self.worker.start()

    def update_progress(self, done, total, pct):
        pass
        
    def task_finished(self, stats):
        self.is_processing = False
        if self.cfg.get("cm_notify", True):
            self.tray.showMessage("Hoàn thành", "Hoàn thành! Đã tạo xong ảnh.", QSystemTrayIcon.MessageIcon.Information, 3000)


# ======================================================================
# MAIN
# ======================================================================
def resource_path(relative_path):
    import os, sys
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def main():
    multiprocessing.freeze_support()
    if platform.system() == "Windows":
        try:
            import ctypes
            # ctypes.windll.shcore.SetProcessDpiAwareness(2)
            # Kích hoạt AppUserModelID để Windows nhận diện chính xác icon trên thanh Taskbar
            myappid = 'mycompany.pdf_to_image.app.'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    app = QApplication(sys.argv)
    
    # Kích hoạt ICON TOÀN CẦU CHO TẤT CẢ CỬA SỔ (Giải quyết lỗi mất ico)

        
    try:
        from PyQt6.QtGui import QIcon
        # Sử dụng trực tiếp app_icon.ico như yêu cầu
        app.setWindowIcon(QIcon(resource_path("app_icon.ico")))
    except Exception:
        pass
    
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", action="store_true")
    parser.add_argument("--action", type=str, default="show_gui")
    parser.add_argument("--files", nargs="*", default=[])
    args, _ = parser.parse_known_args()

    if args.client or (args.action != "show_gui" and args.action != "background") or args.files:
        # Client mode
        socket = QLocalSocket()
        socket.connectToServer("PDFToImageService_V2")
        if socket.waitForConnected(1000):
            data = json.dumps({"action": args.action, "files": args.files})
            socket.write(data.encode('utf-8'))
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            sys.exit(0)
        else:
            # Server not running, we'll start it by falling through
            args.action = "background"

    if args.action == "show_gui":
        # Check Single Instance for Main UI
        shared_mem_main = QSharedMemory("PDF_To_Image_Main_UI_Instance_Key")
        if shared_mem_main.attach():
            sys.exit(0)
        shared_mem_main.create(1)
        
        app.setQuitOnLastWindowClosed(True)
        splash = AnimatedSplashScreen(MainWindow)
        splash.show()
        sys.exit(app.exec())
    else:
        # Check Single Instance for Background Service
        shared_mem_bg = QSharedMemory("PDF_To_Image_Unique_Instance_Key")
        if shared_mem_bg.attach():
            sys.exit(0)
        shared_mem_bg.create(1)

        app.setQuitOnLastWindowClosed(False)
        service = BackgroundService()
        
        if args.files:
            service.pending_tasks.append({"action": args.action, "files": args.files})
            service.process_batch()
            
        sys.exit(app.exec())


if __name__ == "__main__":
    main()

