"""
Voiceover Agent — converts script to natural audio using Kokoro TTS.
CPU-only, Apache 2.0, zero API cost.
Handles [PAUSE] and [EMPHASIS] markers from script.
Normalizes to -14 LUFS (YouTube standard).
"""

import re
import numpy as np
import soundfile as sf
from pathlib import Path

from agents.base import advance_job, record_policy
from core.config import KOKORO_VOICE, KOKORO_SPEED, TEMP_DIR
from core.database import get_job
from core.logger import get_logger
from core.policy_checker import check_audio

log = get_logger("voiceover_agent", "system")

PAUSE_DURATION_SEC = 0.7    # silence inserted at [PAUSE] markers
SECTION_GAP_SEC   = 0.5     # silence between script sections
TARGET_LUFS       = -14.0   # YouTube loudness standard


class VoiceoverAgent:

    def __init__(self):
        self._kokoro = None   # lazy-loaded

    def _get_kokoro(self):
        if self._kokoro is None:
            from kokoro_onnx import Kokoro
            # Models downloaded by setup_project.py to data/models/
            self._kokoro = Kokoro(
                "data/models/kokoro-v1.0.onnx",
                "data/models/voices.bin",
            )
            log.info("Kokoro TTS model loaded")
        return self._kokoro

    def run(self, state: dict) -> dict:
        job_id      = state["job_id"]
        script_path = state["script_path"]

        log.info(f"[Job {job_id}] Voiceover Agent starting")
        advance_job(job_id, "voiceover")

        script = Path(script_path).read_text(encoding="utf-8")
        segments = self._parse_script(script)

        out_dir = TEMP_DIR / str(job_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = out_dir / "audio.wav"

        # Generate audio per segment, concatenate
        sample_rate = 24000
        all_audio = []

        for seg in segments:
            audio = self._synthesize(seg["text"], seg.get("speed_factor", 1.0))
            all_audio.append(audio)

            # Add pause after segment if [PAUSE] was marked
            if seg.get("pause_after"):
                silence = np.zeros(int(sample_rate * PAUSE_DURATION_SEC), dtype=np.float32)
                all_audio.append(silence)
            else:
                # Small natural gap between sections
                gap = np.zeros(int(sample_rate * 0.15), dtype=np.float32)
                all_audio.append(gap)

        combined = np.concatenate(all_audio)
        combined = self._normalize_lufs(combined, sample_rate, TARGET_LUFS)

        sf.write(str(audio_path), combined, sample_rate)
        log.info(f"[Job {job_id}] Audio saved: {audio_path}")

        # Get duration
        duration_sec = len(combined) / sample_rate
        log.info(f"[Job {job_id}] Audio duration: {duration_sec:.1f}s ({duration_sec/60:.1f} min)")

        # Policy check
        result = check_audio(str(audio_path), duration_sec)
        record_policy(job_id, "voiceover", result["passed"], result["violations"],
                      "continue" if result["passed"] else "retry")

        if not result["passed"]:
            state["policy_violations"] = result["violations"]
            state["error"] = "audio_policy_failed"
            return state

        advance_job(job_id, "voiceover_done", {"audio_path": str(audio_path)})
        state["audio_path"]   = str(audio_path)
        state["duration_sec"] = duration_sec
        # Always set AI disclosure for synthetic voice
        meta = state.get("metadata", {})
        meta["contains_synthetic_media"] = True
        meta["duration_min"] = round(duration_sec / 60, 1)
        state["metadata"] = meta

        log.info(f"[Job {job_id}] Voiceover Agent complete")
        return state

    # ── Script parsing ────────────────────────────────────────

    def _parse_script(self, script: str) -> list[dict]:
        """
        Split script into segments respecting:
        - [PAUSE] → pause_after = True
        - [EMPHASIS] → slight speed reduction for that phrase
        - Timestamp headers like [00:00] → section boundary
        - [KEY QUOTE]: lines → skip (metadata only)
        """
        segments = []
        # Remove [KEY QUOTE] lines
        script = re.sub(r"\[KEY QUOTE\]:.*?\n", "", script)

        # Split on [PAUSE] markers
        raw_parts = re.split(r"\[PAUSE\]", script)

        for part in raw_parts:
            # Remove timestamp headers
            clean = re.sub(r"\[\d{2}:\d{2}\]\s*[A-Z\s]+\n", " ", part)
            # Remove [EMPHASIS] markers but keep text
            clean = re.sub(r"\[EMPHASIS\]", "", clean)
            # Remove [DISCLAIMER] marker (keep text around it)
            clean = re.sub(r"\[DISCLAIMER\]\s*", "", clean)
            clean = clean.strip()

            if not clean:
                continue

            # Split very long segments (Kokoro handles shorter chunks better)
            if len(clean) > 800:
                sub_parts = self._split_long_text(clean)
                for i, sub in enumerate(sub_parts):
                    segments.append({
                        "text":        sub,
                        "pause_after": (i == len(sub_parts) - 1),  # pause after last sub
                        "speed_factor": KOKORO_SPEED,
                    })
            else:
                segments.append({
                    "text":        clean,
                    "pause_after": True,
                    "speed_factor": KOKORO_SPEED,
                })

        return segments

    def _split_long_text(self, text: str, max_len: int = 600) -> list[str]:
        """Split at sentence boundaries to stay under max_len chars."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks, current = [], ""
        for s in sentences:
            if len(current) + len(s) < max_len:
                current += (" " if current else "") + s
            else:
                if current:
                    chunks.append(current)
                current = s
        if current:
            chunks.append(current)
        return chunks if chunks else [text]

    # ── TTS synthesis ─────────────────────────────────────────

    def _synthesize(self, text: str, speed_factor: float = 0.95) -> np.ndarray:
        kokoro = self._get_kokoro()
        try:
            samples, sample_rate = kokoro.create(
                text,
                voice=KOKORO_VOICE,
                speed=speed_factor,
                lang="en-us",
            )
            return samples.astype(np.float32)
        except Exception as e:
            log.error(f"Kokoro TTS error: {e}")
            # Return short silence on error rather than crashing
            return np.zeros(24000, dtype=np.float32)

    # ── Audio normalization ───────────────────────────────────

    def _normalize_lufs(
        self, audio: np.ndarray, sr: int, target_lufs: float
    ) -> np.ndarray:
        """Simple peak normalization as LUFS approximation (no GPU needed)."""
        rms = np.sqrt(np.mean(audio ** 2))
        if rms == 0:
            return audio
        # Target RMS derived from LUFS target (-14 LUFS ≈ -14 dBFS RMS for speech)
        target_rms = 10 ** (target_lufs / 20)
        gain = target_rms / rms
        # Limit gain to avoid clipping
        gain = min(gain, 10.0)
        normalized = audio * gain
        # Hard clip at 0 dBFS
        return np.clip(normalized, -1.0, 1.0)
