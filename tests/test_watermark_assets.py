from __future__ import annotations

from io import BytesIO

from PIL import Image
from PySide6.QtWidgets import QApplication

from app.core.watermark import WatermarkSpec
from app.main import create_application
from app.services.watermark_assets import installed_font_families, render_image_asset, render_text_asset


def test_text_watermark_renders_chinese_with_local_font() -> None:
    existing = QApplication.instance()
    app = existing or create_application([])
    families = installed_font_families()
    # Qt's offscreen platform can expose an empty font database even though
    # the Windows platform plugin returns the installed families in production.
    preferred = next(
        (name for name in ("Microsoft YaHei UI", "SimSun", "Segoe UI") if name in families),
        families[0] if families else "Microsoft YaHei UI",
    )
    asset = render_text_asset(WatermarkSpec(text="仅供内部使用", font_family=preferred, rotation=-45))
    with Image.open(BytesIO(asset.png)) as image:
        assert image.width > 100
        assert image.height > 40
        assert image.mode == "RGBA"
        assert image.getchannel("A").getbbox() is not None
    if existing is None:
        app.quit()


def test_image_watermark_keeps_alpha_and_applies_rotation(tmp_path) -> None:
    source = tmp_path / "logo.png"
    Image.new("RGBA", (120, 40), (10, 20, 30, 200)).save(source, dpi=(144, 144))
    asset = render_image_asset(WatermarkSpec(kind="image", opacity=0.5, rotation=30), source)
    with Image.open(BytesIO(asset.png)) as image:
        assert image.width > 120
        assert image.height > 40
        assert image.getchannel("A").getextrema()[1] <= 100
