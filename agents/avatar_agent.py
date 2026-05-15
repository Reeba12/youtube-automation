"""
Avatar Agent — generates talking-head video of Aria using SadTalker (CPU).
Input:  data/avatar/aria_base.png + temp/{job_id}/audio.wav
Output: temp/{job_id}/aria_talking.mp4

SadTalker runs on CPU (slow but works — starts Monday night, done Tuesday morning).
Upgrade path: swap AVATAR_ENGINE = "musetalk" when GPU available (1 line change).

First-time setup: setup_project.py clones SadTalker and downloads model weights.
"""

import os
import subprocess
import sys
from pathlib import Path

from agents.base import advance_job, record_policy
from core.config import AVATAR_BASE_IMAGE, AVATAR_ENABLED, TEMP_DIR
from core.logger import get_logger

log = get_logger("avatar_agent", "system")

SADTALKER_DIR  = Path("SadTalker")                     # cloned by setup_project.py
AVATAR_ENGINE  = "sadtalker"                            # swap to "musetalk" when GPU ready
OUTPUT_SIZE    = 256                                    # 256px → upscaled in video agent


class AvatarAgent:

    def run(self, state: dict) -> dict:
        job_id     = state["job_id"]
        audio_path = state["audio_path"]

        if not AVATAR_ENABLED:
            log.info(f"[Job {job_id}] Avatar disabled in config — skipping")
            state["avatar_path"] = None
            return state

        if not AVATAR_BASE_IMAGE.exists():
            log.error(f"Avatar base image not found: {AVATAR_BASE_IMAGE}")
            log.error("Run: python setup_project.py --generate-avatar")
            state["avatar_path"] = None
            return state

        log.info(f"[Job {job_id}] Avatar Agent starting (engine={AVATAR_ENGINE})")
        advance_job(job_id, "avatar")

        out_dir = TEMP_DIR / str(job_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        if AVATAR_ENGINE == "sadtalker":
            avatar_path = self._run_sadtalker(audio_path, out_dir, job_id)
        elif AVATAR_ENGINE == "musetalk":
            avatar_path = self._run_musetalk(audio_path, out_dir, job_id)
        else:
            log.error(f"Unknown avatar engine: {AVATAR_ENGINE}")
            state["avatar_path"] = None
            return state

        if avatar_path and Path(avatar_path).exists():
            log.info(f"[Job {job_id}] Avatar video generated: {avatar_path}")
            advance_job(job_id, "avatar_done", {"avatar_path": avatar_path})
            state["avatar_path"] = avatar_path
        else:
            log.warning(f"[Job {job_id}] Avatar generation failed — will use static image fallback")
            state["avatar_path"] = None

        return state

    # ── SadTalker (CPU) ───────────────────────────────────────

    def _run_sadtalker(self, audio_path: str, out_dir: Path, job_id: int) -> str | None:
        if not SADTALKER_DIR.exists():
            log.error("SadTalker not found. Run: python setup_project.py --install-avatar")
            return None

        output_path = out_dir / "aria_talking.mp4"

        cmd = [
            sys.executable,
            str(SADTALKER_DIR / "inference.py"),
            "--driven_audio",   audio_path,
            "--source_image",   str(AVATAR_BASE_IMAGE),
            "--result_dir",     str(out_dir),
            "--still",                          # less head motion (more stable on CPU)
            "--preprocess",     "crop",
            "--size",           str(OUTPUT_SIZE),
            "--cpu",                            # force CPU inference
            "--enhancer",       "none",         # skip GFPGAN enhancer (needs GPU)
        ]

        log.info(f"[Job {job_id}] Running SadTalker (CPU — may take 20-40 min for 12-min audio)")
        log.info(f"Command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(SADTALKER_DIR),
                capture_output=True,
                text=True,
                timeout=7200,  # 2 hour timeout for long videos on CPU
            )
            if result.returncode != 0:
                log.error(f"SadTalker failed:\n{result.stderr[-2000:]}")
                return None

            # SadTalker saves to result_dir with auto-named file
            # Find the generated mp4
            generated = list(out_dir.glob("*.mp4"))
            if generated:
                mp4 = generated[0]
                mp4.rename(output_path)
                return str(output_path)
            log.error("SadTalker ran but no .mp4 output found")
            return None

        except subprocess.TimeoutExpired:
            log.error(f"[Job {job_id}] SadTalker timed out after 2 hours")
            return None
        except Exception as e:
            log.error(f"[Job {job_id}] SadTalker exception: {e}")
            return None

    # ── MuseTalk (GPU — future) ───────────────────────────────

    def _run_musetalk(self, audio_path: str, out_dir: Path, job_id: int) -> str | None:
        """
        Placeholder for MuseTalk GPU pipeline.
        Swap AVATAR_ENGINE = "musetalk" in this file when GPU is available.
        Install: setup_project.py --install-musetalk
        """
        log.info(f"[Job {job_id}] MuseTalk engine selected (GPU required)")
        musetalk_dir = Path("MuseTalk")
        if not musetalk_dir.exists():
            log.error("MuseTalk not found. Run: python setup_project.py --install-musetalk")
            return None

        output_path = out_dir / "aria_talking.mp4"
        cmd = [
            sys.executable,
            str(musetalk_dir / "scripts" / "inference.py"),
            "--unet_config",     str(musetalk_dir / "models/musetalk/musetalk.json"),
            "--unet_model_path", str(musetalk_dir / "models/musetalk/pytorch_model.bin"),
            "--avatar_image",    str(AVATAR_BASE_IMAGE),
            "--audio_path",      audio_path,
            "--result_dir",      str(out_dir),
            "--fps",             "25",
            "--batch_size",      "8",
        ]
        try:
            subprocess.run(cmd, check=True, timeout=3600)
            generated = list(out_dir.glob("*.mp4"))
            if generated:
                generated[0].rename(output_path)
                return str(output_path)
        except Exception as e:
            log.error(f"MuseTalk error: {e}")
        return None

    # ── Avatar base image generator (FLUX.1 schnell, CPU) ────

    @staticmethod
    def generate_aria_base(output_path: Path | None = None) -> str:
        """
        One-time: generate Aria's base image using Stable Diffusion 1.5.
        Fully open — no HuggingFace login, no gated access needed.
        Model: ~4GB download. CPU inference: ~10-20 min.
        Call: python -c "from agents.avatar_agent import AvatarAgent; AvatarAgent.generate_aria_base()"
        """
        import torch
        from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler

        out = output_path or AVATAR_BASE_IMAGE
        out.parent.mkdir(parents=True, exist_ok=True)

        log.info("Loading Stable Diffusion 1.5 (CPU) — downloading ~4GB first time...")
        pipe = StableDiffusionPipeline.from_pretrained(
            "runwayml/stable-diffusion-v1-5",
            torch_dtype=torch.float32,   # float32 for CPU (no float16 support)
            safety_checker=None,          # disable — we control the prompt
            requires_safety_checker=False,
        )

        # Faster scheduler
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
        pipe.enable_attention_slicing()   # reduce RAM usage

        prompt = (
            "headshot portrait of a professional woman, early 30s, "
            "confident friendly smile, finance analyst, business casual, "
            "full face visible, centered face, head and shoulders only, "
            "neutral gray studio background, soft front lighting, "
            "photorealistic DSLR photography, looking directly at camera, "
            "sharp focus, high detail, no text, no watermark, "
            "symmetrical face, clear eyes"
        )
        negative_prompt = (
            "cartoon, anime, illustration, painting, blurry, ugly, "
            "deformed, cropped face, cut off, half face, out of frame, "
            "extra limbs, watermark, text, logo, multiple people, "
            "body below shoulders, full body, far away"
        )

        log.info("Generating Aria base image (CPU — 25 steps, ~15-25 min)...")
        image = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=25,
            guidance_scale=8.0,
            height=512,
            width=512,
        ).images[0]

        image.save(str(out))
        log.info(f"Aria base image saved: {out}")
        return str(out)
