import os
import shutil
import subprocess
import time
from pathlib import Path


def test_clean_cache_removes_old_audio_and_uploads(tmp_path: Path):
    project = tmp_path / "Petagent"
    scripts = project / "scripts"
    audio_dir = project / "backend" / "static" / "audio"
    upload_dir = project / "backend" / "data" / "uploads"
    scripts.mkdir(parents=True)
    audio_dir.mkdir(parents=True)
    upload_dir.mkdir(parents=True)
    script = scripts / "clean_cache.sh"
    shutil.copyfile(Path(__file__).parents[2] / "scripts" / "clean_cache.sh", script)

    old_audio = audio_dir / "old.wav"
    old_upload = upload_dir / "old.webm"
    fresh_upload = upload_dir / "fresh.webm"
    old_audio.write_text("old audio", encoding="utf-8")
    old_upload.write_text("old upload", encoding="utf-8")
    fresh_upload.write_text("fresh upload", encoding="utf-8")
    old_time = time.time() - 5 * 24 * 60 * 60
    for path in (old_audio, old_upload):
        path.touch()
        path.chmod(0o600)
        os.utime(path, (old_time, old_time))

    subprocess.run(["sh", str(script)], check=True, capture_output=True, text=True)

    assert not old_audio.exists()
    assert not old_upload.exists()
    assert fresh_upload.exists()


def test_clean_cache_enforces_size_cap(tmp_path: Path):
    project = tmp_path / "Petagent"
    scripts = project / "scripts"
    audio_dir = project / "backend" / "static" / "audio"
    upload_dir = project / "backend" / "data" / "uploads"
    scripts.mkdir(parents=True)
    audio_dir.mkdir(parents=True)
    upload_dir.mkdir(parents=True)
    script = scripts / "clean_cache.sh"
    shutil.copyfile(Path(__file__).parents[2] / "scripts" / "clean_cache.sh", script)

    older = audio_dir / "older.wav"
    newer = audio_dir / "newer.wav"
    older.write_bytes(b"x" * 900_000)
    newer.write_bytes(b"x" * 900_000)
    now = time.time()
    os.utime(older, (now - 20, now - 20))
    os.utime(newer, (now, now))
    env = dict(os.environ)
    env["PETAGENT_MAX_AUDIO_CACHE_MB"] = "1"

    subprocess.run(
        ["sh", str(script)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert not older.exists()
    assert newer.exists()
