"""A small, animated, frosted-glass desktop countdown for Windows."""

from __future__ import annotations

import ctypes
import json
import math
import os
from pathlib import Path
import random
import sys
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon, QImage, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QAbstractButton, QMenu, QSystemTrayIcon, QWidget

from countdown import beijing_now, daily_countdowns, format_remaining
from skins import SKINS

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
SETTINGS = ROOT / "data" / "settings.json"
WIDTH, HEIGHT = 168, 192


def rgba(value, alpha=255):
    colour = QColor(value)
    colour.setAlpha(max(0, min(255, int(alpha))))
    return colour


def read_settings():
    try:
        value = json.loads(SETTINGS.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_settings(value):
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as error:
        print(f"无法保存设置：{error}", file=sys.stderr)


def request_windows_acrylic(widget):
    """Ask DWM for a translucent acrylic backdrop where the OS supports it."""
    if os.name != "nt":
        return False
    try:
        class AccentPolicy(ctypes.Structure):
            _fields_ = [("state", ctypes.c_int), ("flags", ctypes.c_int),
                        ("gradient", ctypes.c_uint), ("animation", ctypes.c_int)]

        class CompositionData(ctypes.Structure):
            _fields_ = [("attribute", ctypes.c_int), ("data", ctypes.c_void_p),
                        ("size", ctypes.c_size_t)]

        user32 = ctypes.windll.user32
        function = user32.SetWindowCompositionAttribute
        function.argtypes = (ctypes.c_void_p, ctypes.POINTER(CompositionData))
        function.restype = ctypes.c_int
        # A translucent neutral tint leaves the chosen animated palette visible.
        policy = AccentPolicy(4, 2, 0x70202020, 0)
        data = CompositionData(19, ctypes.addressof(policy), ctypes.sizeof(policy))
        return bool(function(int(widget.winId()), ctypes.byref(data)))
    except (AttributeError, OSError):
        return False


class GlassButton(QAbstractButton):
    def __init__(self, clock, kind):
        super().__init__(clock)
        self.clock = clock
        self.kind = kind
        self.setFixedSize(25, 25)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("切换皮肤" if kind == "skin" else "窗口置顶")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        skin = SKINS[self.clock.skin_index]
        if self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(rgba(skin.ink, 30))
            p.drawEllipse(QRectF(2, 2, 21, 21))
        if self.kind == "skin":
            p.setPen(QPen(rgba(skin.ink, 195), 0.8))
            p.setBrush(rgba(skin.ring, 210))
            p.drawEllipse(QRectF(8, 8, 9, 9))
            p.setPen(QPen(rgba("#ffffff", 140), 0.8))
            p.drawArc(QRectF(9.4, 9.1, 5, 5), 35 * 16, 115 * 16)
        else:
            colour = rgba(skin.ring if self.clock.pinned else skin.ink,
                          245 if self.clock.pinned else 135)
            pen = QPen(colour, 1.45)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            # A compact angled pin, recognisable even when the widget is small.
            path = QPainterPath(QPointF(8, 6.8))
            path.lineTo(15.4, 7.3)
            path.lineTo(16.1, 10.5)
            path.lineTo(18, 12.6)
            path.lineTo(13.2, 14.4)
            path.lineTo(10.3, 18.1)
            path.lineTo(10.8, 13.5)
            path.lineTo(7.1, 10.3)
            path.closeSubpath()
            p.drawPath(path)
            p.drawLine(QPointF(11, 15), QPointF(7, 19))
        p.end()


class GlassClock(QWidget):
    def __init__(self):
        self.settings = read_settings()
        self.skin_index = int(self.settings.get("skin", 0)) % len(SKINS)
        self.pinned = bool(self.settings.get("pinned", True))
        self.rain_enabled = bool(self.settings.get("rain", True))
        self.animating = bool(self.settings.get("animating", True))
        # Tool windows remain on the desktop without taking a taskbar button.
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if self.pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(WIDTH, HEIGHT)
        self.setWindowTitle("玻璃下班时钟")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMouseTracking(True)
        self.drag_offset = None
        self.time_origin = time.monotonic()
        self.last_tick = self.time_origin
        self.rng = random.Random(82013)
        self.rain = [self.new_drop(initial=True) for _ in range(38)]
        self.grain = self.make_grain()

        self.skin_button = GlassButton(self, "skin")
        self.skin_button.move(5, 5)
        self.skin_button.clicked.connect(self.next_skin)
        self.pin_button = GlassButton(self, "pin")
        self.pin_button.move(WIDTH - 30, 5)
        self.pin_button.clicked.connect(self.toggle_pin)
        self.update_tooltips()

        self.restore_position()
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def new_drop(self, initial=False):
        return {
            "x": self.rng.uniform(12, WIDTH - 12),
            "y": self.rng.uniform(14, HEIGHT - 12) if initial else self.rng.uniform(-35, 8),
            "r": self.rng.uniform(1.1, 2.9),
            "speed": self.rng.uniform(6, 27),
            "phase": self.rng.uniform(0, math.tau),
        }

    def make_grain(self):
        image = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        for _ in range(5200):
            x, y = self.rng.randrange(WIDTH), self.rng.randrange(HEIGHT)
            light = self.rng.choice((True, False))
            p.setPen(rgba("#ffffff" if light else "#000000", self.rng.randrange(5, 22)))
            p.drawPoint(x, y)
        p.end()
        return image

    def restore_position(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = self.settings.get("x", area.right() - WIDTH - 24)
        y = self.settings.get("y", area.top() + 24)
        try:
            point = QPoint(int(x), int(y))
        except (TypeError, ValueError):
            point = QPoint(area.right() - WIDTH - 24, area.top() + 24)
        screens = QApplication.screens()
        if not any(s.availableGeometry().intersects(
                self.frameGeometry().translated(point - self.pos())) for s in screens):
            point = QPoint(area.right() - WIDTH - 24, area.top() + 24)
        self.move(point)

    def save(self):
        write_settings({"skin": self.skin_index, "pinned": self.pinned,
                        "rain": self.rain_enabled, "animating": self.animating,
                        "x": self.x(), "y": self.y()})

    def update_tooltips(self):
        self.skin_button.setToolTip(f"{SKINS[self.skin_index].name}：点击切换皮肤；右键可选择")
        self.pin_button.setToolTip("取消置顶" if self.pinned else "置顶显示")

    def next_skin(self):
        self.choose_skin((self.skin_index + 1) % len(SKINS))

    def choose_skin(self, index):
        self.skin_index = index
        self.update_tooltips()
        self.skin_button.update()
        self.pin_button.update()
        self.update()
        self.save()

    def toggle_pin(self):
        self.pinned = not self.pinned
        position = self.pos()
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.pinned)
        self.move(position)
        if was_visible:
            self.show()
        self.update_tooltips()
        self.pin_button.update()
        self.save()

    def tick(self):
        now = time.monotonic()
        delta = min(now - self.last_tick, 0.15)
        self.last_tick = now
        if self.animating and self.rain_enabled:
            for index, drop in enumerate(self.rain):
                drop["y"] += drop["speed"] * delta
                if drop["y"] > HEIGHT + 10:
                    self.rain[index] = self.new_drop()
        self.update()

    def closeEvent(self, event):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        else:
            super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(30, lambda: request_windows_acrylic(self))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_offset is not None:
            self.drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.save()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #222b37; color: #f1f5f8; border: 1px solid #647283;
                    padding: 5px; font-family: 'Microsoft YaHei UI'; font-size: 12px; }
            QMenu::item { padding: 6px 24px 6px 22px; border-radius: 4px; }
            QMenu::item:selected { background: #526579; }
            QMenu::separator { height: 1px; background: #566573; margin: 4px; }
        """)
        skins_menu = menu.addMenu("选择皮肤")
        for index, skin in enumerate(SKINS):
            item = QAction(skin.name, skins_menu)
            item.setCheckable(True)
            item.setChecked(index == self.skin_index)
            item.triggered.connect(lambda checked=False, i=index: self.choose_skin(i))
            skins_menu.addAction(item)
        rain = menu.addAction("雨滴效果")
        rain.setCheckable(True)
        rain.setChecked(self.rain_enabled)
        rain.triggered.connect(self.set_rain)
        moving = menu.addAction("动态背景")
        moving.setCheckable(True)
        moving.setChecked(self.animating)
        moving.triggered.connect(self.set_animating)
        pin = menu.addAction("窗口置顶")
        pin.setCheckable(True)
        pin.setChecked(self.pinned)
        pin.triggered.connect(self.toggle_pin)
        menu.addSeparator()
        if QSystemTrayIcon.isSystemTrayAvailable():
            menu.addAction("隐藏到系统托盘", self.hide)
        menu.addAction("退出时钟", QApplication.quit)
        menu.exec(event.globalPos())

    def set_rain(self, checked):
        self.rain_enabled = checked
        self.save()
        self.update()

    def set_animating(self, checked):
        self.animating = checked
        self.save()
        self.update()

    def paintEvent(self, event):
        skin = SKINS[self.skin_index]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        outer = QRectF(1, 1, WIDTH - 2, HEIGHT - 2)
        surface = QPainterPath()
        surface.addRoundedRect(outer, 16, 16)
        p.setClipPath(surface)

        background = QLinearGradient(0, 0, WIDTH, HEIGHT)
        background.setColorAt(0, rgba(skin.base, 204))
        background.setColorAt(1, rgba(skin.shade, 224))
        p.fillPath(surface, background)

        elapsed = time.monotonic() - self.time_origin if self.animating else 0.0
        for colour, x, y, radius, alpha in (
            (skin.glow, 18 + 32 * math.sin(elapsed * 0.24), 20 + 14 * math.cos(elapsed * 0.19), 105, 65),
            (skin.glow2, WIDTH - 15 + 24 * math.cos(elapsed * 0.20), HEIGHT - 33 + 15 * math.sin(elapsed * 0.27), 116, 55),
        ):
            glow = QRadialGradient(QPointF(x, y), radius)
            glow.setColorAt(0, rgba(colour, alpha))
            glow.setColorAt(1, rgba(colour, 0))
            p.fillRect(outer, glow)

        self.paint_ripples(p, skin, elapsed)
        p.drawImage(QPoint(0, 0), self.grain)
        if self.rain_enabled:
            self.paint_rain(p, skin)

        p.setClipping(False)
        p.setPen(QPen(rgba("#ffffff", 110), 0.9))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(outer.adjusted(.5, .5, -.5, -.5), 15.5, 15.5)
        p.setPen(QPen(rgba("#ffffff", 45), 0.7))
        p.drawArc(QRectF(4, 4, WIDTH - 8, 25), 5 * 16, 170 * 16)

        self.paint_clock(p, skin)
        p.end()

    def paint_ripples(self, p, skin, elapsed):
        for index in range(3):
            phase = elapsed * (0.18 + index * 0.03) + index * 1.4
            path = QPainterPath(QPointF(-20, 36 + index * 39 + 8 * math.sin(phase)))
            path.cubicTo(QPointF(35, 4 + index * 35),
                         QPointF(92, 82 + index * 26 + 9 * math.cos(phase)),
                         QPointF(WIDTH + 15, 24 + index * 48))
            colour = skin.glow if index != 1 else skin.glow2
            pen = QPen(rgba(colour, 16 if skin.effect != "water" else 27), 5 + index * 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPath(path)
        if skin.effect == "stars":
            for x, y in ((20, 45), (145, 48), (31, 120), (131, 119), (42, 24)):
                p.setPen(QPen(rgba(skin.ink, 105), 1))
                p.drawPoint(QPointF(x, y))

    def paint_rain(self, p, skin):
        for drop in self.rain:
            x, y, r = drop["x"], drop["y"], drop["r"]
            trail = min(14, drop["speed"] * .38)
            gradient = QLinearGradient(x, y - trail, x, y)
            gradient.setColorAt(0, rgba("#b5e5ff", 0))
            gradient.setColorAt(1, rgba("#b5e5ff", 45))
            p.setPen(QPen(gradient, max(0.6, r * .7)))
            p.drawLine(QPointF(x, y - trail), QPointF(x, y))
            p.setPen(QPen(rgba("#e0f4ff", 75), .65))
            p.setBrush(rgba("#d2ecfa", 34))
            p.drawEllipse(QRectF(x - r, y - r * 1.25, r * 2, r * 2.5))
            p.setPen(QPen(rgba("#ffffff", 155), .7))
            p.drawArc(QRectF(x - r * .65, y - r, r * 1.2, r * 1.4), 40 * 16, 95 * 16)

    def paint_clock(self, p, skin):
        now = beijing_now()
        target, previous, next_evening = daily_countdowns(now)
        remaining = max(0.0, (target - now).total_seconds())
        duration = max(1.0, (target - previous).total_seconds())
        fraction = min(1.0, remaining / duration)
        circle = QRectF(26, 27, 116, 116)
        track = QPen(rgba(skin.ink, 40), 3.0)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(track)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(circle)
        progress = QPen(rgba(skin.ring, 235), 3.0)
        progress.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(progress)
        p.drawArc(circle, 90 * 16, -max(0, round(fraction * 360 * 16)))

        p.setPen(rgba(skin.ink, 220))
        p.setFont(self.font_for(9))
        p.drawText(QRectF(24, 58, 120, 16), Qt.AlignmentFlag.AlignCenter,
                   f"距离 {target:%H:%M}")
        p.setPen(rgba(skin.ink, 255))
        p.setFont(self.font_for(19, bold=True, digits=True))
        p.drawText(QRectF(12, 77, 144, 27), Qt.AlignmentFlag.AlignCenter,
                   format_remaining(target - now))

        p.setPen(QPen(rgba(skin.ink, 65), .7))
        p.drawLine(QPointF(13, 151), QPointF(WIDTH - 13, 151))
        p.drawLine(QPointF(84, 157), QPointF(84, 183))
        p.setPen(rgba(skin.ink, 185))
        p.setFont(self.font_for(7))
        p.drawText(QRectF(8, 154, 74, 12), Qt.AlignmentFlag.AlignCenter, "北京时间")
        p.drawText(QRectF(86, 154, 74, 12), Qt.AlignmentFlag.AlignCenter, "距离 18:00")
        p.setPen(rgba(skin.ink, 245))
        p.setFont(self.font_for(10, digits=True))
        p.drawText(QRectF(8, 166, 74, 16), Qt.AlignmentFlag.AlignCenter, f"{now:%H:%M:%S}")
        p.drawText(QRectF(86, 166, 74, 16), Qt.AlignmentFlag.AlignCenter,
                   format_remaining(next_evening - now))

    @staticmethod
    def font_for(pixels, bold=False, digits=False):
        font = QFont("Consolas" if digits else "Microsoft YaHei UI")
        font.setPixelSize(pixels)
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        return font


def tray_icon():
    """Draw a small glass clock icon that stays legible in the notification area."""
    image = QPixmap(64, 64)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#e3d4ff"), 2.5))
    painter.setBrush(QColor("#36415c"))
    painter.drawRoundedRect(QRectF(5, 5, 54, 54), 15, 15)
    painter.setPen(QPen(QColor("#ffffff"), 2.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(16, 16, 32, 32))
    painter.drawLine(QPointF(32, 32), QPointF(32, 22))
    painter.drawLine(QPointF(32, 32), QPointF(39, 35))
    painter.end()
    return QIcon(image)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("玻璃下班时钟")
    app.setWindowIcon(tray_icon())
    clock = GlassClock()
    if QSystemTrayIcon.isSystemTrayAvailable():
        app.setQuitOnLastWindowClosed(False)
        tray = QSystemTrayIcon(app.windowIcon(), app)
        tray.setToolTip("GlassClock · 玻璃下班时钟")
        tray_menu = QMenu()
        show_action = tray_menu.addAction("显示时钟")
        show_action.triggered.connect(lambda: (clock.show(), clock.raise_(), clock.activateWindow()))
        hide_action = tray_menu.addAction("隐藏时钟")
        hide_action.triggered.connect(clock.hide)
        tray_menu.addSeparator()
        pin_action = tray_menu.addAction("窗口置顶")
        pin_action.setCheckable(True)
        pin_action.setChecked(clock.pinned)
        pin_action.triggered.connect(clock.toggle_pin)
        tray_menu.aboutToShow.connect(lambda: pin_action.setChecked(clock.pinned))
        skins_menu = tray_menu.addMenu("选择皮肤")
        for index, skin in enumerate(SKINS):
            action = skins_menu.addAction(skin.name)
            action.triggered.connect(lambda checked=False, i=index: clock.choose_skin(i))
        tray_menu.addSeparator()
        tray_menu.addAction("退出时钟", app.quit)
        tray.setContextMenu(tray_menu)
        tray.activated.connect(
            lambda reason: (clock.show(), clock.raise_(), clock.activateWindow())
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        tray.show()
    else:
        app.setQuitOnLastWindowClosed(True)
        clock.setWindowFlag(Qt.WindowType.Tool, False)
        clock.setWindowFlag(Qt.WindowType.Window, True)
    clock.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
