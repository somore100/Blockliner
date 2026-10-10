"""Single source of truth for the version and the About window text.

Pure module (no Tk). To release: change APP_VERSION here to match the git
tag (without the leading "v"), then commit.
"""
import os

APP_VERSION = "2.3.0"
BUILD_NUMBER = 1  # bump by hand for a meaningfully new build (shown in About)

APP_NAME = "Blockliner"
TAGLINE = "Visual Code Builder"
AUTHOR = "somore100 (domore100)"
REPO_URL = "https://github.com/somore100/Blockliner"

DESCRIPTION = (
    "Blockliner is a visual, block-first code editor. Build programs by "
    "connecting blocks and nodes, and get real, readable source code out - "
    "Python, C, C++, C#, Java, JavaScript, Rust, Go and HTML."
)

CREDITS = (
    "Created by " + AUTHOR + "\n\n"
    "Built with\n"
    "  - Python and Tkinter\n"
    "  - Pillow (images)\n"
    "  - tree-sitter (code parsing)\n\n"
    "Made with love for people who think in blocks."
)


def version_text():
    return f"Version {APP_VERSION}  ·  build {BUILD_NUMBER}"


def read_license(base_dir):
    """Text of LICENSE.md next to the program, or a short fallback."""
    try:
        with open(os.path.join(base_dir, "LICENSE.md"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "LICENSE.md was not found next to the program.\n\nSee " + REPO_URL
