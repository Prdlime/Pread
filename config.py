"""Settings for Pread. Change them in the .env file, not here."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Global keyboard shortcut. Format used by the pynput library.
HOTKEY = os.getenv("PREAD_HOTKEY", "<ctrl>+<alt>+p")

# Which Claude model reviews the code. "claude-haiku-5-5" is cheaper.
MODEL = os.getenv("PREAD_MODEL", "claude-sonnet-5-5")

# Upper limit on the length of Claude's answer (controls cost).
MAX_OUTPUT_TOKENS = int(os.getenv("PREAD_MAX_TOKENS", "1200"))

# Spaces per indent level in your code (Python is usually 4).
INDENT_UNIT = int(os.getenv("PREAD_INDENT", "4"))

# Safety limit on how much code is sent in one go.
MAX_LINES = 300

# Enlarge the screenshot before reading it. Helps the reader catch small
# punctuation such as commas. 1 = off.
OCR_UPSCALE = float(os.getenv("PREAD_UPSCALE", "2"))

# Set PREAD_DEBUG=1 to save each capture and the text read to ~/pread-debug/
DEBUG = os.getenv("PREAD_DEBUG", "") == "1"
