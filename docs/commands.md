# ARIA commands

- `open <dynamically discovered application>`
- `make it one-fifth of the screen`
- `make it smaller` / `make it bigger` (10% relative change)
- `resize <window title> 20%`
- `move it top right|top left|bottom right|bottom left|center`
- `move it right|left|up|down` (50 pixels)
- `minimize|maximize|restore [window]`
- `create folder called <name> on desktop|documents|downloads|videos|pictures`
- `open desktop|documents|downloads|videos|pictures`
- `take screenshot`
- `set volume 50%`, `increase volume by 10%`, `mute`, `unmute`

Start Enter-to-speak mode with `aria --voice`, or global Ctrl+Space activation
with `aria --desktop`. The cached multilingual `base` model stays loaded.

Sprint 3 file and system commands:

- `delete "C:\\path\\test_file.txt"` — confirmation; Recycle Bin.
- `move file "C:\\source.txt" to "C:\\destination.txt"` — confirmation.
- `rename file "C:\\source.txt" to "new-name.txt"` — confirmation.
- `copy file "C:\\source.txt" to "C:\\destination.txt"` — low risk; no overwrite.
- `shutdown` / `shut down computer` — confirmation.

Relative paths resolve against ARIA's launch directory; the dialog shows absolute paths.
Configure `--confirmation-timeout 45` or `--confirm-low` as needed.
Confirmation dialogs are available in desktop mode; legacy CLI modes reject risky
actions without executing them. Spoken filenames remain subject to ASR accuracy.
