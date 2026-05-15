"""
First-run setup script — run once before starting the system.
Handles: Python venv creation (3.11), deps install, SadTalker clone,
         Kokoro model download, music setup, font download, avatar generation.

IMPORTANT: Run with ANY Python version — script creates .venv with Python 3.11.
All subsequent commands run INSIDE .venv automatically.

Usage:
  python setup_project.py                    # full setup (recommended)
  python setup_project.py --deps-only        # only install packages in .venv
  python setup_project.py --avatar           # generate Aria base image
  python setup_project.py --install-avatar   # clone SadTalker
  python setup_project.py --verify           # check what's installed
"""

import argparse
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

# Force UTF-8 output on Windows (prevents cp1252 encode errors)
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


ROOT   = Path(__file__).parent
DATA   = ROOT / "data"
MODELS = DATA / "models"
VENV   = ROOT / ".venv"

# Python 3.11 installer URL (Windows 64-bit)
PYTHON311_URL      = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
PYTHON311_INSTALLER = ROOT / "python311_installer.exe"

# Detect venv Python path
if sys.platform == "win32":
    VENV_PYTHON = VENV / "Scripts" / "python.exe"
    VENV_PIP    = VENV / "Scripts" / "pip.exe"
    VENV_ACTIVATE = str(VENV / "Scripts" / "activate.bat")
else:
    VENV_PYTHON = VENV / "bin" / "python"
    VENV_PIP    = VENV / "bin" / "pip"


def run(cmd: str, cwd: str | None = None, use_venv: bool = True) -> int:
    """Run shell command. use_venv=True runs inside .venv Python."""
    print(f"\n>>> {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    return result.returncode


def venv_run(cmd: str, cwd: str | None = None) -> int:
    """Run pip/python command inside .venv."""
    full_cmd = f'"{VENV_PYTHON}" {cmd}'
    return run(full_cmd, cwd=cwd, use_venv=False)


def step(msg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print('='*60)


# ── 0. Ensure Python 3.11 + venv ─────────────────────────────

def ensure_python311() -> str:
    """Find Python 3.11 on system or download installer."""
    step("Checking Python version")

    # Try py launcher first (Windows)
    for ver in ["3.11", "3.12"]:
        result = subprocess.run(
            f"py -{ver} --version", shell=True,
            capture_output=True, text=True
        )
        if result.returncode == 0:
            py_path = subprocess.run(
                f"py -{ver} -c \"import sys; print(sys.executable)\"",
                shell=True, capture_output=True, text=True
            ).stdout.strip()
            print(f"Found Python {ver}: {py_path}")
            return py_path

    # Not found — download Python 3.11
    print("\nPython 3.11/3.12 not found. Downloading Python 3.11.9 installer...")
    print("This is required — most ML packages don't support Python 3.14 yet.\n")
    urllib.request.urlretrieve(PYTHON311_URL, str(PYTHON311_INSTALLER), _progress_hook)
    print(f"\nDownloaded: {PYTHON311_INSTALLER}")

    # Run silent install (adds to PATH, installs for all users)
    print("Installing Python 3.11 (silent install)...")
    result = subprocess.run(
        f'"{PYTHON311_INSTALLER}" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1',
        shell=True
    )
    if result.returncode != 0:
        print("\nAuto-install failed. Please install manually:")
        print(f"  Download: {PYTHON311_URL}")
        print("  Run installer, check 'Add to PATH'")
        sys.exit(1)

    # Clean up installer
    PYTHON311_INSTALLER.unlink(missing_ok=True)

    # Try again after install
    result = subprocess.run(
        "py -3.11 --version", shell=True, capture_output=True, text=True
    )
    if result.returncode == 0:
        py_path = subprocess.run(
            "py -3.11 -c \"import sys; print(sys.executable)\"",
            shell=True, capture_output=True, text=True
        ).stdout.strip()
        return py_path

    print("Python 3.11 installed but not found via py launcher. Restart terminal and re-run setup.")
    sys.exit(1)


def create_venv(python_path: str) -> None:
    """Create .venv using Python 3.11."""
    if VENV_PYTHON.exists():
        print(f".venv already exists at {VENV}")
        return

    step(f"Creating virtual environment (.venv) with Python 3.11")
    result = subprocess.run(
        f'"{python_path}" -m venv "{VENV}"', shell=True
    )
    if result.returncode != 0:
        print("Failed to create venv")
        sys.exit(1)

    # Upgrade pip inside venv
    venv_run("-m pip install --upgrade pip")
    print(f"\n.venv created: {VENV}")
    print(f"To activate manually: {VENV_ACTIVATE}")


# ── 1. Install Python dependencies ────────────────────────────

def install_deps() -> None:
    step("Installing Python dependencies into .venv")

    # CPU-only PyTorch for Python 3.11 (no CUDA — saves ~3GB)
    # Latest CPU torch that supports Python 3.11
    venv_run(
        "-m pip install torch torchvision torchaudio "
        "--index-url https://download.pytorch.org/whl/cpu"
    )

    # Install all other requirements (excluding torch lines)
    # Filter out torch/torchvision/torchaudio from requirements.txt
    req_path = ROOT / "requirements.txt"
    filtered_req = ROOT / "requirements_filtered.txt"
    lines = req_path.read_text().splitlines()
    filtered = [
        l for l in lines
        if not any(l.strip().startswith(pkg) for pkg in
                   ["torch==", "torchvision==", "torchaudio==",
                    "torch ", "torchvision ", "torchaudio "])
    ]
    filtered_req.write_text("\n".join(filtered))

    venv_run(f"-m pip install -r \"{filtered_req}\"")
    filtered_req.unlink(missing_ok=True)
    print("\nAll dependencies installed in .venv")


# ── 2. Download Kokoro TTS model ──────────────────────────────

def download_kokoro() -> None:
    step("Downloading Kokoro TTS model (CPU-friendly, ~350MB)")
    MODELS.mkdir(parents=True, exist_ok=True)

    # Correct URLs (v1.0 from HuggingFace onnx-community)
    MODEL_URL  = "https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/onnx/model.onnx"
    VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

    model_file  = MODELS / "kokoro-v1.0.onnx"
    voices_file = MODELS / "voices.bin"

    if not model_file.exists():
        print("Downloading kokoro-v1.0.onnx (~310MB)...")
        try:
            urllib.request.urlretrieve(MODEL_URL, str(model_file), _progress_hook)
            print(f"\nSaved: {model_file}")
        except Exception as e:
            print(f"\nDirect download failed: {e}")
            print("Trying huggingface-cli fallback...")
            venv_run(f"-m pip install huggingface_hub")
            venv_run(
                f"-c \"from huggingface_hub import hf_hub_download; "
                f"hf_hub_download('onnx-community/Kokoro-82M-v1.0-ONNX', "
                f"filename='onnx/model.onnx', local_dir='{MODELS}')\""
            )
    else:
        print(f"Already exists: {model_file}")

    if not voices_file.exists():
        print("Downloading voices-v1.0.bin...")
        try:
            urllib.request.urlretrieve(VOICES_URL, str(voices_file), _progress_hook)
            print(f"\nSaved: {voices_file}")
        except Exception as e:
            print(f"\nVoices download failed: {e}")
            print(f"Download manually from: {VOICES_URL}")
            print(f"Save as: {voices_file}")
    else:
        print(f"Already exists: {voices_file}")


# ── 3. Clone SadTalker (avatar, CPU) ─────────────────────────

def install_sadtalker() -> None:
    step("Cloning SadTalker (CPU talking-head avatar)")
    sadtalker_dir = ROOT / "SadTalker"

    if not sadtalker_dir.exists():
        run("git clone https://github.com/OpenTalker/SadTalker.git")
        venv_run(f"-m pip install -r \"{sadtalker_dir / 'requirements.txt'}\"")
    else:
        print("SadTalker already cloned")

    # Download SadTalker model weights
    weights_dir = sadtalker_dir / "checkpoints"
    weights_dir.mkdir(exist_ok=True)

    weights_urls = {
        "SadTalker_V0.0.2_256.safetensors": (
            "https://huggingface.co/vinthony/SadTalker/resolve/main/"
            "SadTalker_V0.0.2_256.safetensors"
        ),
        "mapping_00109-model.pth.tar": (
            "https://huggingface.co/vinthony/SadTalker/resolve/main/"
            "mapping_00109-model.pth.tar"
        ),
        "mapping_00229-model.pth.tar": (
            "https://huggingface.co/vinthony/SadTalker/resolve/main/"
            "mapping_00229-model.pth.tar"
        ),
    }

    for fname, url in weights_urls.items():
        dest = weights_dir / fname
        if not dest.exists():
            print(f"Downloading {fname}...")
            urllib.request.urlretrieve(url, str(dest), _progress_hook)
            print()
        else:
            print(f"Already exists: {fname}")

    # Also need shape predictor for face detection
    gfpgan_dir = sadtalker_dir / "gfpgan" / "weights"
    gfpgan_dir.mkdir(parents=True, exist_ok=True)
    lm_file = gfpgan_dir / "shape_predictor_68_face_landmarks.dat"
    if not lm_file.exists():
        urllib.request.urlretrieve(
            "https://huggingface.co/spaces/vinthony/SadTalker/resolve/main/"
            "gfpgan/weights/shape_predictor_68_face_landmarks.dat",
            str(lm_file),
            _progress_hook,
        )
        print()


# ── 4. Download royalty-free music tracks ────────────────────

def download_music() -> None:
    step("Setting up royalty-free music library")
    music_dir = DATA / "music"
    music_dir.mkdir(parents=True, exist_ok=True)

    # These are from YouTube Audio Library (free, no attribution needed)
    # You need to manually download these from studio.youtube.com/channel/X/music
    # OR use Pixabay Music API — we create placeholder instructions
    readme = music_dir / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Add royalty-free music tracks here (MP3 format).\n\n"
            "Free sources:\n"
            "1. YouTube Audio Library: studio.youtube.com → Audio Library\n"
            "2. Pixabay Music: pixabay.com/music (free commercial use)\n"
            "3. Free Music Archive: freemusicarchive.org\n\n"
            "Download 5-10 calm instrumental tracks.\n"
            "Name them: track_01.mp3, track_02.mp3, etc.\n"
            "These will be randomly selected per video.\n"
        )
    print(f"Music dir ready: {music_dir}")
    print("ACTION NEEDED: Download 5-10 royalty-free MP3 tracks into data/music/")


# ── 5. Download fonts ─────────────────────────────────────────

def download_fonts() -> None:
    step("Setting up fonts for thumbnails")
    font_dir = DATA / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)

    # Montserrat Bold — open source (SIL license)
    font_url = (
        "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf"
    )
    font_path = font_dir / "Montserrat-Bold.ttf"
    if not font_path.exists():
        print("Downloading Montserrat-Bold.ttf...")
        urllib.request.urlretrieve(font_url, str(font_path), _progress_hook)
        print(f"\nSaved: {font_path}")
    else:
        print(f"Already exists: {font_path}")


# ── 6. Generate Aria avatar base image ───────────────────────

def generate_avatar() -> None:
    step("Generating Aria base image (FLUX.1 schnell, CPU — takes 5-15 min)")
    avatar_path = DATA / "avatar" / "aria_base.png"
    if avatar_path.exists():
        print(f"Aria base image already exists: {avatar_path}")
        overwrite = input("Regenerate? (y/N): ").strip().lower()
        if overwrite != "y":
            return

    from agents.avatar_agent import AvatarAgent
    AvatarAgent.generate_aria_base(avatar_path)
    print(f"Aria base image saved: {avatar_path}")


# ── 7. Create .env from template ─────────────────────────────

def create_env() -> None:
    step("Setting up .env file")
    env_file = ROOT / ".env"
    example  = ROOT / ".env.example"

    if env_file.exists():
        print(".env already exists — skipping")
        return

    if example.exists():
        import shutil
        shutil.copy(str(example), str(env_file))
        print(f"Created .env from template.")
        print("ACTION NEEDED: Fill in your API keys in .env")
    else:
        print(".env.example not found")


# ── 8. Verify setup ───────────────────────────────────────────

def verify_setup() -> None:
    step("Verifying setup")
    checks = {
        "Python 3.11 .venv":   VENV_PYTHON,
        "Kokoro ONNX model":   MODELS / "kokoro-v1.0.onnx",
        "Kokoro voices":       MODELS / "voices.bin",
        "Montserrat font":     DATA / "fonts" / "Montserrat-Bold.ttf",
        ".env file":           ROOT / ".env",
        "SadTalker":           ROOT / "SadTalker",
        "Music directory":     DATA / "music",
        "Policy reference":    DATA / "YOUTUBE_POLICY_REFERENCE.md",
    }

    all_ok = True
    for name, path in checks.items():
        exists = Path(path).exists()
        status = "[OK]" if exists else "[MISSING]"
        print(f"  {status} {name}: {path}")
        if not exists:
            all_ok = False

    print()
    if all_ok:
        print("[OK] All checks passed! Run: .venv\\Scripts\\python.exe main.py")
    else:
        print("[MISSING] Some items missing. Re-run setup or add manually.")


# ── Utilities ─────────────────────────────────────────────────

def _progress_hook(count, block_size, total_size):
    pct = min(int(count * block_size * 100 / max(total_size, 1)), 100)
    print(f"\r  Progress: {pct}%", end="", flush=True)


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="YouTube Automation Setup")
    parser.add_argument("--deps-only",        action="store_true", help="Only install Python deps")
    parser.add_argument("--install-avatar",   action="store_true", help="Clone SadTalker + download weights")
    parser.add_argument("--avatar",           action="store_true", help="Generate Aria base image (FLUX.1)")
    parser.add_argument("--verify",           action="store_true", help="Verify setup only")
    args = parser.parse_args()

    if args.verify:
        verify_setup()
        return

    if args.deps_only:
        install_deps()
        return

    if args.install_avatar:
        install_sadtalker()
        return

    if args.avatar:
        generate_avatar()
        return

    # Full setup
    print("\nYouTube Automation System — Full Setup")
    print("This will take 10-30 minutes (model downloads)\n")

    # Step 0: ensure Python 3.11 + create .venv
    py311 = ensure_python311()
    create_venv(py311)

    install_deps()
    download_kokoro()
    install_sadtalker()
    download_fonts()
    download_music()
    create_env()
    verify_setup()

    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("1. Fill in your API keys in .env")
    print("2. Add royalty-free MP3s to data/music/")
    print("3. Add your channel logo to data/channel_logo.png")
    print("4. Get YouTube OAuth credentials from Google Cloud Console")
    print("   → Save as data/youtube_client_secrets.json")
    print("5. Generate Aria avatar: python setup_project.py --avatar")
    print("6. Run: python main.py")
    print("="*60)


if __name__ == "__main__":
    main()
