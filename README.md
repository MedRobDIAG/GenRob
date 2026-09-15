# DEMIURGE — demo tecnica

Dimostratore tecnico dei due moduli generativi puri descritti nella relazione
(*Sistemi generativi per ambienti di simulazione immersiva*, DIAG Sapienza,
bando 36/2026): **Modulo A** (estrazione di parametri robotici da un manuale
tecnico) e **Modulo B** (generazione di una scena da un obiettivo di
apprendimento), più il passaggio successivo di validazione visiva in
CoppeliaSim.

Principio guida, coerente col report: **separare nettamente cosa è
generativo (AI) da cosa è deterministico (script/parsing)**. Solo due script
in tutta la repo chiamano un modello generativo
(`module_a/extract_from_manual.py`, `module_b/generate_scene.py`); tutto il
resto — costruzione URDF, validazione cinematica, rendering della scena,
import in CoppeliaSim — è codice deterministico e gira su qualunque laptop,
senza GPU.

## Struttura

```
module_a/                 Modulo A: manuale tecnico -> parametri -> URDF -> validazione
  extract_from_manual.py    [GPU] VLM (Qwen3-VL) legge il PDF -> data/extracted.json
  urdf_builder.py            deterministico: tabella DH -> URDF (condiviso)
  build_extracted.py         deterministico: data/extracted.json -> outputs/extracted_robot.urdf
  build_reference.py         deterministico: xacro pubblico KUKA -> outputs/reference_robot.urdf
  validate.py                deterministico: confronto quantitativo (portata + cinematica)
  data/
    extracted.json           output cache di un run precedente di extract_from_manual.py
    kuka_lwr.urdf.xacro      xacro di riferimento pubblico (scaricato automaticamente se assente)

module_b/                 Modulo B: obiettivo di apprendimento -> scena Three.js
  generate_scene.py          [GPU] LLM (Qwen3-VL) compone la scena -> data/scene_spec.json
  render_scene.py             deterministico: scene_spec.json -> outputs/scene.html (Three.js)
  data/
    example_scene_spec.json  output cache di un run precedente di generate_scene.py

coppelia/
  compare_in_coppeliasim.py  importa i due URDF in CoppeliaSim e li affianca (via zmqRemoteApi)

notebooks/
  demiurge_demo.ipynb        prototipo originale (Colab), tenuto per riferimento/cronologia

outputs/                  file generati (gitignored)
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # su Linux/macOS; su Windows: .venv\Scripts\activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

`requirements.txt` include gia' tutto il necessario per rieseguire davvero
i due script generativi (`torch`, `torchvision`, `transformers`,
`accelerate`, `qwen-vl-utils`, `pymupdf`) — girano senza modifiche su:

- **GPU NVIDIA (CUDA)**: quantizzazione 4-bit via bitsandbytes — decommenta
  `bitsandbytes` in `requirements.txt` (solo Linux/Windows con CUDA, non
  installabile su Apple Silicon).
- **Mac Apple Silicon**: backend MPS di PyTorch, nessuna quantizzazione
  (bitsandbytes e' CUDA-only). Testato su MacBook Pro M5 Pro/24GB: il
  modello Qwen3-VL-4B (~8GB) gira comodamente.
- **CPU**: funziona ma e' lento (minuti per singola inferenza anziche'
  secondi).

Il device viene rilevato automaticamente (`cuda` > `mps` > `cpu`), stesso
codice su tutte le piattaforme. Il primo avvio di uno dei due script scarica
il modello da Hugging Face (~8GB, una tantum, cache in `~/.cache/huggingface`).

Senza GPU o senza voler scaricare il modello, tutta la pipeline
deterministica gira comunque partendo dai dati cache in `module_a/data/` e
`module_b/data/` (output di run precedenti, gia' inclusi nella repo).

## Modulo A — riproduzione end-to-end

```bash
cd module_a

# 1. [~8GB di download al primo avvio] estrazione dal manuale PDF
python3 extract_from_manual.py --pdf manuale.pdf --pages 12 13 --drawing-page 14
#    (per saltare questo passo: si riusa data/extracted.json, gia' presente)

# 2. costruzione URDF (deterministico)
python3 build_extracted.py
python3 build_reference.py

# 3. validazione quantitativa (deterministico)
python3 validate.py
```

`--pages`/`--drawing-page` sono indici di pagina 0-based nel PDF: nel
manuale KUKA LBR iiwa usato per questo dimostratore, le pagine 13-14
(indici 12-13) contengono la tabella delle specifiche e la pagina 15
(indice 14) il disegno quotato con le lunghezze dei link.

Output atteso del passo 1 (confermato su Mac M5 Pro, backend MPS, con lo
stesso PDF): il VLM legge correttamente nome, 7 giunti, payload, reach,
massa, ripetibilita' e range/velocita' per giunto dalla tabella; sul disegno
quotato **non** legge le quote con sicurezza sufficiente e restituisce
`link_dimensions_mm: [null, null]` invece di inventare un numero (comportamento
voluto dal prompt) — lo script stampa un avviso e va completato a mano,
inserendo i due valori (spalla→gomito, gomito→polso, in mm) in
`data/extracted.json` prima del passo 2.

Output atteso di `validate.py` (con i dati cache forniti, o con 400/400mm
inseriti a mano dopo il passo 1):

```
Portata totale — estratta:    800.0 mm
Portata totale — riferimento: 790.0 mm
Errore: 10.0 mm (1.3%)

Equivalenza cinematica su 300 coppie casuali:
  Errore posizione:    media 13.11 mm, max 19.96 mm
  Errore orientazione: media 0.0000°, max 0.0000°
```

Nota metodologica: `build_reference.py` non usa la somma grezza dei 7 offset
di giunto nello xacro pubblico (che mescolerebbe geometria del pedestal e
della flangia con le lunghezze dei link, sovrastimando l'errore) — li
raggruppa nella convenzione DH standard per il KUKA LWR4+/iiwa (paper Gaz,
Flacco, De Luca, in bibliografia nel report), la stessa a 2 soli offset non
nulli (spalla→gomito, gomito→polso) assunta anche da `build_extracted.py`.
Il residuo 1.3% riflette la sola imprecisione del VLM nel leggere la seconda
quota dal disegno (400mm letti contro 390mm reali) — vedi il docstring di
`build_reference.py` per il dettaglio del raggruppamento.

## Modulo B — riproduzione end-to-end

```bash
cd module_b

# 1. [~8GB di download al primo avvio, o riuso della cache se gia' scaricato per il Modulo A]
python3 generate_scene.py --objective "Spiega le tappe del ciclo di Krebs..." --out data/scene_spec.json

# 2. render Three.js (deterministico)
python3 render_scene.py --spec data/scene_spec.json
# apri ../outputs/scene.html nel browser (doppio click, oppure "open" su macOS,
# "xdg-open" su Linux), o servilo con: python3 -m http.server --directory ../outputs
```

Senza rieseguire il passo 1: `python3 render_scene.py` (senza `--spec`) usa
di default `data/example_scene_spec.json`, gia' incluso nella repo.

Output atteso del passo 1 (confermato su Mac M5 Pro, backend MPS): un JSON
valido con 2-3 elementi scelti in modo specifico per l'obiettivo dato (es.
per un obiettivo sul volume operativo: `robot_kuka` con
`highlight: joint_limits` + `target_marker` raggiungibile) — non sempre la
stessa combinazione fissa.

## Confronto in CoppeliaSim (S3.8 del report)

Prerequisiti: [CoppeliaSim](https://www.coppeliarobotics.com/downloads)
(edition Edu) installato e aperto, con il server zmqRemoteApi attivo (di
default lo e' su `localhost:23000` — nessuna configurazione aggiuntiva
richiesta su un'installazione standard).

```bash
python3 -m pip install coppeliasim-zmqremoteapi-client
```

**Confronto visivo** — importa i due URDF affiancati nella scena aperta:

```bash
cd coppelia
python3 compare_in_coppeliasim.py

# per vedere i due bracci in una posa piegata (non a riposo/distesa) e
# confrontarli visivamente fianco a fianco:
python3 set_demo_pose.py
```

`set_demo_pose.py` comanda i giunti come motorizzati (`setJointTargetPosition`),
fa girare la simulazione per un paio di secondi e poi la mette in **pausa**
(mai in *stop*, che riporterebbe il robot alla posa iniziale).

**Validazione quantitativa in simulazione** (suggerita in sede di revisione
del progetto: non affidarsi al solo confronto visivo, ma comandare lo stesso
valore ai giunti corrispondenti dei due robot e misurare — leggendola
dall'ambiente di simulazione, non calcolandola offline — la posa di un
piccolo utensile all'estremita' di ciascun braccio, cosi' da validare sia
la posizione che l'orientamento):

```bash
python3 measure_toolpose.py --n-poses 20
```

Lo script reimporta i due robot, aggiunge un dummy "tool tip" all'estremita'
di `link_7` di ciascuno, e per un campione di pose casuali (entro i limiti
di giunto) comanda gli stessi angoli a entrambi e confronta la posa del tool
tip letta dal motore fisico di CoppeliaSim. Output atteso:

```
Errore posizione:    media 10.00 mm, max 10.00 mm
Errore orientamento: media 0.000°, max 0.000°
```

L'errore di posizione e' **costante** su tutte le pose (non solo in media) —
coerente con la causa nota (§1.9, §3.2): un solo segmento (spalla→gomito o
gomito→polso) differisce di 10 mm tra estratto e riferimento (400 vs 390 mm,
l'imprecisione del VLM nel leggere la seconda quota dal disegno), e poiche'
le rotazioni a valle preservano la lunghezza di quel vettore di errore, il
suo modulo non dipende dalla configurazione del braccio — una proprieta'
geometrica esatta, non una coincidenza del campione di pose. L'errore di
orientamento e' zero in ogni posa perche' i due modelli condividono
esattamente gli stessi angoli α (la topologia angolare estratta era gia'
corretta al 100%, unico errore quello sulla singola lunghezza di link).

## Limiti dichiarati

Vedi la Parte III del report tecnico (§3.5) per la lista completa. In sintesi:
nessun fine-tuning (modelli pre-addestrati generici), un solo documento/run
per il Modulo A, nessuna simulazione fisica completa (solo confronto
cinematico/geometrico), validazione del Modulo B qualitativa (non esiste un
"ground truth" per una scena didattica).
