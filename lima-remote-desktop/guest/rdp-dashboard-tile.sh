#!/usr/bin/env bash
set -euo pipefail

if ! read -r left top width height < <(wmctrl -d | awk '$2 == "*" {
    split($8, position, ","); split($9, size, "x");
    print position[1], position[2], size[1], size[2]
}'); then
    exit 0
fi

split_x=$((width / 2))
split_y=$((height * 72 / 100))

fit_frame() {
    local id=$1 x=$2 y=$3 outer_width=$4 outer_height=$5
    local border_left=0 border_right=0 border_top=0 border_bottom=0 extents

    extents=$(xprop -id "$id" _NET_FRAME_EXTENTS 2>/dev/null) || return 0
    if [[ "$extents" =~ =[[:space:]]([0-9]+),[[:space:]]([0-9]+),[[:space:]]([0-9]+),[[:space:]]([0-9]+) ]]; then
        border_left=${BASH_REMATCH[1]}
        border_right=${BASH_REMATCH[2]}
        border_top=${BASH_REMATCH[3]}
        border_bottom=${BASH_REMATCH[4]}
    fi
    wmctrl -ir "$id" -e "0,$x,$y,$((outer_width - border_left - border_right)),$((outer_height - border_top - border_bottom))"
}

while read -r id _desktop class _machine title; do
    case "${class,,} $title" in
        *dashboard-rdp-left*)
            fit_frame "$id" "$left" "$top" "$split_x" "$split_y"
            ;;
        *dashboard-rdp-right*)
            fit_frame "$id" "$((left + split_x))" "$top" "$((width - split_x))" "$split_y"
            ;;
        *' SSH Workbench')
            # VTE otherwise rounds the window dimensions down to whole cells.
            if xprop -id "$id" WM_NORMAL_HINTS | awk '/resize increment/ {found=1} END {exit !found}'; then
                xprop -id "$id" -remove WM_NORMAL_HINTS
                sleep 0.1
            fi
            fit_frame "$id" "$left" "$((top + split_y))" "$width" "$((height - split_y))"
            ;;
    esac
done < <(wmctrl -lx)
