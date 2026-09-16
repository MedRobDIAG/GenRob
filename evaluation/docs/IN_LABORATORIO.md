# In laboratorio — foglio operativo

**Macchina:** PC del Prof. Leonardi · RTX 5090, 31,5 GB di memoria video · doppio avvio Windows/Ubuntu
**Durata prevista:** 2-2,5 ore · **Cosa porti a casa:** un file zip da meno di 1 MB

> **Regola d'oro:** se un comando dà errore, **fermati e copiami il messaggio**. Non tentare
> varianti a caso: quasi sempre è un problema di versione, e indovinare costa più tempo che
> chiedere.

---

## Prima di uscire di casa

Metti su una **chiavetta USB** (o mandati un'email a te stesso, è piccolo):

- `demiurge_test_vlm_locale.zip` — il banco di prova

Tutto qui. Il resto si scarica sul posto.

---

## Cosa dire al professore, all'arrivo

> «Devo **far girare** un modello visione-linguaggio su sette schede tecniche, non addestrarlo.
> Sono circa due ore, di cui buona parte è scaricare il modello. Lavoro in una cartella mia e
> uso un ambiente Python separato, quindi non tocco nulla del sistema.»

Poi quattro domande pratiche, tutte importanti:

1. **«Posso avviare in Ubuntu invece che Windows?»** — su Windows queste librerie sono molto più
   fragili. Se può, Ubuntu.
2. **«Posso installare pacchetti Python?»** — non servono privilegi di amministratore, installo
   tutto dentro la mia cartella. È utile che lo sappia.
3. **«Il modello occupa circa 17 GB nella cache. Lo lascio o lo cancello quando ho finito?»** —
   se torno, lasciarlo mi risparmia mezz'ora la prossima volta. Decide lui.
4. ⭐ **«Posso avere un accesso SSH per collegarmi da remoto?»** — è la domanda che vale di più.
   Se dice sì, questa è **l'unica volta** che devo venire di persona: ripetizioni, varianti e
   inevitabili secondi tentativi li faccio da casa.

---

## PASSO 1 — Guarda cosa hai davanti (5 minuti)

Apri un terminale (su Ubuntu: `Ctrl+Alt+T`). Crea la tua cartella e copiaci il banco:

```bash
mkdir -p ~/demiurge-francesco
cd ~/demiurge-francesco
# copia qui lo zip dalla chiavetta, poi:
unzip demiurge_test_vlm_locale.zip
cd test_vlm
```

Ora il controllo preliminare:

```bash
python3 controlla.py
```

**Cosa devi leggere nell'uscita:**

| se vedi | significa |
|---|---|
| `NVIDIA GeForce RTX 5090 ... 31.5 GB` | tutto bene, procedi |
| `nvidia-smi non risponde` | sei avviato in Windows, o manca il driver — chiedi al professore |
| `HuggingFace NON raggiungibile` | la rete blocca il download — **fermati e scrivimi** |
| meno di 60 GB liberi su disco | **scrivimi**, dobbiamo ridimensionare il piano |

Il comando salva `controlla_esito.json`: tienilo, va nei risultati.

---

## PASSO 2 — Prepara l'ambiente (10 minuti)

Un «ambiente virtuale» è una cartella isolata dove finiscono i pacchetti: non tocca il Python
del sistema, e cancellandola sparisce tutto. Serve proprio perché la macchina non è tua.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Da ora il prompt mostra `(.venv)` all'inizio. **Se chiudi il terminale devi rifare
`source .venv/bin/activate`** prima di qualunque altro comando.

```bash
pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install transformers accelerate pillow pyyaml
```

La 5090 è una scheda recente: serve la versione di PyTorch per CUDA 12.8, da qui l'indirizzo
speciale nella seconda riga. Verifica che abbia funzionato:

```bash
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Deve stampare `True NVIDIA GeForce RTX 5090`. **Se stampa `False`, fermati e scrivimi.**

---

## PASSO 3 — Prova del fumo (20-30 minuti, quasi tutto attesa)

```bash
python3 esegui_locale.py --prova --quant none --max-pixels 1229312
```

Qui scarica il modello: **17 GB**. È il pezzo lungo, e succede una volta sola.

> **Perché `--quant none` e non `8`.** Con 31,5 GB il modello ci sta **senza alcuna
> compressione**, e questo è meglio per due motivi: è il vero tetto di prestazione del modello,
> ed evita la libreria di quantizzazione, che sulle schede appena uscite è la cosa che più spesso
> dà problemi. Se questo funziona, abbiamo già il confronto che ci serve.

Alla fine stampa la risposta del modello, se il JSON è valido, il tempo e la memoria usata.
**Segnati il numero della VRAM** — serve per la richiesta infrastrutturale.

**Se dice «CUDA out of memory»:** riprova con `--quant 8`. Se anche quello fallisce per un errore
che nomina `bitsandbytes`, riprova con `--quant 4` e scrivimi.

---

## PASSO 4 — Le tre misure che contano (25 minuti in tutto)

Lanciale **in quest'ordine**. Se il tempo finisce, quello che hai fatto è già utile.

```bash
# 1. la campagna completa, senza compressione
python3 esegui_locale.py --quant none --max-pixels 1229312 --etichetta qwen8_pieno_base
python3 valuta.py risultati/qwen8_pieno_base/*.json
```

```bash
# 2. la stessa cosa senza immagine (baseline obbligatoria)
python3 esegui_locale.py --quant none --variante solo_testo --etichetta qwen8_pieno_solotesto
python3 valuta.py risultati/qwen8_pieno_solotesto/*.json
```

```bash
# 3. tre ripetizioni sui cinque robot ancorati (auto-coerenza)
python3 esegui_locale.py --quant none --max-pixels 1229312 --ripetizioni 3 \
    --etichetta qwen8_pieno_ripetuto \
    --robot yaskawa_gp8 yaskawa_gp7 kuka_iisy8_R930 kuka_kr4_R600 abb_irb6400pe
```

**Il numero `1229312` non va cambiato.** È la stessa risoluzione usata a casa: se cambia, il
confronto fra le due giornate non vale più niente.

### Se avanza tempo — gli 8 bit

```bash
python3 esegui_locale.py --quant 8 --max-pixels 1229312 --etichetta qwen8_8bit_base
python3 valuta.py risultati/qwen8_8bit_base/*.json
```

Aggiunge un punto intermedio sull'asse della compressione: avremmo 4 bit, 8 bit e nessuna
compressione. Tre punti invece di due.

### Se avanza molto tempo — il modello grande

⚠️ **Prima controlla lo spazio:** `df -h ~` — il modello da 32B pesa circa **64 GB** da
scaricare. Se non ci stanno, salta.

```bash
python3 esegui_locale.py --quant 4 --modello qwen32 --max-pixels 1229312 --etichetta qwen32_4bit_base
```

---

## PASSO 5 — Raccogli i risultati e vai via (5 minuti)

I risultati sono **piccolissimi**: solo file di testo, in tutto meno di 1 MB.

```bash
cd ~/demiurge-francesco/test_vlm
cp controlla_esito.json risultati/ 2>/dev/null
zip -r ~/risultati_lab.zip risultati/
ls -lh ~/risultati_lab.zip
```

Poi portalo a casa in uno di questi modi, in ordine di affidabilità:

1. **chiavetta USB** — `cp ~/risultati_lab.zip /media/...` (il percorso lo vedi nel gestore file);
2. **email a te stesso** — è meno di 1 MB, passa ovunque come allegato;
3. **Google Drive dal browser** — funziona, ma ricordati di **uscire dall'account** quando hai finito.

### Prima di lasciare la postazione

```bash
deactivate                  # esce dall'ambiente virtuale
```

E poi, **solo se il professore ha detto di ripulire**:

```bash
rm -rf ~/demiurge-francesco
rm -rf ~/.cache/huggingface        # i 17 GB del modello
```

Se ha detto di lasciare, non cancellare niente: la prossima volta risparmi mezz'ora di download.
In ogni caso **non lasciare account aperti** nel browser.

---

## Riepilogo dei tempi

| passo | durata |
|---|---|
| 1 · controllo macchina | 5 min |
| 2 · ambiente e pacchetti | 10 min |
| 3 · prova del fumo (incluso scaricamento) | 20-30 min |
| 4 · le tre misure | 25 min |
| margine per imprevisti | 30-45 min |
| 5 · raccolta e pulizia | 5 min |
| **totale realistico** | **2 - 2,5 ore** |

Con gli 8 bit e il modello grande si arriva a 3,5-4 ore.

---

## Se qualcosa va storto

**Non improvvisare.** Copia il messaggio d'errore per intero — anche se è lungo — e mandamelo.
Le tre cose che più probabilmente succederanno, e che so già come affrontare:

- **PyTorch non vede la GPU** → versione CUDA sbagliata, si risolve cambiando una riga;
- **errore che nomina `bitsandbytes` o `sm_120`** → è la scheda troppo nuova per la libreria di
  quantizzazione; la soluzione è `--quant none`, che infatti è il piano principale;
- **il modello risponde ma il JSON non è valido** → non è un guasto, è un risultato: le risposte
  grezze finiscono in file `.raw.txt` accanto ai risultati. Portali a casa, sono dati.

Qualunque cosa succeda, **i risultati parziali valgono**. Anche solo il passo 4.1 fatto bene
cambia il report.
