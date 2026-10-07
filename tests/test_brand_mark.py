import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

try:
    import PIL  # noqa: F401
except ImportError:
    PIL = None


@unittest.skipIf(PIL is None, "serve Pillow")
class BrandMarkTest(unittest.TestCase):
    def test_draws_logo_and_name_or_nothing_without_brand(self):
        from PIL import Image
        import brand_mark
        d = tempfile.mkdtemp()
        p = os.path.join(d, "brand.json")
        with open(p, "w") as f:
            json.dump({"name": ["Paga", "Puntuale"], "color": "#0f766e", "color_light": "#5eead4"}, f)
        b = brand_mark.load(p)
        self.assertEqual(b["name"], ["Paga", "Puntuale"])
        img = Image.new("RGB", (400, 100), (0, 0, 0))
        w = brand_mark.draw(img, 10, 10, 60, b)
        self.assertGreater(w, 60)
        self.assertEqual(img.getpixel((40, 14))[:3], (15, 118, 110))  # teal clock face
        self.assertIsNone(brand_mark.load(os.path.join(d, "missing.json")))
        blank = Image.new("RGB", (100, 100))
        self.assertEqual(brand_mark.draw(blank, 0, 0, 40, {}), 0)  # no brand: image left as it was
        self.assertEqual(blank.getbbox(), None)


if __name__ == "__main__":
    unittest.main()
