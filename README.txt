LOKI 0.4 – KDE Plasma integration (CachyOS / Arch Linux)
=========================================================

Loki is a fast, read-only browser for the systemd journal. The interface is
available in Finnish and English. It follows the system language (Finnish uses
Finnish; all other languages use English) until you choose a language in the
application. Your choice is saved for the next launch.

1. REQUIREMENTS

    sudo pacman -S --needed pyside6

The application requires systemd's journalctl command. Loki does not require
root privileges. Some system logs may not be visible to a regular user.

2. INSTALL IN THE KDE APPLICATION MENU

Extract the ZIP and open a terminal in the extracted "loki" directory. Run:

    python3 asennus.py

Do not use sudo for this command.

Installation creates only user files:
  ~/.local/share/loki-journal/                     application and uninstaller
  ~/.local/share/applications/loki-journal.desktop application menu entry
  ~/.local/share/icons/hicolor/scalable/apps/loki-journal.svg icon
  ~/.local/bin/loki-journal                        command-line launcher

If XDG_DATA_HOME is set, data and icon directories are placed there.

Find "Loki" in Plasma's application menu. You can pin the application to the
taskbar by right-clicking it after launch. Or run ~/.local/bin/loki-journal.

3. UNINSTALL

    python3 ~/.local/share/loki-journal/asennus.py --poista

If you set XDG_DATA_HOME, use its actual path. Uninstall does not remove the
journal or exported TXT files.

4. RUN WITHOUT INSTALLING

You can also launch the extracted application directly:

    python3 loki.py

5. FEATURES

- Finnish and English interface with a saved language preference.
- KDE user-level application menu entry and matching window identity.
- QTableView, background journal queries, search, filters, timing metrics and
  TXT export.
- Read-only journal access; root privileges and a network connection are not
  needed.

SECURITY AND LIMITATIONS

Logs can contain personal data and other sensitive information. Review exports
before sharing them. Some logs may require membership in the appropriate system
group to be visible.


LOKI 0.4 – KDE Plasma -integraatio (CachyOS / Arch Linux)
========================================================

Loki on systemd-journalin nopea, vain luku -tilassa toimiva selainsovellus.
Käyttöliittymä on suomeksi ja englanniksi. Ohjelma käyttää järjestelmän kieltä
(suomi valitsee suomen, muut kielet englannin), kunnes valitset kielen
sovelluksessa. Valinta tallennetaan seuraavaa käynnistystä varten.

1. EDELLYTYKSET

    sudo pacman -S --needed pyside6

Ohjelma tarvitsee systemd:n journalctl-komennon. Loki ei vaadi root-oikeuksia.
Kaikki järjestelmälokit eivät välttämättä näy tavalliselle käyttäjälle.

2. ASENNUS KDE PLASMAN VALIKKOON

Pura ZIP ja avaa terminaali purettuun "loki"-hakemistoon. Suorita:

    python3 asennus.py

ÄLÄ käytä sudoa tässä komennossa.

Asennus luo vain käyttäjäkohtaiset tiedostot:
  ~/.local/share/loki-journal/                     ohjelmakoodi ja poisto
  ~/.local/share/applications/loki-journal.desktop käynnistysvalikko
  ~/.local/share/icons/hicolor/scalable/apps/loki-journal.svg kuvake
  ~/.local/bin/loki-journal                        komentorivikäynnistin

Jos XDG_DATA_HOME on asetettu, data- ja kuvakehakemistot sijoitetaan sinne.

Etsi Plasman sovellusvalikosta "Loki". Voit kiinnittää sovelluksen
tehtäväpalkkiin käynnistämisen jälkeen oikealla hiiren napilla. Voit myös
käynnistää ohjelman komennolla ~/.local/bin/loki-journal.

3. POISTO

    python3 ~/.local/share/loki-journal/asennus.py --poista

Jos olet määrittänyt XDG_DATA_HOME:n, anna sen todellinen polku. Poisto ei
koske itse journalia eikä TXT-muotoon tallennettuja lokitiedostoja.

4. KÄYTTÖ ILMAN ASENNUSTA

Voit myös käynnistää puretun ohjelman suoraan:

    python3 loki.py

5. OMINAISUUDET

- Suomen- ja englanninkielinen käyttöliittymä ja tallennettava kielivalinta.
- Käyttäjäkohtainen KDE:n sovellusvalikkokäynnistin ja ikkunatunniste.
- QTableView, taustalla toimivat journal-haut, haku, suodattimet,
  ajoitusmittarit ja TXT-vienti.
- Journalin luku ei muuta lokeja eikä vaadi root-oikeuksia tai verkkoyhteyttä.

TIETOTURVA JA RAJOITUKSET

Lokit voivat sisältää henkilötietoja ja muita arkaluonteisia merkintöjä.
Tarkista tallenteet ennen niiden jakamista. Osa lokeista voi edellyttää
käyttäjän lisäämistä oikeaan järjestelmäryhmään.
