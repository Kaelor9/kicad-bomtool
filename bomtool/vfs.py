"""In-memory view of an uploaded project (zip file or loose files).

Nothing is extracted to disk: members are read into a dict, which also avoids
path-traversal problems with hostile archives.
"""
import io
import posixpath
import zipfile

KEEP_EXT = (".kicad_sch", ".kicad_pcb", ".kicad_pro", ".kicad_mod", ".kicad_sym",
            ".sch", ".pro")
KEEP_NAMES = ("fp-lib-table", "sym-lib-table")
MAX_MEMBER = 200 * 1024 * 1024


def _wanted(path):
    low = path.lower()
    parts = low.split("/")
    if any(p.endswith("-backups") or p.startswith("_autosave") or p == "__macosx" for p in parts):
        return False
    name = parts[-1]
    if name.startswith("_autosave") or name.startswith("~") or name.endswith(".lck"):
        return False
    return name.endswith(KEEP_EXT) or name in KEEP_NAMES


def _norm(path):
    path = path.replace("\\", "/").lstrip("/")
    path = posixpath.normpath(path)
    return "" if path.startswith("..") else path


class ProjectFiles:
    def __init__(self, files):
        # files: {posix relative path: bytes}
        self.files = files

    @classmethod
    def from_upload(cls, name, data):
        """Accept a zip archive or a single KiCad file."""
        if data[:4] == b"PK\x03\x04" or name.lower().endswith(".zip"):
            return cls.from_zip(data)
        return cls({_norm(name): data})

    @classmethod
    def from_zip(cls, data, prefix=""):
        files = {}
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir() or info.file_size > MAX_MEMBER:
                    continue
                path = _norm(info.filename)
                if not path:
                    continue
                if path.lower().endswith(".zip") and "-backups/" not in path.lower():
                    # A zip inside the zip (e.g. a project packed twice).
                    try:
                        inner = cls.from_zip(zf.read(info), prefix=posixpath.dirname(path))
                        files.update(inner.files)
                    except zipfile.BadZipFile:
                        pass
                    continue
                if _wanted(path):
                    files[posixpath.join(prefix, path) if prefix else path] = zf.read(info)
        return cls(files)

    def merge(self, other):
        self.files.update(other.files)

    def text(self, path):
        data = self.files.get(path)
        if data is None:
            return None
        if data[:3] == b"\xef\xbb\xbf":
            data = data[3:]
        return data.decode("utf-8", errors="replace")

    def find(self, ext):
        return sorted(p for p in self.files if p.lower().endswith(ext))

    def resolve(self, base_dir, rel):
        """Resolve a path referenced from a file in base_dir (case-insensitive fallback)."""
        cand = _norm(posixpath.join(base_dir, rel.replace("\\", "/")))
        if cand in self.files:
            return cand
        low = cand.lower()
        for p in self.files:
            if p.lower() == low:
                return p
        name = posixpath.basename(low)
        for p in self.files:
            if posixpath.basename(p.lower()) == name:
                return p
        return None
