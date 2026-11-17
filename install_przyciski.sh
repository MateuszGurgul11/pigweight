#!/usr/bin/env bash
# Instaluje przyciski.py (wlacznik I/O + spust) jako usluge uzytkownika,
# ktora startuje sama po wlaczeniu Pi. Uruchom z folderu projektu:
#   cd ~/Desktop/pigweight
#   bash install_przyciski.sh
#
# Usluga uruchamia przyciski.py prosto z repo — git pull (start_live.sh)
# aktualizuje kod; nowa wersja dziala po: systemctl --user restart przyciski
#
# Wymaga sudo bez hasla (domyslnie pierwszy uzytkownik Pi OS) — przyciski.py
# wola sudo rfkill / sudo tee na governor procesora.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SKRYPT="$ROOT/przyciski.py"

if [[ ! -f "$SKRYPT" ]]; then
  echo "BLAD: brak $SKRYPT"
  exit 1
fi
chmod +x "$SKRYPT"

if ! sudo -n true 2>/dev/null; then
  echo "UWAGA: sudo wymaga hasla — usypianie (rfkill, governor) nie zadziala w usludze."
  echo "       Ekran i spust beda dzialac."
fi

# Pakiety systemowe (zwykle juz sa w Raspberry Pi OS); python3 systemowy, nie .venv
sudo apt-get install -y python3-gpiozero python3-lgpio wlr-randr rfkill

# Stara wersja z instaluj.sh (kopia w ~/przyciski) — zastepujemy wersja z repo
if [[ -f "$HOME/przyciski/przyciski.py" ]]; then
  echo ">>> Stara kopia $HOME/przyciski/przyciski.py nie bedzie juz uzywana (mozna usunac)"
fi

mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/przyciski.service" <<EOF
[Unit]
Description=PigWeight — wlacznik I/O i spust (GPIO 27 / GPIO 17)
After=graphical-session.target

[Service]
WorkingDirectory=$ROOT
ExecStart=/usr/bin/python3 $SKRYPT
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable przyciski.service
systemctl --user restart przyciski.service
sudo loginctl enable-linger "$USER"

echo
echo "Gotowe. Status:   systemctl --user status przyciski"
echo "Logi na zywo:     journalctl --user -u przyciski -f"
