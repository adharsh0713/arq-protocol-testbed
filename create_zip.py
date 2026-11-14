from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path.cwd()
output = root.parent / f"{root.name}.zip"

with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    for path in root.rglob("*"):
        relative_path = path.relative_to(root)

        # Exclude only the root-level venv directory
        if relative_path.parts[0] == "venv":
            continue

        if path.is_file():
            archive.write(path, relative_path)

print(f"ZIP created: {output}")