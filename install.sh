# --- Konfiguration ---
COMMAND_NAME="pod-tui"
MAIN_SCRIPT="pod-tui.py"
PROJECT_DIR=$(pwd)
VENV_DIR="$PROJECT_DIR/.venv"
BIN_DIR="$HOME/.local/bin"

echo "--- POD-TUI Installationsguide ---"
echo "Kontrollerar beroenden..."

# 1. Kontrollera grundläggande verktyg
if ! command -v python3 &> /dev/null || ! command -v pip &> /dev/null; then
    echo "Fel: Python3 och/eller pip är inte installerat."
    exit 1
fi

# 2. Skapa den virtuella miljön (.venv)
echo "Skapar virtuell miljö i $VENV_DIR..."
python3 -m venv "$VENV_DIR"

# 3. Aktivera och installera beroenden
source "$VENV_DIR/bin/activate"
echo "Installerar Python-beroenden från requirements.txt..."
pip install requests feedparser rich
deactivate

# 4. Skapa en global 'wrapper'
echo "Skapar en global länk ($COMMAND_NAME) i $BIN_DIR..."
mkdir -p "$BIN_DIR"

WRAPPER_SCRIPT="$BIN_DIR/$COMMAND_NAME"

cat << EOF > "$WRAPPER_SCRIPT"
#!/bin/bash
"$VENV_DIR/bin/python" "$PROJECT_DIR/$MAIN_SCRIPT" "\$@"
EOF

chmod +x "$WRAPPER_SCRIPT"

echo "✅ Installationen är klar!"
echo "Du kan nu köra: $COMMAND_NAME"
