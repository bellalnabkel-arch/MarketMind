"""Create a portable source ZIP without environments, secrets, caches or VCS data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
target = root.parent / "MarketMind_Streamlit.zip"
excluded = {".venv", "__pycache__", ".pytest_cache", ".git", ".cache"}
with ZipFile(target, "w", ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or set(relative.parts) & excluded or path.name in {".env", "secrets.toml"}:
            continue
        archive.write(path, Path("MarketMind_Streamlit") / relative)
with ZipFile(target) as archive:
    assert archive.testzip() is None
    assert "MarketMind_Streamlit/app.py" in archive.namelist()
print(f"{target} ({target.stat().st_size:,} bytes)")
