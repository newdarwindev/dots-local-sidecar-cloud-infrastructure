#!/usr/bin/env bash
set -euo pipefail
umask 077

source_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
sudo apt-get update -qq
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    dbus-x11 fonts-dejavu-mono freerdp2-x11 gnome-keyring libnotify-bin libsecret-tools \
    lightdm lightdm-gtk-greeter python3-gi tmux wmctrl x11-utils x11-xserver-utils \
    xdotool xfce4 xfce4-terminal xserver-xorg

install -d -m 700 "$HOME/.local/bin" "$HOME/.config/autostart" "$HOME/.config/lima-remote-desktop"
for file in "$source_dir"/{desktop-preferences,rdp-dashboard-tile,rdp-login-dashboard,remote-ssh-session,remote-workspace}.sh; do
    name="${file##*/}"
    install -m 700 "$file" "$HOME/.local/bin/${name%.sh}"
done
install -m 700 "$source_dir/secret-service.py" "$HOME/.local/bin/lima-rdp-secret-service"
python3 "$source_dir/dark-theme.py"

cat > "$HOME/.config/autostart/remote-workspace.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=SSH and Remote Desktops
Exec="$HOME/.local/bin/remote-workspace"
Icon=utilities-terminal
OnlyShowIn=XFCE;
Terminal=false
DESKTOP
sudo install -d -m 755 /etc/lightdm/lightdm.conf.d
printf '[Seat:*]\nautologin-user=%s\nautologin-user-timeout=0\nuser-session=xfce\n' "$(id -un)" |
    sudo tee /etc/lightdm/lightdm.conf.d/60-remote-desktop.conf >/dev/null
sudo systemctl set-default graphical.target
