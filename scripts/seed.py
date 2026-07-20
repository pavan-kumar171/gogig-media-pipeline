"""
Seed script: uploads a handful of synthetically generated test images
(sharp/blurry/dark/duplicate) so a reviewer can hit the results API and see
real, varied output without hunting for their own vehicle photos.

Run with the API already up: `python scripts/seed.py`
"""
import io
import sys
import time
import requests
from PIL import Image, ImageDraw, ImageFilter

API_BASE = "http://localhost:8000/api/v1"


def _to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def make_sharp_vehicle_photo() -> bytes:
    img = Image.new("RGB", (1024, 768), color=(100, 110, 120))
    d = ImageDraw.Draw(img)
    d.rectangle([300, 550, 700, 620], fill=(255, 255, 255))
    d.text((320, 570), "KA05MH4521", fill=(0, 0, 0))
    return _to_bytes(img)


def make_blurry_photo() -> bytes:
    img = Image.new("RGB", (1024, 768), color=(100, 110, 120))
    d = ImageDraw.Draw(img)
    d.rectangle([300, 550, 700, 620], fill=(255, 255, 255))
    return _to_bytes(img.filter(ImageFilter.GaussianBlur(radius=12)))


def make_dark_photo() -> bytes:
    img = Image.new("RGB", (1024, 768), color=(15, 12, 18))
    return _to_bytes(img)


def make_small_screenshot_like() -> bytes:
    # phone-screenshot aspect ratio, no camera EXIF (PIL never writes any)
    img = Image.new("RGB", (390, 844), color=(230, 230, 230))
    return _to_bytes(img)


def upload(name: str, content: bytes) -> str:
    resp = requests.post(
        f"{API_BASE}/uploads",
        files={"file": (f"{name}.jpg", content, "image/jpeg")},
    )
    resp.raise_for_status()
    job_id = resp.json()["job_id"]
    print(f"  uploaded {name} -> job {job_id}")
    return job_id


def main():
    print("Seeding sample uploads against", API_BASE)
    samples = {
        "sharp_plate": make_sharp_vehicle_photo(),
        "blurry": make_blurry_photo(),
        "duplicate_of_sharp": make_sharp_vehicle_photo(),  # same content -> flags duplicate
        "dark": make_dark_photo(),
        "screenshot_like": make_small_screenshot_like(),
    }
    job_ids = {name: upload(name, content) for name, content in samples.items()}

    print("\nWaiting for background processing...")
    time.sleep(5)

    print("\nResults:")
    for name, job_id in job_ids.items():
        r = requests.get(f"{API_BASE}/jobs/{job_id}/results")
        if r.status_code == 200:
            data = r.json()
            issues = [c["check_name"] for c in data["checks"] if not c["passed"]]
            print(f"  {name}: status={data['status']} has_issues={data['has_issues']} failed_checks={issues}")
        else:
            print(f"  {name}: not ready yet ({r.json().get('detail')})")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("Could not reach the API. Is it running on http://localhost:8000?")
        sys.exit(1)
