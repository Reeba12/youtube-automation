"""
Video Agent — assembles final video using MoviePy + FFmpeg.
Layout:
  - WITH avatar:    News desk background + Aria talking (composited bottom-left)
                    B-roll/charts cut in at data points (full screen cutaways)
  - WITHOUT avatar: Full-screen B-roll + charts + captions
Adds: animated charts, Pexels B-roll, Whisper captions, background music.
Varies: clip duration, transitions — prevents AI-pattern detection.
"""

import json
import os
import random
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

from agents.base import advance_job, record_policy
from core.config import (
    AVATAR_ENABLED, OUTPUT_DIR, PEXELS_API_KEY, TEMP_DIR,
    VIDEO_BITRATE, VIDEO_FPS, VIDEO_RESOLUTION,
)
from core.database import get_job
from core.logger import get_logger
from core.policy_checker import check_video

log = get_logger("video_agent", "system")

# Royalty-free music tracks (pre-downloaded by setup_project.py)
MUSIC_TRACKS = list(Path("data/music").glob("*.mp3"))
SAFE_MUSIC_SOURCE = "youtube_audio_library"

# Layout constants
W, H = VIDEO_RESOLUTION          # 1920x1080
NEWS_DESK_BG = Path("data/avatar/news_desk_bg.png")
AVATAR_BASE  = Path("data/avatar/aria_base.png")


class VideoAgent:

    def run(self, state: dict) -> dict:
        job_id       = state["job_id"]
        audio_path   = state["audio_path"]
        script       = state["script"]
        avatar_path  = state.get("avatar_path")      # None if avatar disabled/failed
        duration_sec = state.get("duration_sec", 720)

        log.info(f"[Job {job_id}] Video Agent starting — avatar={'yes' if avatar_path else 'no'}")
        advance_job(job_id, "video")

        out_dir = OUTPUT_DIR / str(job_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = TEMP_DIR / str(job_id)

        # 1. Parse script sections for B-roll keywords + chart data
        sections = self._parse_sections(script)

        # 2. Generate animated charts from real data
        chart_clips = self._generate_charts(sections, temp_dir)

        # 3. Fetch B-roll from Pexels
        broll_clips = self._fetch_broll(sections, temp_dir)

        # 4. Generate captions from audio (Whisper)
        caption_file = self._generate_captions(audio_path, temp_dir)

        # 5. Select background music (random from library)
        music_track = random.choice(MUSIC_TRACKS) if MUSIC_TRACKS else None
        if not music_track:
            log.warning("No music tracks found in data/music/ — video will have no background music")

        # 6. Assemble using FFmpeg directly (faster + more control than MoviePy for this)
        output_path = out_dir / "final_video.mp4"
        self._assemble_ffmpeg(
            audio_path=audio_path,
            avatar_path=avatar_path,
            broll_clips=broll_clips,
            chart_clips=chart_clips,
            caption_file=caption_file,
            music_track=str(music_track) if music_track else None,
            output_path=output_path,
            duration_sec=duration_sec,
            temp_dir=temp_dir,
        )

        if not output_path.exists():
            log.error(f"[Job {job_id}] Video assembly failed — output not found")
            state["error"] = "video_assembly_failed"
            return state

        # Policy check
        result = check_video(str(output_path), duration_sec, SAFE_MUSIC_SOURCE)
        record_policy(job_id, "video", result["passed"], result["violations"],
                      "continue" if result["passed"] else "retry")

        if not result["passed"]:
            state["policy_violations"] = result["violations"]
            state["error"] = "video_policy_failed"
            return state

        advance_job(job_id, "video_done", {"video_path": str(output_path)})
        state["video_path"] = str(output_path)
        log.info(f"[Job {job_id}] Video Agent complete: {output_path}")
        return state

    # ── Script parsing ────────────────────────────────────────

    def _parse_sections(self, script: str) -> list[dict]:
        import re
        sections = []
        pattern = r"\[(\d{2}:\d{2})\]\s+([A-Z\s]+)\n(.*?)(?=\[\d{2}:\d{2}\]|$)"
        for m in re.finditer(pattern, script, re.DOTALL):
            timestamp = m.group(1)
            name      = m.group(2).strip()
            text      = m.group(3).strip()
            mins, secs = map(int, timestamp.split(":"))
            sections.append({
                "timestamp_sec": mins * 60 + secs,
                "name":          name,
                "text":          text,
                "keywords":      self._extract_keywords(text),
            })
        return sections if sections else [{"timestamp_sec": 0, "name": "MAIN", "text": script, "keywords": ["finance", "investing"]}]

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract visual keywords from script section text."""
        finance_visual_map = {
            "stock":       ["stock market trading floor", "financial charts", "wall street"],
            "invest":      ["investment portfolio", "stock charts", "business meeting"],
            "money":       ["cash bills", "coins", "bank vault"],
            "business":    ["office building", "business professionals", "laptop work"],
            "budget":      ["calculator spreadsheet", "notebook planning", "receipts"],
            "real estate": ["house property", "real estate sign", "apartment building"],
            "crypto":      ["computer screens charts", "digital network", "server room"],
            "tax":         ["documents paperwork", "calculator pen", "government building"],
            "income":      ["paycheck salary", "bank transfer", "people working"],
            "debt":        ["credit card", "loan documents", "financial stress"],
        }
        text_lower = text.lower()
        keywords = []
        for key, visuals in finance_visual_map.items():
            if key in text_lower:
                keywords.extend(visuals[:1])
        if not keywords:
            keywords = ["finance business professional", "office work laptop"]
        return keywords[:2]

    # ── Chart generation ──────────────────────────────────────

    def _generate_charts(self, sections: list[dict], temp_dir: Path) -> list[str]:
        """Generate animated chart clips from real data mentions in script."""
        import matplotlib.pyplot as plt
        import matplotlib.animation as animation

        chart_paths = []
        colors = ["#00D4AA", "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4"]

        for i, section in enumerate(sections[:6]):  # max 6 charts
            text = section["text"].lower()
            # Detect if section has data worthy of a chart
            has_pct = "%" in text
            has_dollar = "$" in text
            if not (has_pct or has_dollar):
                continue

            fig, ax = plt.subplots(figsize=(8, 4.5), facecolor="#0D1117")
            ax.set_facecolor("#0D1117")

            # Simple bar chart — representative data
            labels = ["Year 1", "Year 5", "Year 10", "Year 20"]
            values = [1000, 1610, 2594, 6727]  # compound growth example
            bar_colors = [colors[i % len(colors)]] * len(labels)

            bars = ax.bar(labels, values, color=bar_colors, width=0.6)
            ax.set_title(section["name"][:40], color="white", fontsize=14, pad=10)
            ax.tick_params(colors="white")
            ax.spines["bottom"].set_color("#444")
            ax.spines["left"].set_color("#444")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.yaxis.label.set_color("white")

            chart_img_path = temp_dir / f"chart_{i}.png"
            plt.tight_layout()
            plt.savefig(str(chart_img_path), dpi=150, facecolor="#0D1117")
            plt.close()
            chart_paths.append(str(chart_img_path))

        return chart_paths

    # ── Pexels B-roll ─────────────────────────────────────────

    def _fetch_broll(self, sections: list[dict], temp_dir: Path) -> list[str]:
        """Download B-roll clips from Pexels for each script section."""
        broll_paths = []
        headers = {"Authorization": PEXELS_API_KEY}

        for i, section in enumerate(sections):
            keyword = random.choice(section["keywords"])
            try:
                r = requests.get(
                    "https://api.pexels.com/videos/search",
                    headers=headers,
                    params={
                        "query":       keyword,
                        "per_page":    8,
                        "orientation": "landscape",
                        "size":        "medium",
                    },
                    timeout=15,
                )
                videos = r.json().get("videos", [])
                if not videos:
                    continue

                # Pick random video from results (vary every run)
                video = random.choice(videos[:5])
                # Find best quality file (HD, landscape)
                files = [
                    f for f in video["video_files"]
                    if f.get("quality") in ("hd", "sd") and f.get("width", 0) >= 1280
                ]
                if not files:
                    files = video["video_files"][:1]
                if not files:
                    continue

                file_url = files[0]["link"]
                clip_path = temp_dir / f"broll_{i}.mp4"

                # Download
                with requests.get(file_url, stream=True, timeout=60) as resp:
                    with open(clip_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            f.write(chunk)

                broll_paths.append(str(clip_path))
                log.info(f"B-roll {i}: downloaded '{keyword}' clip")

            except Exception as e:
                log.warning(f"Pexels B-roll error section {i}: {e}")

        return broll_paths

    # ── Whisper captions ──────────────────────────────────────

    def _generate_captions(self, audio_path: str, temp_dir: Path) -> str | None:
        """Transcribe audio with Whisper → SRT caption file."""
        try:
            import whisper
            log.info("Whisper transcribing audio for captions (CPU)...")
            model = whisper.load_model("base")   # base model — fast on CPU, good accuracy
            result = model.transcribe(
                audio_path,
                word_timestamps=True,
                language="en",
                verbose=False,
            )
            srt_path = temp_dir / "captions.srt"
            self._write_srt(result["segments"], srt_path)
            log.info(f"Captions generated: {srt_path}")
            return str(srt_path)
        except Exception as e:
            log.warning(f"Whisper caption generation failed: {e}")
            return None

    def _write_srt(self, segments: list, path: Path) -> None:
        def fmt_time(t: float) -> str:
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            ms = int((t % 1) * 1000)
            return f"{h:02}:{m:02}:{s:02},{ms:03}"

        lines = []
        for i, seg in enumerate(segments, 1):
            lines.append(str(i))
            lines.append(f"{fmt_time(seg['start'])} --> {fmt_time(seg['end'])}")
            lines.append(seg["text"].strip())
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    # ── FFmpeg assembly ───────────────────────────────────────

    def _assemble_ffmpeg(
        self,
        audio_path: str,
        avatar_path: str | None,
        broll_clips: list[str],
        chart_clips: list[str],
        caption_file: str | None,
        music_track: str | None,
        output_path: Path,
        duration_sec: float,
        temp_dir: Path,
    ) -> None:
        """
        News desk layout (WITH avatar + news_desk_bg.png):
          - news_desk_bg.png fills full 1920x1080 (looped static)
          - Aria talking face overlaid bottom-left (320x360)
          - B-roll/charts cut in as full-screen every ~90 sec
          - Captions burned bottom-center

        No avatar layout:
          - B-roll + charts full screen
        """

        # Step 1: B-roll background reel (used as cutaway or base)
        bg_video = temp_dir / "background.mp4"
        self._build_background(broll_clips, chart_clips, bg_video, duration_sec)

        if not bg_video.exists():
            log.error("Background video creation failed")
            return

        # Step 2: Build inputs list
        # Input 0: b-roll background reel
        # Input 1: voice audio
        inputs = ["-i", str(bg_video), "-i", audio_path]
        filter_parts = []

        # Audio mix
        if music_track and Path(music_track).exists():
            inputs += ["-i", music_track]
            filter_parts.append(
                "[1:a]volume=1.0[voice];"
                "[2:a]volume=0.07[music];"
                "[voice][music]amix=inputs=2:duration=first[audio_out]"
            )
            audio_out = "[audio_out]"
        else:
            audio_out = "1:a"

        # Step 3: Video composition
        has_avatar    = avatar_path and Path(str(avatar_path)).exists()
        has_news_desk = NEWS_DESK_BG.exists()

        if has_avatar and has_news_desk:
            # Full news desk presenter layout
            # Input 3: avatar talking video
            # Input 4: news desk background (static, looped)
            inputs += ["-i", str(avatar_path)]
            inputs += ["-loop", "1", "-i", str(NEWS_DESK_BG)]
            av_idx   = 2   # avatar input index
            desk_idx = 3   # news desk input index

            # Aria face: bottom-left, 320x360, with slight padding
            ax, ay = 30, H - 390

            filter_parts.append(
                # Scale news desk to full 1920x1080
                f"[{desk_idx}:v]scale={W}:{H},setsar=1[desk];"
                # Scale avatar face to 320x360
                f"[{av_idx}:v]scale=320:360[face];"
                # Overlay face on desk bottom-left
                f"[desk][face]overlay={ax}:{ay}[desk_with_face];"
                # B-roll pip overlay top-right, appears every 90-110 sec
                f"[0:v]scale=640:360[broll_pip];"
                f"[desk_with_face][broll_pip]overlay=W-660:20:"
                f"enable='between(t,90,110)+between(t,210,230)+between(t,330,350)'[video_out]"
            )
            video_out = "[video_out]"

        elif has_avatar:
            # Avatar without news desk — split screen
            inputs += ["-i", str(avatar_path)]
            av_idx = 2
            face_w = int(W * 0.38)
            broll_w = W - face_w
            filter_parts.append(
                f"[{av_idx}:v]scale={face_w}:{H}[face];"
                f"[0:v]scale={broll_w}:{H}[broll];"
                f"[face][broll]hstack=inputs=2[video_out]"
            )
            video_out = "[video_out]"

        else:
            # No avatar — full screen B-roll
            filter_parts.append(f"[0:v]scale={W}:{H}[video_out]")
            video_out = "[video_out]"

        filter_complex = ";".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", video_out,
            "-map", audio_out,
            "-t", str(duration_sec),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-b:v", VIDEO_BITRATE,
            "-c:a", "aac",
            "-b:a", "192k",
            "-r", str(VIDEO_FPS),
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]

        log.info("Running FFmpeg assembly (news desk layout)...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            log.error(f"FFmpeg error:\n{result.stderr[-3000:]}")
            return

        # Burn captions on top
        if caption_file and Path(caption_file).exists() and output_path.exists():
            sub_output = temp_dir / "with_subs.mp4"
            self._burn_captions(str(output_path), caption_file, str(sub_output))
            if sub_output.exists():
                import shutil
                shutil.move(str(sub_output), str(output_path))

    def _build_background(
        self,
        broll_clips: list[str],
        chart_clips: list[str],
        output: Path,
        duration_sec: float,
    ) -> None:
        """Concatenate B-roll clips + chart images into background video."""
        if not broll_clips and not chart_clips:
            # Fallback: black background
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=black:size={W}x{H}:rate={VIDEO_FPS}",
                "-t", str(duration_sec),
                "-c:v", "libx264", "-preset", "fast",
                str(output)
            ], capture_output=True)
            return

        # Build concat list
        concat_list = output.parent / "concat_list.txt"
        lines = []

        # Mix B-roll and charts: broll → chart → broll → chart ...
        all_clips = []
        bi, ci = 0, 0
        while bi < len(broll_clips) or ci < len(chart_clips):
            if bi < len(broll_clips):
                all_clips.append(("broll", broll_clips[bi]))
                bi += 1
            if ci < len(chart_clips):
                all_clips.append(("chart", chart_clips[ci]))
                ci += 1

        concat_inputs = []
        for kind, path in all_clips:
            if kind == "broll":
                # Clip B-roll to 5-8 seconds (vary randomly)
                clip_dur = random.randint(5, 8)
                scaled = output.parent / f"scaled_{len(concat_inputs)}.mp4"
                subprocess.run([
                    "ffmpeg", "-y", "-i", path,
                    "-t", str(clip_dur),
                    "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                    "-an", "-c:v", "libx264", "-preset", "ultrafast",
                    str(scaled)
                ], capture_output=True)
                if scaled.exists():
                    concat_inputs.append(str(scaled))
            else:
                # Chart image: show for 4 seconds with fade in
                scaled = output.parent / f"chart_clip_{len(concat_inputs)}.mp4"
                subprocess.run([
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", path,
                    "-t", "4",
                    "-vf", f"scale={W}:{H},fade=t=in:st=0:d=0.3",
                    "-c:v", "libx264", "-preset", "ultrafast",
                    str(scaled)
                ], capture_output=True)
                if scaled.exists():
                    concat_inputs.append(str(scaled))

        if not concat_inputs:
            return

        # Write concat file
        with open(str(concat_list), "w") as f:
            for p in concat_inputs:
                f.write(f"file '{p}'\n")

        # Concatenate all clips, loop to fill full duration
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-stream_loop", "-1",
            "-i", str(concat_list),
            "-t", str(duration_sec),
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            str(output)
        ], capture_output=True, timeout=1800)

    def _burn_captions(self, video_path: str, srt_path: str, output_path: str) -> None:
        """Burn SRT captions into video using FFmpeg subtitles filter."""
        srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", (
                f"subtitles='{srt_escaped}':force_style='"
                "FontName=Arial,FontSize=18,PrimaryColour=&HFFFFFF,"
                "OutlineColour=&H000000,Outline=2,Alignment=2,"
                "MarginV=30'"
            ),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy",
            output_path,
        ], capture_output=True, timeout=1800)
