#!/usr/bin/env bash
set -euo pipefail

# Wait for Xfwm before requesting window placement.
for _ in {1..30}; do
    wmctrl -m >/dev/null 2>&1 && break
    sleep 0.25
done

"$HOME/.local/bin/desktop-preferences"

if ! tmux has-session -t '=remote-ssh' 2>/dev/null; then
    tmux new-session -d -s remote-ssh -n Hosts -x 120 -y 35
    tmux set-window-option -t remote-ssh:Hosts remain-on-exit on
    tmux set-option -t remote-ssh status off
    tmux set-window-option -t remote-ssh:Hosts pane-border-style "fg=colour238,bg=default"
    tmux set-window-option -t remote-ssh:Hosts pane-active-border-style "fg=#53c6ff,bg=default"
    tmux set-window-option -t remote-ssh:Hosts pane-border-status top
    tmux set-window-option -t remote-ssh:Hosts pane-border-format ' #{pane_title} '
    tmux select-pane -t remote-ssh:Hosts.0 -T rdp-left
    tmux respawn-pane -k -t remote-ssh:Hosts.0 "$HOME/.local/bin/remote-ssh-session rdp-left"
    tmux split-window -h -t remote-ssh:Hosts "$HOME/.local/bin/remote-ssh-session rdp-right"
    tmux select-pane -t remote-ssh:Hosts.1 -T rdp-right
    tmux select-pane -t remote-ssh:Hosts.0
    tmux bind-key R respawn-pane -k
fi

if ! wmctrl -a 'SSH Workbench'; then
    xfce4-terminal --disable-server --title='SSH Workbench' --hide-menubar \
        --hide-toolbar --hide-scrollbar --command='tmux attach-session -t =remote-ssh' &
fi
exec "$HOME/.local/bin/rdp-login-dashboard"
