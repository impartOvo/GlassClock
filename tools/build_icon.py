"""Pack the selected PNG, without changing its artwork, into Windows icon sizes."""

from pathlib import Path
import struct

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage


ROOT = Path(__file__).resolve().parents[1]
source = QImage(str(ROOT / "assets" / "GlassClock.png"))
if source.isNull():
    raise SystemExit("Icon source image is missing")

images = []
for size in (16, 24, 32, 48, 64, 128, 256):
    scaled = source.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not scaled.save(buffer, "PNG"):
        raise SystemExit(f"Cannot encode {size}px icon")
    images.append((size, bytes(buffer.data())))

header = struct.pack("<HHH", 0, 1, len(images))
offset = 6 + len(images) * 16
entries = bytearray()
payload = bytearray()
for size, data in images:
    entries.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                               1, 32, len(data), offset))
    payload.extend(data)
    offset += len(data)

(ROOT / "assets" / "GlassClock.ico").write_bytes(header + entries + payload)
