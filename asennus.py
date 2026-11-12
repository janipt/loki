#!/usr/bin/env python3
"""Loki 0.3: install/uninstall KDE launcher for the current user only.

No root access, external Python modules, or network access are needed by
this installer. The Loki application itself requires PySide6 and journalctl.
"""

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

APP_ID = "loki-journal"
APP_FILES = ("loki.py", "loki-journal.svg", "asennus.py", "README.txt")
MARKER = "Loki 0.3 - oma käyttäjäasennus"


def paths():
    home = Path.home()
    xdg = os.environ.get("XDG_DATA_HOME", "")
    data_home = Path(xdg) if xdg and Path(xdg).is_absolute() else home / ".local/share"
    return {
        "application": data_home / APP_ID,
        "desktop": data_home / "applications" / f"{APP_ID}.desktop",
        "icon": data_home / "icons/hicolor/scalable/apps" / f"{APP_ID}.svg",
        "launcher": home / ".local/bin" / APP_ID,
    }


def desktop_exec_argument(path):
    # Desktop Entry Exec is not a shell command line. Quote/escape by its spec.
    result = str(path).replace("\\", "\\\\").replace('"', '\\"')
    result = result.replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    return f'"{result}"'


def refresh_kde():
    cache_tool = shutil.which("kbuildsycoca6")
    if cache_tool:
        try:
            subprocess.run([cache_tool, "--noincremental"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass  # Plasma normally detects menu changes automatically.


def install():
    source = Path(__file__).resolve().parent
    missing = [name for name in APP_FILES if not (source / name).is_file()]
    if missing:
        raise RuntimeError("Asennuspaketista puuttuu: " + ", ".join(missing))
    if importlib.util.find_spec("PySide6") is None:
        raise RuntimeError("PySide6 puuttuu. Asenna CachyOS:ssä ensin: sudo pacman -S --needed pyside6")
    if not shutil.which("journalctl"):
        raise RuntimeError("journalctl puuttuu. Loki edellyttää systemd-journalia.")

    p = paths()
    p["application"].mkdir(parents=True, exist_ok=True)
    p["desktop"].parent.mkdir(parents=True, exist_ok=True)
    p["icon"].parent.mkdir(parents=True, exist_ok=True)
    p["launcher"].parent.mkdir(parents=True, exist_ok=True)

    for name in APP_FILES:
        destination = p["application"] / name
        if (source / name) != destination:
            shutil.copy2(source / name, destination)
    shutil.copy2(source / "loki-journal.svg", p["icon"])

    # Shell and Desktop Entry use different quoting; use shlex for shell.
    import shlex
    launcher = (f"#!/bin/sh\n# {MARKER}\n"
                f"exec {shlex.quote(sys.executable)} "
                f"{shlex.quote(str(p['application'] / 'loki.py'))} \"$@\"\n")
    p["launcher"].write_text(launcher, encoding="utf-8")
    p["launcher"].chmod(0o755)

    desktop = (f"[Desktop Entry]\n"
               f"# {MARKER}\n"
               "Type=Application\n"
               "Name=Loki\n"
               "GenericName=Journalin lokiselain\n"
               "Comment=Selaa ja suodata systemd-journalin tapahtumia\n"
               f"Exec={desktop_exec_argument(p['launcher'])}\n"
               f"Icon={p['icon']}\n"
               "Terminal=false\n"
               "StartupNotify=true\n"
               "Categories=System;Utility;\n"
               "Keywords=lokit;virheet;systemd;journal;journalctl;kernel;logs;\n")
    p["desktop"].write_text(desktop, encoding="utf-8")
    refresh_kde()
    print("Loki 0.3 asennettu nykyiselle käyttäjälle. Root-oikeuksia ei käytetty.")
    print(f"Plasman sovellusvalikko: {p['desktop']}")
    print("Etsi sovellusvalikosta 'Loki' tai paina Meta ja kirjoita Loki.")
    print("Voit kiinnittää käynnissä olevan sovelluksen tehtäväpalkkiin.")
    print(f"Poisto: python3 {p['application'] / 'asennus.py'} --poista")


def uninstall():
    p = paths()
    targets = (p["desktop"], p["launcher"], p["icon"])
    for target in targets:
        if target.exists():
            if target in (p["desktop"], p["launcher"]) and MARKER not in target.read_text(encoding="utf-8"):
                raise RuntimeError(f"Ei poisteta tuntematonta tiedostoa: {target}")
            target.unlink()
    for name in APP_FILES:
        (p["application"] / name).unlink(missing_ok=True)
    try:
        p["application"].rmdir()  # Keep unrecognized/user files, if any.
    except (FileNotFoundError, OSError):
        pass
    refresh_kde()
    print("Lokin sovellusvalikon käynnistin ja ohjelmatiedostot poistettu.")
    print("Mahdollisia omia TXT-vientejä ei poistettu.")


def main():
    parser = argparse.ArgumentParser(description="Loki: asenna KDE Plasman sovellusvalikkoon")
    parser.add_argument("--poista", action="store_true", help="Poista nykyisen käyttäjän Loki-asennus")
    args = parser.parse_args()
    try:
        if args.poista:
            uninstall()
        else:
            install()
    except (OSError, RuntimeError) as exc:
        print(f"Virhe: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
