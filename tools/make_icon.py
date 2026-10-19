"""Write the app icon. Usage: python tools/make_icon.py OUT.icns (macOS) or OUT.png
(Windows: PyInstaller converts the PNG to .ico when Pillow is installed)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from divyinvestorpro import icon  # noqa: E402


def main(out):
    app = QGuiApplication(sys.argv[:1])  # noqa: F841 (needed for fonts)
    master = icon.draw(1024)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    if out.endswith(".png"):
        master.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(out)
        return
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "app.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = size * scale
                name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
                master.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(
                    str(iconset / name))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", out], check=True)


if __name__ == "__main__":
    main(sys.argv[1])
