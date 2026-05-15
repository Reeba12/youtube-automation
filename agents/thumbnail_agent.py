"""
Thumbnail Agent — extracts best video frame + adds text/logo overlay.
Runs AFTER video agent (uses real frames from actual video).
Rotates 3 templates. Uses Aria face if avatar enabled.
Output: 1280x720 JPEG, <2MB, mobile-readable.
"""

import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from colorthief import ColorThief

from agents.base import advance_job, record_policy
from core.config import AVATAR_ENABLED, TEMP_DIR
from core.database import get_job
from core.logger import get_logger
from core.policy_checker import check_thumbnail

log = get_logger("thumbnail_agent", "system")

THUMB_W, THUMB_H = 1280, 720
FONT_DIR = Path("data/fonts")
LOGO_PATH = Path("data/channel_logo.png")

# 3 rotating layout templates
TEMPLATES = [
    {
        "name":           "split",
        "text_area":      "right",   # text on right 55%, image on left 45%
        "text_x_pct":     0.47,
        "text_y_pct":     0.25,
        "gradient_side":  "right",
        "main_font_size": 90,
        "sub_font_size":  48,
    },
    {
        "name":           "bottom_overlay",
        "text_area":      "bottom",  # text bottom 40%, image full screen
        "text_x_pct":     0.05,
        "text_y_pct":     0.58,
        "gradient_side":  "bottom",
        "main_font_size": 100,
        "sub_font_size":  52,
    },
    {
        "name":           "top_left",
        "text_area":      "left",    # text top-left 50%, image right
        "text_x_pct":     0.03,
        "text_y_pct":     0.15,
        "gradient_side":  "left",
        "main_font_size": 88,
        "sub_font_size":  46,
    },
]


class ThumbnailAgent:

    def run(self, state: dict) -> dict:
        job_id     = state["job_id"]
        video_path = state["video_path"]
        topic      = state["topic"]
        metadata   = state.get("metadata", {})

        log.info(f"[Job {job_id}] Thumbnail Agent starting")
        advance_job(job_id, "thumbnail")

        out_dir = TEMP_DIR / str(job_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = out_dir / "thumbnail.jpg"

        # 1. Extract best frame from video
        best_frame = self._extract_best_frame(video_path)

        # 2. If avatar enabled, also get Aria face image to composite
        aria_face = self._get_aria_face() if AVATAR_ENABLED else None

        # 3. Pick template (rotate per recent jobs)
        template = self._pick_template(job_id)
        log.info(f"[Job {job_id}] Using thumbnail template: {template['name']}")

        # 4. Build thumbnail
        hook_text = self._get_hook_text(topic, metadata)
        sub_text  = self._get_sub_text(topic)

        thumbnail = self._build_thumbnail(
            frame=best_frame,
            aria_face=aria_face,
            template=template,
            hook_text=hook_text,
            sub_text=sub_text,
        )

        # 5. Save
        thumbnail.save(str(thumb_path), "JPEG", quality=92, optimize=True)
        log.info(f"[Job {job_id}] Thumbnail saved: {thumb_path} ({thumb_path.stat().st_size // 1024}KB)")

        # 6. Policy check
        title = (metadata.get("title_options") or [topic.get("title", "")])[0]
        result = check_thumbnail(str(thumb_path), title, topic.get("title", ""))
        record_policy(job_id, "thumbnail", result["passed"], result["violations"],
                      "continue" if result["passed"] else "retry")

        if not result["passed"]:
            state["policy_violations"] = result["violations"]
            state["error"] = "thumbnail_policy_failed"
            return state

        advance_job(job_id, "thumbnail_done", {"thumbnail_path": str(thumb_path)})
        state["thumbnail_path"] = str(thumb_path)
        log.info(f"[Job {job_id}] Thumbnail Agent complete")
        return state

    # ── Frame extraction ──────────────────────────────────────

    def _extract_best_frame(self, video_path: str) -> np.ndarray:
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30

        # Sample 30 frames skipping intro (10%) and outro (15%)
        start_f = int(total_frames * 0.10)
        end_f   = int(total_frames * 0.85)
        sample_indices = [
            int(start_f + (end_f - start_f) * i / 29)
            for i in range(30)
        ]

        best_frame, best_score = None, -1
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            score = self._score_frame(frame)
            if score > best_score:
                best_score = score
                best_frame = frame.copy()

        cap.release()

        if best_frame is None:
            best_frame = np.zeros((THUMB_H, THUMB_W, 3), dtype=np.uint8)

        # Convert BGR → RGB, resize to thumbnail size
        best_frame = cv2.cvtColor(best_frame, cv2.COLOR_BGR2RGB)
        best_frame = cv2.resize(best_frame, (THUMB_W, THUMB_H))
        return best_frame

    def _score_frame(self, frame: np.ndarray) -> float:
        """Score frame by brightness, contrast, sharpness."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = gray.mean()
        contrast   = gray.std()
        laplacian  = cv2.Laplacian(gray, cv2.CV_64F).var()  # sharpness

        # Penalize very dark or very bright frames
        brightness_ok = 1.0 if 60 < brightness < 210 else 0.3
        score = (contrast * 0.4 + laplacian * 0.001 + brightness_ok * 20)
        return score

    # ── Aria face ─────────────────────────────────────────────

    def _get_aria_face(self) -> np.ndarray | None:
        from core.config import AVATAR_BASE_IMAGE
        if not AVATAR_BASE_IMAGE.exists():
            return None
        img = cv2.imread(str(AVATAR_BASE_IMAGE))
        if img is None:
            return None
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # ── Template picker ───────────────────────────────────────

    def _pick_template(self, job_id: int) -> dict:
        # Rotate based on job_id to ensure variety
        return TEMPLATES[job_id % len(TEMPLATES)]

    # ── Thumbnail builder ─────────────────────────────────────

    def _build_thumbnail(
        self,
        frame: np.ndarray,
        aria_face: np.ndarray | None,
        template: dict,
        hook_text: str,
        sub_text: str,
    ) -> Image.Image:
        img = Image.fromarray(frame).resize((THUMB_W, THUMB_H), Image.LANCZOS)

        # If avatar + split template: composite Aria on left
        if aria_face is not None and template["name"] == "split":
            aria_img = Image.fromarray(aria_face)
            aria_w = int(THUMB_W * 0.43)
            aria_h = THUMB_H
            aria_img = aria_img.resize((aria_w, aria_h), Image.LANCZOS)
            img.paste(aria_img, (0, 0))

        # Add dark gradient overlay for text readability
        img = self._add_gradient(img, template["gradient_side"])

        # Add text
        draw = ImageDraw.Draw(img)
        main_font = self._load_font(template["main_font_size"])
        sub_font  = self._load_font(template["sub_font_size"])

        text_x = int(THUMB_W * template["text_x_pct"])
        text_y = int(THUMB_H * template["text_y_pct"])
        max_w  = int(THUMB_W * 0.52)

        # Wrap text
        hook_lines = self._wrap_text(hook_text.upper(), main_font, max_w, draw)
        sub_lines  = self._wrap_text(sub_text, sub_font, max_w, draw)

        # Draw hook text (white + black stroke)
        y = text_y
        for line in hook_lines:
            # Stroke
            for dx, dy in [(-2,-2),(2,-2),(-2,2),(2,2)]:
                draw.text((text_x+dx, y+dy), line, font=main_font, fill=(0,0,0))
            draw.text((text_x, y), line, font=main_font, fill=(255,255,255))
            y += main_font.size + 8

        y += 12
        # Draw sub text (yellow)
        for line in sub_lines:
            for dx, dy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
                draw.text((text_x+dx, y+dy), line, font=sub_font, fill=(0,0,0))
            draw.text((text_x, y), line, font=sub_font, fill=(255,221,0))
            y += sub_font.size + 6

        # Add channel logo (top-right corner)
        if LOGO_PATH.exists():
            logo = Image.open(str(LOGO_PATH)).convert("RGBA")
            logo = logo.resize((80, 80), Image.LANCZOS)
            img.paste(logo, (THUMB_W - 95, 15), mask=logo.split()[3])

        return img

    def _add_gradient(self, img: Image.Image, side: str) -> Image.Image:
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if side == "right":
            for x in range(int(THUMB_W * 0.40), THUMB_W):
                alpha = int(200 * (x - THUMB_W * 0.40) / (THUMB_W * 0.60))
                draw.line([(x, 0), (x, THUMB_H)], fill=(0, 0, 0, alpha))
        elif side == "bottom":
            for y in range(int(THUMB_H * 0.50), THUMB_H):
                alpha = int(210 * (y - THUMB_H * 0.50) / (THUMB_H * 0.50))
                draw.line([(0, y), (THUMB_W, y)], fill=(0, 0, 0, alpha))
        elif side == "left":
            for x in range(0, int(THUMB_W * 0.55)):
                alpha = int(190 * (1 - x / (THUMB_W * 0.55)))
                draw.line([(x, 0), (x, THUMB_H)], fill=(0, 0, 0, alpha))

        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        return img.convert("RGB")

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont:
        font_candidates = [
            FONT_DIR / "Montserrat-Bold.ttf",
            FONT_DIR / "Impact.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        for path in font_candidates:
            if Path(path).exists():
                return ImageFont.truetype(str(path), size)
        return ImageFont.load_default()

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_w: int, draw: ImageDraw.Draw) -> list[str]:
        words = text.split()
        lines, current = [], ""
        for word in words:
            test = (current + " " + word).strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] > max_w and current:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)
        return lines[:3]  # max 3 lines

    def _get_hook_text(self, topic: dict, metadata: dict) -> str:
        hooks = topic.get("hook_angles", [])
        titles = metadata.get("title_options", [])
        if hooks:
            return hooks[0][:50]
        if titles:
            return titles[0][:50]
        return topic.get("title", "Finance Insight")[:50]

    def _get_sub_text(self, topic: dict) -> str:
        hooks = topic.get("hook_angles", [])
        if len(hooks) > 1:
            return hooks[1][:60]
        return "What they don't tell you"
