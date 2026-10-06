import difflib
import hashlib
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from file_policy import FileAccessPolicy

if os.name == "nt":
    import msvcrt
else:
    import fcntl

FILE_ICONS = {".py": "🐍", ".md": "📝", ".txt": "📝", ".sql": "🗄️", ".yml": "⚙️", ".yaml": "⚙️", ".toml": "⚙️", ".ini": "⚙️", ".json": "⚙️", ".sh": "📜", ".lock": "🔒", ".png": "🖼️", ".jpg": "🖼️", ".jpeg": "🖼️", ".svg": "🖼️", ".pdf": "📕", ".zip": "📦", ".gz": "📦"}


def file_icon(name, is_directory):
    if is_directory:
        return "📁"
    lowered = name.lower()
    if lowered == ".dockerignore" or lowered.startswith(("dockerfile", "docker-compose", "compose.")):
        return "🐳"
    return FILE_ICONS.get(Path(name).suffix.lower(), "📄")


class FileSystemTools:
    """Operaciones restringidas a un espacio de trabajo, con revisión optimista."""
    protected = {".git", ".aws", ".ssh", ".codex", ".agents", ".venv", ".idea", ".history", ".workspace.lock"}

    def __init__(self, root=None, max_bytes=100_000, policy=None, rules_file=None):
        root = Path(root if root is not None else Path.home()).expanduser()
        if self._link(root):
            raise ValueError("El espacio de trabajo no puede ser un enlace simbólico")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root.resolve()
        self.max_bytes = max_bytes
        self.policy = policy if policy is not None else FileAccessPolicy()
        self.rules_file = Path(rules_file).resolve() if rules_file is not None else None

    @staticmethod
    def _link(path):
        return path.is_symlink() or path.is_junction()

    def _check(self, path, operation):
        if path == self.rules_file or not self.policy.allows(path.relative_to(self.root).as_posix(), operation):
            raise ValueError(f"Las reglas no permiten la acción '{operation}' sobre esta ruta")

    @classmethod
    def _protected(cls, part):
        lowered = part.lower().rstrip(" .")
        return lowered in cls.protected or lowered.startswith((".env", "credentials")) or lowered.endswith((".key", ".pem", ".p12"))

    def _path(self, value, allow_root=False):
        if not isinstance(value, str) or not value or "\x00" in value:
            raise ValueError("Indica una ruta válida")
        path = Path(value)
        path = path if path.is_absolute() else self.root / path
        if os.name == "nt" and any(":" in part for part in path.parts[1:]):
            raise ValueError("No se permiten flujos alternativos de archivos de Windows")
        # Rechaza enlaces, incluso si su destino actual está dentro del espacio.
        probe = path
        while probe != self.root and probe != probe.parent:
            if self._link(probe):
                raise ValueError("No se permiten enlaces simbólicos")
            probe = probe.parent
        path = path.resolve()
        if not path.is_relative_to(self.root) or (path == self.root and not allow_root):
            raise ValueError("La ruta debe estar dentro de tu espacio de trabajo")
        if any(self._protected(part) for part in path.relative_to(self.root).parts):
            raise ValueError("El archivo está protegido")
        if path == self.rules_file:
            raise ValueError("El archivo de reglas está protegido")
        return path

    @contextmanager
    def _lock(self):
        lock_path = self.root / ".workspace.lock"
        if self._link(lock_path):
            raise ValueError("El archivo de bloqueo no es válido")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "r+b") as lock:
            if os.name == "nt":
                if os.fstat(lock.fileno()).st_size == 0:
                    lock.write(b"\0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_EX)
                yield

    def _read(self, path):
        if self._link(path):
            raise ValueError("No se permiten enlaces simbólicos ni junctions")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(descriptor, "rb") as file:
            data = file.read(self.max_bytes + 1)
        if len(data) > self.max_bytes:
            raise ValueError(f"El archivo supera el límite de {self.max_bytes} bytes")
        return data.decode("utf-8")

    @staticmethod
    def _hash(content):
        return hashlib.sha256(content.encode()).hexdigest()

    def list_files(self, directory="."):
        try:
            path = self._path(directory, allow_root=True)
            self._check(path, "list")
            entries = []
            with os.scandir(path) as items:
                for item in items:
                    if item.name.startswith("."):
                        continue
                    item_path = Path(item.path)
                    if self._protected(item.name) or self._link(item_path) or item_path == self.rules_file or not self.policy.allows(item_path.relative_to(self.root).as_posix(), "list"):
                        continue
                    if len(entries) == 1000:
                        return {"error": "El directorio supera el límite de 1000 elementos. Lista un subdirectorio."}
                    directory = item.is_dir(follow_symlinks=False)
                    entries.append({"name": item.name, "type": "directory" if directory else "file", "icon": file_icon(item.name, directory)})
            entries.sort(key=lambda entry: (entry["type"] != "directory", entry["name"].casefold()))
            return {"files": [entry["name"] for entry in entries], "entries": entries}
        except (OSError, ValueError) as error:
            return {"error": str(error)}

    def read_file(self, file_path):
        try:
            path = self._path(file_path)
            self._check(path, "read")
            content = self._read(path)
            return {"content": content, "revision": self._hash(content)}
        except (OSError, ValueError) as error:
            return {"error": str(error)}

    def _edit_plan(self, file_path, prev_text=None, new_text=""):
        path = self._path(file_path)
        existed = path.exists()
        self._check(path, "edit" if existed else "create")
        if existed:
            self._check(path, "read")
        original = self._read(path) if existed else ""
        if existed:
            if prev_text is None or (not prev_text and original):
                raise ValueError("Indica el texto exacto que quieres reemplazar")
            if prev_text not in original:
                raise ValueError("El texto indicado no coincide con el archivo actual")
            updated = original.replace(prev_text, new_text, 1) if original else new_text
        else:
            updated = new_text
        if len(updated.encode()) > self.max_bytes:
            raise ValueError("El archivo resultante supera el límite de tamaño")
        revision = self._hash(original) if existed else "missing"
        return path, original, updated, revision

    def preview_edit(self, **arguments):
        try:
            path, original, updated, revision = self._edit_plan(**arguments)
            relative = str(path.relative_to(self.root))
            diff = "".join(difflib.unified_diff(original.splitlines(keepends=True), updated.splitlines(keepends=True), fromfile=relative, tofile=relative))
            return {"path": relative, "revision": revision, "diff": diff, "operation": "editar" if revision != "missing" else "crear"}
        except (OSError, ValueError) as error:
            return {"error": str(error)}

    def _backup(self, path):
        history = self.root / ".history"
        if self._link(history):
            raise ValueError("El directorio de respaldo no es válido")
        history.mkdir(mode=0o700, exist_ok=True)
        target = history / str(uuid4())
        shutil.copy2(path, target)
        return target.name

    def edit_file(self, file_path, prev_text=None, new_text="", expected_revision=None):
        try:
            with self._lock():
                path, original, updated, revision = self._edit_plan(file_path, prev_text, new_text)
                if expected_revision is not None and revision != expected_revision:
                    raise ValueError("El archivo cambió desde la revisión. Solicita una nueva vista previa.")
                backup = self._backup(path) if path.exists() else None
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False) as file:
                        temp_path = Path(file.name)
                        file.write(updated)
                        file.flush()
                        os.fsync(file.fileno())
                    # Vuelve a validar justo antes de reemplazar; conserva el modo previo.
                    self._path(file_path)
                    current = self._hash(self._read(path)) if path.exists() else "missing"
                    if current != revision:
                        raise ValueError("El archivo cambió durante la edición")
                    if path.exists():
                        os.chmod(temp_path, path.stat().st_mode & 0o777)
                    os.replace(temp_path, path)
                finally:
                    if temp_path is not None:
                        temp_path.unlink(missing_ok=True)
                return {"success": True, "message": "Archivo guardado", "backup": backup}
        except (OSError, ValueError) as error:
            return {"error": str(error)}

    def _delete_plan(self, file_path, recursive=False):
        path = self._path(file_path)
        self._check(path, "delete")
        if not path.exists():
            raise ValueError("El archivo no existe")
        paths = [path]
        if path.is_dir():
            paths = sorted(path.rglob("*"))
            if paths and not recursive:
                raise ValueError("El directorio no está vacío; requiere recursive=true")
            if len(paths) > 1000:
                raise ValueError("La operación supera el límite de 1000 archivos")
        digest = hashlib.sha256()
        for item in paths:
            self._path(str(item))
            self._check(item, "delete")
            digest.update(str(item.relative_to(self.root)).encode())
            if item.is_file():
                digest.update(self._read(item).encode())
        return path, digest.hexdigest(), [str(item.relative_to(self.root)) for item in paths]

    def preview_delete(self, file_path, recursive=False):
        try:
            path, revision, files = self._delete_plan(file_path, recursive)
            return {"path": str(path.relative_to(self.root)), "revision": revision, "files": files, "operation": "eliminar"}
        except (OSError, ValueError) as error:
            return {"error": str(error)}

    def delete_file(self, file_path, recursive=False, expected_revision=None):
        try:
            with self._lock():
                path, revision, _ = self._delete_plan(file_path, recursive)
                if expected_revision is not None and revision != expected_revision:
                    raise ValueError("El archivo o directorio cambió desde la revisión")
                history = self.root / ".history"
                if self._link(history):
                    raise ValueError("El directorio de respaldo no es válido")
                history.mkdir(exist_ok=True, mode=0o700)
                backup = str(uuid4())
                os.replace(path, history / backup)
                return {"success": True, "message": "Archivo eliminado del espacio de trabajo", "backup": backup}
        except (OSError, ValueError) as error:
            return {"error": str(error)}
