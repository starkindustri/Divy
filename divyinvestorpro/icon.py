"""The app icon, drawn in code so no image files are needed."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen


def draw(size: int = 1024) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 1024

    # macOS-style rounded square with a green gradient
    body = QRectF(100 * s, 100 * s, 824 * s, 824 * s)
    grad = QLinearGradient(body.topLeft(), body.bottomRight())
    grad.setColorAt(0, QColor("#34c48a"))
    grad.setColorAt(1, QColor("#11694a"))
    path = QPainterPath()
    path.addRoundedRect(body, 185 * s, 185 * s)
    p.fillPath(path, grad)

    # rising bars
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 235))
    base, width = 760 * s, 120 * s
    for i, h in enumerate((190, 300, 430)):
        x = (250 + i * 175) * s
        p.drawRoundedRect(QRectF(x, base - h * s, width, h * s), 26 * s, 26 * s)

    # coin above the tallest bar
    cx, cy, r = 735 * s, 250 * s, 92 * s
    p.setBrush(QColor("#ffd55c"))
    p.setPen(QPen(QColor("#e0a92a"), 14 * s))
    p.drawEllipse(QPointF(cx, cy), r, r)
    font = p.font()
    font.setBold(True)
    font.setPixelSize(int(118 * s))
    p.setFont(font)
    p.setPen(QColor("#8a5a00"))
    p.drawText(QRectF(cx - r, cy - r, 2 * r, 2 * r), Qt.AlignCenter, "$")
    p.end()
    return img
