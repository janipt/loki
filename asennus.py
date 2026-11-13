#!/usr/bin/env python3
"""Install or remove Loki's KDE launcher for the current user."""

import importlib.util
import locale
import os
from pathlib import Path
import shutil
import subprocess
import sys

try:
    from version import VERSION
except ModuleNotFoundError:
    VERSION = None

APP_ID = "loki-journal"
APP_FILES = ("loki.py", "loki-journal.svg", "asennus.py", "README.md", "version.py")
LEGACY_APP_FILES = ("README.txt",)
MARKER = "Loki user installation"
LEGACY_MARKERS = (
    "Loki 0.4 - oma käyttäjäasennus",
    "Loki 0.3 - oma käyttäjäasennus",
)

MESSAGES = {
    "fi": {
        "help": (
            "Loki {version} – asennus ja poisto nykyiselle käyttäjälle\n\n"
            "Käyttö: python3 {script} [--poista | --uninstall | --help]\n\n"
            "Ilman valitsimia asenna tai päivitä Loki.\n"
            "  --poista       Poista käyttäjäkohtainen Loki-asennus.\n"
            "  --uninstall    Englanninkielinen alias valitsimelle --poista.\n"
            "  -h, --help     Näytä tämä ohje.\n\n"
            "Asennus ei käytä root-oikeuksia. Loki tarvitsee PySide6:n ja journalctl:n."
        ),
        "usage": "Käyttö: python3 {script} [--poista | --uninstall | --help]",
        "invalid_arguments": "Virheelliset argumentit: {arguments}",
        "missing_files": "Asennuspaketista puuttuu: {files}",
        "missing_pyside": "PySide6 puuttuu. Asenna CachyOS:ssä ensin: sudo pacman -S --needed pyside6",
        "missing_journalctl": "journalctl puuttuu. Loki edellyttää systemd-journalia.",
        "installed": "Loki {version} asennettu nykyiselle käyttäjälle. Root-oikeuksia ei käytetty.",
        "updated": "Loki {version} päivitetty nykyiselle käyttäjälle. Root-oikeuksia ei käytetty.",
        "menu_path": "Plasman sovellusvalikko: {path}",
        "menu_hint": "Etsi sovellusvalikosta 'Loki' tai paina Meta ja kirjoita Loki.",
        "pin_hint": "Voit kiinnittää käynnissä olevan sovelluksen tehtäväpalkkiin.",
        "uninstall_command": "Poisto: python3 {path} --poista",
        "unknown_file": "Ei poisteta tuntematonta tiedostoa: {path}",
        "removed": "Lokin sovellusvalikon käynnistin ja ohjelmatiedostot poistettu.",
        "kept_exports": "Mahdollisia omia TXT-vientejä ei poistettu.",
        "error": "Virhe: {message}",
    },
    "en": {
        "help": (
            "Loki {version} – install and remove for the current user\n\n"
            "Usage: python3 {script} [--uninstall | --poista | --help]\n\n"
            "With no options, install or update Loki.\n"
            "  --uninstall    Remove the user-level Loki installation.\n"
            "  --poista       Finnish alias for --uninstall.\n"
            "  -h, --help     Show this help.\n\n"
            "Installation does not use root privileges. Loki requires PySide6 and journalctl."
        ),
        "usage": "Usage: python3 {script} [--uninstall | --poista | --help]",
        "invalid_arguments": "Invalid arguments: {arguments}",
        "missing_files": "The installation package is missing: {files}",
        "missing_pyside": "PySide6 is missing. On CachyOS, install it first: sudo pacman -S --needed pyside6",
        "missing_journalctl": "journalctl is missing. Loki requires the systemd journal.",
        "installed": "Loki {version} installed for the current user. No root privileges were used.",
        "updated": "Loki {version} updated for the current user. No root privileges were used.",
        "menu_path": "Plasma application menu entry: {path}",
        "menu_hint": "Find 'Loki' in the application menu or press Meta and type Loki.",
        "pin_hint": "You can pin the running application to the taskbar.",
        "uninstall_command": "Uninstall: python3 {path} --uninstall",
        "unknown_file": "Refusing to remove an unrecognized file: {path}",
        "removed": "Loki's application menu entry and program files were removed.",
        "kept_exports": "Any personal TXT exports were kept.",
        "error": "Error: {message}",
    },
}


def get_language():
    """Return Finnish only for Finnish system locales; use English otherwise."""
    locale_name = next((os.environ.get(key) for key in
                        ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG") if os.environ.get(key)), "")
    if not locale_name:
        try:
            locale_name = locale.getlocale(locale.LC_MESSAGES)[0] or ""
        except (AttributeError, ValueError):
            locale_name = ""
    locale_name = locale_name.split(":", 1)[0].split(".", 1)[0].split("@", 1)[0].lower()
    return "fi" if locale_name == "fi" or locale_name.startswith("fi_") or locale_name.startswith("fi-") else "en"


def msg(key, **values):
    return MESSAGES[get_language()][key].format(**values)


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
        raise RuntimeError(msg("missing_files", files=", ".join(missing)))
    if importlib.util.find_spec("PySide6") is None:
        raise RuntimeError(msg("missing_pyside"))
    if not shutil.which("journalctl"):
        raise RuntimeError(msg("missing_journalctl"))

    p = paths()
    upgrading = any(path.exists() for path in (p["application"], p["desktop"], p["launcher"]))
    p["application"].mkdir(parents=True, exist_ok=True)
    p["desktop"].parent.mkdir(parents=True, exist_ok=True)
    p["icon"].parent.mkdir(parents=True, exist_ok=True)
    p["launcher"].parent.mkdir(parents=True, exist_ok=True)

    for name in APP_FILES:
        destination = p["application"] / name
        if (source / name) != destination:
            shutil.copy2(source / name, destination)
    # Remove the documentation filename managed by older Loki installers.
    (p["application"] / "README.txt").unlink(missing_ok=True)
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
               "Name[fi]=Loki\n"
               "Name[en]=Loki\n"
               "GenericName=Journal browser\n"
               "GenericName[fi]=Journalin lokiselain\n"
               "GenericName[en]=Journal browser\n"
               "Comment=Browse and filter systemd journal events\n"
               "Comment[fi]=Selaa ja suodata systemd-journalin tapahtumia\n"
               "Comment[en]=Browse and filter systemd journal events\n"
               f"Exec={desktop_exec_argument(p['launcher'])}\n"
               f"Icon={p['icon']}\n"
               "Terminal=false\n"
               "StartupNotify=true\n"
               "Categories=System;Utility;\n"
               "Keywords=logs;errors;systemd;journal;journalctl;kernel;\n"
               "Keywords[fi]=lokit;virheet;systemd;journal;journalctl;kernel;\n"
               "Keywords[en]=logs;errors;systemd;journal;journalctl;kernel;\n")
    p["desktop"].write_text(desktop, encoding="utf-8")
    refresh_kde()
    print(msg("updated" if upgrading else "installed", version=VERSION))
    print(msg("menu_path", path=p["desktop"]))
    print(msg("menu_hint"))
    print(msg("pin_hint"))
    print(msg("uninstall_command", path=p["application"] / "asennus.py"))


def _has_loki_marker(path):
    contents = path.read_text(encoding="utf-8")
    return any(marker in contents for marker in (MARKER, *LEGACY_MARKERS))


def uninstall():
    p = paths()
    targets = (p["desktop"], p["launcher"], p["icon"])
    for target in targets:
        if target.exists():
            if target in (p["desktop"], p["launcher"]) and not _has_loki_marker(target):
                raise RuntimeError(msg("unknown_file", path=target))
            target.unlink()
    for name in (*APP_FILES, *LEGACY_APP_FILES):
        (p["application"] / name).unlink(missing_ok=True)
    try:
        p["application"].rmdir()  # Keep unrecognized/user files, if any.
    except (FileNotFoundError, OSError):
        pass
    refresh_kde()
    print(msg("removed"))
    print(msg("kept_exports"))


def print_help():
    version = VERSION or ("tuntematon" if get_language() == "fi" else "unknown")
    print(msg("help", version=version, script=Path(sys.argv[0]).name))


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["-h"], ["--help"]):
        print_help()
        return 0
    if arguments not in ([], ["--poista"], ["--uninstall"]):
        print(msg("invalid_arguments", arguments=" ".join(arguments)), file=sys.stderr)
        print(msg("usage", script=Path(sys.argv[0]).name), file=sys.stderr)
        return 2
    try:
        uninstall() if arguments else install()
    except (OSError, RuntimeError) as exc:
        print(msg("error", message=exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
