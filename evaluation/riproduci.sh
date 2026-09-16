#!/usr/bin/env bash
# Riproduzione delle misure della Parte II.
#
#   ./riproduci.sh              livello deterministico: ricalcola tutte le cifre
#                               dai risultati versionati. Nessuna GPU. ~10 secondi.
#   ./riproduci.sh --modello    rilancia anche il modello sulle stesse pagine.
#                               Richiede GPU e ~17 GB di scaricamento.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1. verifica delle cifre della relazione =="
python3 verifica_numeri.py
echo

echo "== 2. dettaglio per robot, campagna con immagine =="
python3 valuta.py risultati/qwen8_4bit_base/*.json | tail -20
echo

echo "== 3. dettaglio per robot, baseline solo testo =="
python3 valuta.py risultati/qwen8_4bit_solo_testo/*.json | tail -12
echo

if [ "${1:-}" = "--modello" ]; then
  echo "== 4. riesecuzione del modello =="
  python3 controlla.py
  python3 esegui_locale.py --quant 4 --max-pixels 1229312 --etichetta riproduzione
  python3 esegui_locale.py --quant 4 --variante solo_testo --etichetta riproduzione_solo_testo
  echo
  echo "I nuovi risultati sono in risultati/riproduzione*/."
  echo "Confrontali con: python3 valuta.py risultati/riproduzione/*.json"
  echo "Nota: a temperatura nulla l'uscita e' quasi deterministica, ma non"
  echo "garantita bit-per-bit fra versioni diverse di transformers o di GPU."
fi
