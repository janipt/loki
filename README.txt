LOKI 0.3 – KDE Plasma -integraatio (CachyOS / Arch Linux)
========================================================

Loki on systemd-journalin nopea, vain luku -tilassa toimiva selainsovellus.
Versio 0.3 perustuu toimivaksi todettuun 0.2-versioon. Lokin varsinaisia
hakutoimintoja tai käyttöliittymärakennetta ei ole muutettu.

1. EDELLYTYKSET

    sudo pacman -S --needed pyside6

Ohjelma tarvitsee systemd:n journalctl-komennon. Loki ei vaadi root-oikeuksia.
Kaikki järjestelmälokit eivät välttämättä näy tavalliselle käyttäjälle.

2. ASENNUS KDE PLASMAN VALIKKOON

Pura ZIP ja avaa terminaali purettuun "loki"-hakemistoon. Suorita:

    python3 asennus.py

ÄLÄ käytä sudoa tässä komennossa.

Asennus luo vain käyttäjäkohtaiset tiedostot:
  ~/.local/share/loki-journal/                    ohjelmakoodi ja poisto
  ~/.local/share/applications/loki-journal.desktop käynnistysvalikko
  ~/.local/share/icons/hicolor/scalable/apps/loki-journal.svg kuvake
  ~/.local/bin/loki-journal                       komentorivikäynnistin

Jos XDG_DATA_HOME on asetettu, data- ja kuvakehakemistot sijoitetaan sinne.

Etsi Plasman sovellusvalikosta "Loki". Voit kiinnittää sovelluksen
tehtäväpalkkiin käynnistämisen jälkeen oikealla hiiren napilla.
Vaihtoehtoisesti voit käynnistää ohjelman komennolla ~/.local/bin/loki-journal.

3. POISTO

    python3 ~/.local/share/loki-journal/asennus.py --poista

Jos olet määrittänyt XDG_DATA_HOME:n, anna sen todellinen polku.
Poisto ei koske itse journalia eikä TXT-muotoon tallennettuja lokitiedostoja.

4. KÄYTTÖ ILMAN ASENNUSTA

Voit myös käynnistää puretun ohjelman suoraan:

    python3 loki.py

5. MUUTOKSET VERSIOON 0.2

- Oma SVG-kuvake näkyy ikkunassa ja Plasma-valikossa.
- Käyttäjäkohtainen .desktop-käynnistin (ei sudoa).
- Työpöytätunnus KDE:n/Waylandin ikkunan ja tehtäväpalkin yhdistämiseksi.
- Komentorivin käynnistin sekä poistomahdollisuus.
- 0.2:n QTableView, taustasäikeet, haku, suodattimet, ajoitusmittarit
  ja TXT-vienti säilytetty ennallaan.

TIETOTURVA JA RAJOITUKSET

Loki lukee lokit eikä muuta niitä, vaadi ylläpitäjän oikeuksia tai käytä
verkkoyhteyttä. Lokit voivat sisältää henkilötietoja ja muita arkaluonteisia
merkintöjä. Tarkista tallenteet ennen niiden jakamista.

Asennusskriptin toiminta ja Python-syntaksi on testattu eristetyssä
ympäristössä; graafista KDE-toimintaa ei voida täysin testata ilman
paikallista CachyOS/Plasma-istuntoa.
