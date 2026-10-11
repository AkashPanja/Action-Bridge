import json
from pathlib import Path
from graphify.detect import detect
from graphify.paths import out_path
from graphify.watch import _read_build_excludes, _read_build_gitignore

result = detect(Path("D:/OpenCode/RPA"),
                extra_excludes=_read_build_excludes(out_path()),
                gitignore=_read_build_gitignore(out_path()))
Path("graphify-out/.graphify_detect.json").write_text(
    json.dumps(result, ensure_ascii=False), encoding="utf-8")
print(f"Detected {result['total_files']} files")
print("keys:", list(result.keys()))
print("skipped_sensitive:", result.get("skipped_sensitive"))
print("total_words:", result.get("total_words"))
for k, v in (result.get("files") or {}).items():
    print(f"  {k}: {len(v) if isinstance(v, list) else v}")
