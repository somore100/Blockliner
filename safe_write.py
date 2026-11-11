"""Writing a file so a crash or a full disk can never leave half of it (pure, no Tk)."""
import os
import shutil
import tempfile


def write_text_atomic(path, text, keep_backup=False):
    """Write text (UTF-8) to path: first into a temporary file next to it, then swap it in
    in one step. The old file is untouched until the new one is complete. With keep_backup the
    previous version stays beside it as '<name>.bak' (one generation)."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if keep_backup and os.path.isfile(path):
            try:
                shutil.copy2(path, path + ".bak")
            except OSError:
                pass                        # a failed backup must not stop the save
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
