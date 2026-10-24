# Pread

Press a shortcut, drag a box around your code, and Claude's suggestions appear
in a box beside it. Works with Python and MySQL. macOS only.

How it works:
1. You press **Ctrl + Option + P**.
2. You drag a box around the code on your screen.
3. The text is read **on your Mac** with macOS's built-in text recognition (free, no tokens).
4. Only the text is sent to Claude.
5. Claude's insights appear in a box next to the code.

## Setup (once)

Open **Terminal** and run these one at a time, from inside this folder
(`cd` into it first, for example `cd ~/Desktop/pread`).

1. Check Python (needs 3.10 or newer):
   ```
   python3 --version
   ```
   If it's older, install the latest from python.org.

2. Create a private environment and install the pieces:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Add your API key:
   - Create a key at console.anthropic.com (this is separate from your Claude plan and charges per use).
   - Copy `.env.example` to `.env`:
     ```
     cp .env.example .env
     open -e .env
     ```
   - Replace `paste-your-key-here` with your key, save, and close.

4. Allow Terminal in **System Settings > Privacy & Security**. Turn Terminal **on** under:
   - **Screen & System Audio Recording** (so Pread can see your code)
   - **Input Monitoring** (so the shortcut works while other apps are in front)
   - **Accessibility** (also used by the shortcut)

   Then quit and reopen Terminal.

## Run

```
cd ~/Desktop/pread
source .venv/bin/activate
python3 main.py
```

A small dark bar appears at the top of the screen. Open your code, press
**Ctrl + Option + P**, then:

1. **Click once** on one corner of your code. That point is anchored.
2. **Move the mouse** to the opposite corner. The box follows (no need to hold the button).
3. **Click again** to finish.

Press-and-drag-and-release also still works. Press **Esc** to cancel.
Click **x** on the bar to quit.

Pread stays in front of every other app, including full-screen ones, and has no Dock icon.

## Reading the results

- Each suggestion has a **number and colour**. The same colour is painted over the lines
  on your real screen, so you can see exactly which code it is about.
- Each card shows the **ORIGINAL** code and the **FIX** side by side. You can select and copy the fix.
- **Hover** a card and its lines on screen light up brighter.
- **Drag the top strip** of the box to move it. Click **x** to close it (the marks disappear too).
- Click **Show what Pread read** at the bottom of the box to see the exact text Claude received.
  If a suggestion is about something that isn't in your code, check here first: the text
  recognition may have misread it.
- The marks stay where they were drawn. If you scroll your code, press the shortcut again.

## Tips

- Select just the code. Include the line numbers if you like; Pread uses them so
  Claude's "L12" matches your editor.
- Use a clear, monospaced font at a normal size for the best text recognition.
- If indentation looks wrong, set `PREAD_INDENT=2` in `.env` if your code uses 2 spaces.
- To make it cheaper, set `PREAD_MODEL=claude-haiku-5-5` in `.env`.
- `PREAD_UPSCALE=2` (default) enlarges the screenshot before reading it, which helps catch
  small punctuation. Try `3` if commas or brackets are still being missed, or `1` to switch it off.
- `PREAD_DEBUG=1` saves every capture and the text read into a `pread-debug` folder in your home folder.
- Change the shortcut with `PREAD_HOTKEY` (for example `<cmd>+<shift>+<space>`).

## If something doesn't work

| Problem | Likely cause |
|---|---|
| Shortcut does nothing | Input Monitoring / Accessibility not allowed for Terminal. Quit and reopen Terminal after allowing. |
| The capture shows only your wallpaper or empty windows | Screen Recording not allowed for Terminal. |
| "No text found" | Selected area too small, or text too small. Zoom in the editor. |
| "Your API key was rejected" | Check the key in `.env` has no extra spaces or quotes. |

## Files

- `main.py`: wires everything together
- `ui.py`: the bar, the drag-to-select overlay and the insights box
- `ocr.py`: text recognition and indentation rebuilding
- `review.py`: the request to Claude (edit `SYSTEM_PROMPT` to change what it looks for)
- `macos.py`: keeps Pread's windows in front of other apps
- `config.py`: settings
- `tests/test_logic.py`: checks for the parts that don't need a Mac

© 2026 Prdlime. Licensed under the MIT License. See the LICENSE file.
