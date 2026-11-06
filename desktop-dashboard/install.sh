#!/bin/sh
# Install only the authorized desktop launcher, not application services/accounts.
set -eu
source_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
command -v surf >/dev/null
command -v xrandr >/dev/null
python3 -c 'import Xlib' >/dev/null
app_dir="$HOME/.local/lib/desktop-dashboard"
mkdir -p "$app_dir" "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.config/desktop-dashboard" "$HOME/.config/autostart"
install -m 755 "$source_dir/dashboard.py" "$app_dir/dashboard.py"
if [ ! -f "$HOME/.config/desktop-dashboard/config.json" ]; then
    install -m 600 "$source_dir/config.example.json" "$HOME/.config/desktop-dashboard/config.json"
fi
cat > "$HOME/.local/bin/desktop-dashboard" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 "$HOME/.local/lib/desktop-dashboard/dashboard.py" "$@"
LAUNCHER
chmod 755 "$HOME/.local/bin/desktop-dashboard"
cat > "$HOME/.config/autostart/desktop-dashboard.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Desktop dashboards
Comment=Borderless dashboard beside Conky
Exec="$HOME/.local/bin/desktop-dashboard" --autostart
TryExec=surf
Terminal=false
StartupNotify=false
OnlyShowIn=XFCE;
X-GNOME-Autostart-enabled=true
EOF
cat > "$HOME/.local/share/applications/desktop-dashboard.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Desktop dashboards
Comment=Open dashboard shortcuts and local connection status
Exec="$HOME/.local/bin/desktop-dashboard" --home
TryExec=surf
Icon=view-grid
Terminal=false
StartupNotify=false
Categories=System;Monitor;
EOF
printf '%s\n' 'Desktop launcher installed. Review private configuration before starting.'
