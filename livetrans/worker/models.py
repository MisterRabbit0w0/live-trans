"""Speech models stored inside the runtime environment.

Loading never touches the network: a model is used only after an explicit
``download`` put it under ``models_dir()``, next to the interpreter that runs
it. A source checkout keeps them in ``<venv>/livetrans-models``, a frozen
build in ``models/`` beside the executable, an external runtime in its own
environment, so each model sits with the packages that can run it.
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger("livetrans.worker.models")

REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "tiny.en": "Systran/faster-whisper-tiny.en",
    "base.en": "Systran/faster-whisper-base.en",
    "small.en": "Systran/faster-whisper-small.en",
    "medium.en": "Systran/faster-whisper-medium.en",
}
# What faster-whisper itself fetches; weights in other formats are skipped.
FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]
REQUIRED = ("config.json", "model.bin")
MARKER = "livetrans-model.json"
PROGRESS_INTERVAL = 0.5

GPU_LARGE = ["large-v3-turbo", "large-v3", "medium", "small", "base", "tiny"]
SMALL = ["small", "base", "tiny"]


class ModelMissing(RuntimeError):
    """The requested model is not in this environment; ``str()`` is its name."""


def models_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "models"
    return Path(sys.prefix) / "livetrans-models"


def detect_free_vram_mb() -> int:
    """通过 nvidia-smi 查询空闲显存(MB)，无 NVIDIA 显卡返回 0。"""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, creationflags=flags,
        )
        if out.returncode != 0:
            return 0
        return max(int(line) for line in out.stdout.split() if line.strip().isdigit())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0


def candidates(free_vram_mb: int) -> tuple[list[str], str]:
    """Models that suit the hardware, best first, and the device to run them on.

    注意：Blackwell (RTX 50xx) 等新架构显卡上 int8_float16 可能触发
    cuBLAS 兼容性错误，CUDA 统一使用 float16 更安全。
    """
    if free_vram_mb >= 5_000:
        return GPU_LARGE, "cuda"
    if free_vram_mb >= 2_000:
        return SMALL, "cuda"
    return SMALL, "cpu"


def pick_model(free_vram_mb: int) -> tuple[str, str, str]:
    """根据空闲显存推荐 (model, device, compute_type)。"""
    names, device = candidates(free_vram_mb)
    return names[0], device, "float16" if device == "cuda" else "int8"


def repo_for(name: str) -> str:
    if "/" in name:
        return name  # a CTranslate2 conversion on the Hugging Face Hub
    try:
        return REPOS[name]
    except KeyError:
        raise ValueError(f"未知模型 {name}，可填写 {', '.join(REPOS)} 或 组织/仓库名") from None


def folder(name: str, root: Path | None = None) -> Path:
    name = name.strip()
    if not name or "\\" in name or ".." in name or name.startswith("/") or ":" in name:
        raise ValueError(f"无效的模型名 {name!r}")
    return (root or models_dir()) / name.replace("/", "--")


def is_installed(path: Path) -> bool:
    return (path / MARKER).is_file() and all((path / f).is_file() for f in REQUIRED)


def _size(path: Path, partial: bool = False) -> int:
    total = 0
    for file in path.rglob("*"):
        # Hub resume data lives under .cache; it only counts while downloading.
        if file.is_file() and (partial or ".cache" not in file.relative_to(path).parts):
            try:
                total += file.stat().st_size
            except OSError:
                pass
    return total


def installed(root: Path | None = None) -> list[dict]:
    root = root or models_dir()
    items = []
    if root.is_dir():
        for path in sorted(root.iterdir()):
            if path.is_dir() and is_installed(path):
                name = json.loads((path / MARKER).read_text("utf-8"))["name"]
                items.append({"name": name, "size": _size(path)})
    return items


def _writable(root: Path) -> bool:
    return os.access(root if root.exists() else root.parent, os.W_OK)


def listing(cuda: bool = True, root: Path | None = None) -> dict:
    root = root or models_dir()
    names, device = candidates(detect_free_vram_mb() if cuda else 0)
    items = installed(root)
    have = {item["name"] for item in items}
    return {"dir": str(root), "installed": items, "recommended": names[0],
            "auto": next((n for n in names if n in have), ""), "device": device,
            "writable": _writable(root)}


def resolve(model: str, root: Path | None = None) -> Path:
    """Directory of an installed model; an existing model directory path is used as is."""
    direct = Path(model).expanduser()
    if direct.is_absolute():
        if all((direct / f).is_file() for f in REQUIRED):
            return direct
        raise ModelMissing(model)
    path = folder(model, root)
    if not is_installed(path):
        raise ModelMissing(model)
    return path


def select(model: str = "auto", device: str = "auto", cuda: bool = True,
           root: Path | None = None) -> tuple[Path, str, str, str]:
    """Resolve settings to ``(path, model name, device, compute type)`` without downloading."""
    root = root or models_dir()
    vram = detect_free_vram_mb() if cuda and device != "cpu" else 0
    names, auto_device = candidates(vram)
    if device == "auto":
        device = auto_device
    if device == "cpu":
        names = SMALL
    if model == "auto":
        found = next((n for n in names if is_installed(folder(n, root))), None)
        if found is None:
            raise ModelMissing(names[0])
        model = found
    path = resolve(model, root)
    compute = "float16" if device == "cuda" else "int8"
    log.info("空闲显存 %d MB → 模型 %s @ %s (%s)", vram, model, device, compute)
    return path, model, device, compute


def _cached_snapshot(hub, repo: str) -> Path | None:
    """A copy in the user's Hugging Face cache, from before models lived in the environment."""
    try:
        path = Path(hub.snapshot_download(repo, allow_patterns=FILES, local_files_only=True))
    except Exception:
        return None
    return path if all((path / f).is_file() for f in REQUIRED) else None


def _remote_size(hub, repo: str) -> int:
    try:
        info = hub.HfApi().model_info(repo, files_metadata=True)
    except Exception:
        return 0  # progress without a total is still progress
    return sum(s.size or 0 for s in info.siblings or ()
               if any(fnmatch.fnmatch(s.rfilename, p) for p in FILES))


def _copy(source: Path, target: Path):
    for file in source.rglob("*"):
        if file.is_file():
            destination = target / file.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, destination)  # follows cache symlinks


def download(name: str, progress=lambda done, total: None, root: Path | None = None) -> Path:
    """Fetch ``name`` into the environment; an interrupted download resumes next time."""
    repo = repo_for(name)
    target = folder(name, root)
    target.mkdir(parents=True, exist_ok=True)
    (target / MARKER).unlink(missing_ok=True)
    # hf_xet reads its cache (including logs) from the process env, not local_dir.
    os.environ["HF_XET_CACHE"] = str(target / ".cache" / "xet")
    import huggingface_hub as hub

    cached = _cached_snapshot(hub, repo)
    total = sum(f.stat().st_size for f in cached.rglob("*") if f.is_file()) if cached \
        else _remote_size(hub, repo)
    stop = threading.Event()

    def report():
        while not stop.wait(PROGRESS_INTERVAL):
            progress(_size(target, partial=True), total)

    reporter = threading.Thread(target=report, name="livetrans-model-progress", daemon=True)
    reporter.start()
    try:
        if cached is not None:
            log.info("从 Hugging Face 缓存复制 %s → %s", repo, target)
            _copy(cached, target)
        else:
            log.info("下载 %s → %s", repo, target)
            hub.snapshot_download(repo, local_dir=target, allow_patterns=FILES)
    finally:
        stop.set()
        reporter.join()
    missing = [f for f in REQUIRED if not (target / f).is_file()]
    if missing:
        raise RuntimeError(f"{repo} 缺少 {', '.join(missing)}，不是 faster-whisper 模型")
    shutil.rmtree(target / ".cache", ignore_errors=True)
    (target / MARKER).write_text(json.dumps({"name": name, "repo": repo}), "utf-8")
    size = _size(target)
    progress(size, max(total, size))
    return target


def delete(name: str, root: Path | None = None) -> None:
    target = folder(name, root)
    if target.is_dir():
        shutil.rmtree(target)
