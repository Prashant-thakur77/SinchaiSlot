"""Draw the bundled sample Soil Health Card (a made-up card for the demo; values in soil_card_sample.json)."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
V = json.loads((HERE / "soil_card_sample.json").read_text())


def font(size: int):
    for p in ("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main() -> None:
    im = Image.new("RGB", (900, 1200), (246, 241, 228))
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, 880, 1180], outline=(40, 90, 50), width=4)
    d.text((60, 50), "SOIL HEALTH CARD (SAMPLE - NOT A REAL CARD)", fill=(40, 90, 50), font=font(30))
    d.text((60, 100), f"Card No: {V['card_no']}", fill=(20, 20, 20), font=font(26))
    d.text((60, 140), "District: Samastipur   Farmer: DEMO", fill=(20, 20, 20), font=font(26))
    d.text((60, 180), f"Soil texture: {V['texture']}", fill=(20, 20, 20), font=font(26))
    rows = [("pH", V["ph"], ""), ("EC", V["ec_dsm"], "dS/m"), ("Organic Carbon (OC)", V["oc_pct"], "%"),
            ("Available Nitrogen (N)", V["n_kg_ha"], "kg/ha"), ("Available Phosphorus (P)", V["p_kg_ha"], "kg/ha"),
            ("Available Potassium (K)", V["k_kg_ha"], "kg/ha"), ("Available Sulphur (S)", V["s_ppm"], "ppm"),
            ("Available Zinc (Zn)", V["zn_ppm"], "ppm")]
    y = 260
    d.text((60, y), "Parameter", fill=(40, 90, 50), font=font(26))
    d.text((560, y), "Value", fill=(40, 90, 50), font=font(26))
    d.text((720, y), "Unit", fill=(40, 90, 50), font=font(26))
    for name, val, unit in rows:
        y += 70
        d.line([60, y - 12, 840, y - 12], fill=(190, 180, 150), width=1)
        d.text((60, y), name, fill=(20, 20, 20), font=font(26))
        d.text((560, y), str(val), fill=(20, 20, 20), font=font(26))
        d.text((720, y), unit, fill=(20, 20, 20), font=font(26))
    im.save(HERE / "soil_card_sample.png", optimize=True)


if __name__ == "__main__":
    main()
