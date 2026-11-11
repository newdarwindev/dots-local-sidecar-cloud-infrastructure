#!/usr/bin/env python3
"""Install shortcuts for the configured local views, reusing supervised panes."""
import json
from pathlib import Path
import subprocess

from dashboard import validate_config


def main():
    home = Path.home()
    config = validate_config(json.loads((home / '.config/desktop-dashboard/config.json').read_text()))
    launcher = str(home / '.local/bin/desktop-dashboard').replace('%', '%%').replace('"', '\\"')
    result = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True, check=True)
    desktop = Path(result.stdout.strip())
    if not desktop.is_absolute() or desktop == home:
        raise ValueError('A separate desktop directory must be configured')
    applications = home / '.local/share/applications'
    entries = [('hub', 'Dashboard hub', '--home', 'view-grid'),
               ('restore', 'Restore dashboard layout', '--restore', 'view-restore')]
    entries += [(item['id'], item['name'], '--open ' + item['id'], 'utilities-system-monitor')
                for item in config.get('links', []) if item.get('forward')]
    if config.get('overview'):
        entries.append(('overview', 'Workloads and OpenTelemetry', '--open overview', 'utilities-system-monitor'))
    for identifier, name, argument, icon in entries:
        text = ('[Desktop Entry]\nType=Application\nName=' + name.replace('\n', ' ') +
                '\nComment=Show this view in the existing desktop dashboard panes\nExec="' + launcher +
                '" ' + argument + '\nIcon=' + icon +
                '\nTerminal=false\nStartupNotify=false\nCategories=System;Monitor;\n')
        for directory in (desktop, applications):
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / ('desktop-dashboard-' + identifier + '.desktop')
            path.write_text(text)
            path.chmod(0o755)
    print('Installed', len(entries), 'desktop and application shortcuts.')


if __name__ == '__main__':
    main()
