#!/usr/bin/env python3
"""Generate the border-only Xfwm theme for the dashboard."""
from pathlib import Path

theme = Path.home() / ".themes/Lima Dark/xfwm4"
theme.mkdir(parents=True, exist_ok=True)
(theme / "themerc").write_text(
    """button_layout=|
button_offset=0
button_spacing=0
frame_border_top=0
full_width_title=false
show_app_icon=false
active_text_color=#53c6ff
inactive_text_color=#20242b
title_vertical_offset_active=-8
title_vertical_offset_inactive=-8
title_shadow_active=false
title_shadow_inactive=false
"""
)
pieces = {
    "left": (2, 1), "right": (2, 1), "bottom": (1, 2),
    "top-left": (2, 2), "top-right": (2, 2),
    "bottom-left": (2, 2), "bottom-right": (2, 2),
    **{f"title-{number}": (1, 2) for number in range(1, 6)},
}
for state, color in (("active", "#53c6ff"), ("inactive", "#20242b")):
    for name, (width, height) in pieces.items():
        pixels = ",\n".join(f'"{"." * width}"' for _ in range(height))
        (theme / f"{name}-{state}.xpm").write_text(
            f'/* XPM */\nstatic const char *frame[] = {{\n"{width} {height} 1 1",\n'
            f'". c {color}",\n{pixels}\n}};\n'
        )
