"""
Pixel-level screenshot diff — goes beyond the base pipeline's SSIM
score (a single number) to produce a visual heatmap showing WHERE
the human and bot views differ.
"""

try:
    import cv2          # type: ignore  # optional dep
    import numpy as np  # type: ignore
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


def generate_diff_heatmap(human_screenshot_path: str, bot_screenshot_path: str,
                           output_path: str) -> dict:
    """
    Produces a side-by-side image: human view | bot view | diff heatmap,
    with differing regions highlighted in red.
    """
    if not _CV2_AVAILABLE:
        return {
            "output_path": None,
            "flagged_region_count": 0,
            "flagged_regions": [],
            "total_diff_pixels": 0,
            "diff_percentage": 0.0,
            "error": "opencv-python not installed — run: pip install opencv-python",
        }

    img_h = cv2.imread(human_screenshot_path)
    img_b = cv2.imread(bot_screenshot_path)

    if img_h is None or img_b is None:
        return {
            "output_path": None, "flagged_region_count": 0,
            "flagged_regions": [], "total_diff_pixels": 0,
            "diff_percentage": 0.0,
            "error": "Could not read screenshot file(s)",
        }

    h = min(img_h.shape[0], img_b.shape[0])
    w = min(img_h.shape[1], img_b.shape[1])
    img_h = cv2.resize(img_h, (w, h))
    img_b = cv2.resize(img_b, (w, h))

    gray_h = cv2.cvtColor(img_h, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)

    diff      = cv2.absdiff(gray_h, gray_b)
    _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

    # Dilate to merge nearby differing pixels into coherent regions
    kernel = np.ones((9, 9), np.uint8)
    thresh = cv2.dilate(thresh, kernel, iterations=2)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    heatmap = img_b.copy()
    flagged_regions = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 200:   # ignore tiny noise differences (anti-aliasing etc.)
            continue
        x, y, cw, ch = cv2.boundingRect(contour)
        cv2.rectangle(heatmap, (x, y), (x + cw, y + ch), (0, 0, 255), 3)
        flagged_regions.append({"x": x, "y": y, "width": cw, "height": ch,
                                 "area": float(area)})

    combined = np.hstack([img_h, img_b, heatmap])
    cv2.imwrite(output_path, combined)

    return {
        "output_path":          output_path,
        "flagged_region_count": len(flagged_regions),
        "flagged_regions":      flagged_regions,
        "total_diff_pixels":    int(np.sum(thresh > 0)),
        "diff_percentage":      round(float(np.sum(thresh > 0)) / thresh.size * 100, 2),
    }
