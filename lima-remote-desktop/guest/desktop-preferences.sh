#!/usr/bin/env bash
set -euo pipefail

set_pref() {
    local channel=$1 property=$2 type=$3 value=$4
    if xfconf-query -c "$channel" -p "$property" >/dev/null 2>&1; then
        xfconf-query -c "$channel" -p "$property" -s "$value"
    else
        xfconf-query -c "$channel" -p "$property" -n -t "$type" -s "$value"
    fi
}

dark_rgba() {
    xfconf-query -c "$1" -p "$2" -n -a \
        -t double -s 0.062745098 -t double -s 0.066666667 \
        -t double -s 0.078431373 -t double -s 1
}

set_pref xsettings /Net/ThemeName string Adwaita-dark
set_pref xsettings /Gtk/DecorationLayout string ':'
set_pref xfwm4 /general/title_font string 'Sans 1'
set_pref xfwm4 /general/button_layout string '|'
set_pref xfwm4 /general/show_app_icon bool false
set_pref xfwm4 /general/show_frame_shadow bool false
set_pref xfwm4 /general/show_dock_shadow bool false
set_pref xfwm4 /general/show_popup_shadow bool false
set_pref xfwm4 /general/click_to_focus bool true
set_pref xfwm4 /general/raise_on_click bool true
set_pref xfwm4 /general/raise_on_focus bool false
set_pref xfwm4 /general/theme string 'Lima Dark'

for panel_id in $(xfconf-query -c xfce4-panel -p /panels | awk '/^[[:digit:]]+$/'); do
    panel="/panels/panel-$panel_id"
    set_pref xfce4-panel "$panel/autohide-behavior" uint 2
    set_pref xfce4-panel "$panel/disable-struts" bool true
    set_pref xfce4-panel "$panel/background-style" uint 1
    dark_rgba xfce4-panel "$panel/background-rgba"
done

for monitor in $(xrandr --query | awk '$2 == "connected" {print $1}'); do
    for workspace in $(wmctrl -d | awk '{print $1}'); do
        target="/backdrop/screen0/monitor$monitor/workspace$workspace"
        set_pref xfce4-desktop "$target/color-style" int 0
        set_pref xfce4-desktop "$target/image-style" int 0
        dark_rgba xfce4-desktop "$target/rgba1"
    done
done
set_pref xfce4-desktop /desktop-icons/style int 0
xfdesktop --reload
