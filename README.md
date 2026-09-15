# DEMIURGE — Dimostratore tecnico

Dimostratore tecnico dei due moduli generativi descritti nella relazione
finale (*Sistemi generativi per ambienti di simulazione immersiva*, DIAG
Sapienza, bando 36/2026): il **Modulo A** (estrazione di parametri
robotici da un manuale tecnico) e il **Modulo B** (generazione di una
scena da un obiettivo di apprendimento), corredati da una fase di
validazione visiva e quantitativa in CoppeliaSim.

Principio architetturale adottato in tutta la repository: separare
nettamente la componente generativa (basata su modelli di intelligenza
artificiale) dalla componente deterministica (script di parsing e
calcolo). Solo due script dell'intera repository invocano un modello
generativo (`module_a/extract_from_manual.py` e
`module_b/generate_scene.py`); il resto — costruzione dell'URDF,
validazione cinematica, rendering della scena, importazione in
CoppeliaSim — è codice deterministico, eseguibile su qualunque
elaboratore, senza necessità di GPU dedicata.

## Struttura della repository

```
module_a/                 Modulo A: manuale tecnico -> parametri -> URDF -> validazione
  extract_from_manual.py    [GPU] estrazione via VLM (Qwen3-VL) dal PDF -> data/extracted.json
  urdf_builder.py            deterministico: tabella DH -> URDF (condiviso dai due script seguenti)
  build_extracted.py         deterministico: data/extracted.json -> outputs/extracted_robot.urdf
  build_reference.py         deterministico: xacro pubblico KUKA -> outputs/reference_robot.urdf
  validate.py                deterministico: confronto quantitativo (portata e cinematica)
  data/
    extracted.json           output cache di un'esecuzione precedente di extract_from_manual.py
    kuka_lwr.urdf.xacro       xacro di riferimento pubblico (scaricato automaticamente se assente)

module_b/                 Modulo B: obiettivo di apprendimento -> scena Three.js
  generate_scene.py          [GPU] composizione della scena via LLM (Qwen3-VL) -> data/scene_spec.json
  render_scene.py             deterministico: scene_spec.json -> outputs/scene.html (Three.js)
  data/
    example_scene_spec.json  output cache di un'esecuzione precedente di generate_scene.py

coppelia/
  compare_in_coppeliasim.py  importa i due URDF in CoppeliaSim e li affianca (via zmqRemoteApi)
  compare_with_meshes.py     variante con le mesh CAD reali del KUKA LWR 4+, a scopo illustrativo
  set_demo_pose.py           applica una posa piegata ai robot importati, per il confronto visivo
  measure_toolpose.py        validazione quantitativa di posizione e orientamento del tool tip

notebooks/
  demiurge_demo.ipynb        prototipo originale (Colab), conservato per riferimento

outputs/                  file generati dall'esecuzione della pipeline (esclusi dal controllo versione)
```

## Requisiti e installazione

```bash
python3 -m venv .venv
source .venv/bin/activate        # su Linux/macOS; su Windows: .venv\Scripts\activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

Il file `requirements.txt` include tutte le dipendenze necessarie per
eseguire i due script generativi (`torch`, `torchvision`,
`transformers`, `accelerate`, `qwen-vl-utils`, `pymupdf`), compatibili
senza modifiche con le seguenti configurazioni hardware:

- **GPU NVIDIA (CUDA)**: quantizzazione a 4 bit tramite bitsandbytes —
  decommentare `bitsandbytes` in `requirements.txt` (disponibile solo su
  Linux/Windows con CUDA; non installabile su Apple Silicon).
- **Mac Apple Silicon**: backend MPS di PyTorch, senza quantizzazione
  (bitsandbytes richiede CUDA). Configurazione testata su MacBook Pro
  M5 Pro/24GB: il modello Qwen3-VL-4B (circa 8GB) viene eseguito senza
  difficoltà.
- **CPU**: funzionante ma significativamente più lento (minuti anziché
  secondi per singola inferenza).

Il dispositivo di calcolo viene rilevato automaticamente in ordine di
preferenza (`cuda` > `mps` > `cpu`); il codice è identico su tutte le
piattaforme. Al primo avvio di uno dei due script generativi, il modello
viene scaricato da Hugging Face (circa 8GB, un'unica volta, con cache in
`~/.cache/huggingface`).

In assenza di GPU, o qualora non si desideri scaricare il modello,
l'intera pipeline deterministica è comunque eseguibile a partire dai
dati già presenti in `module_a/data/` e `module_b/data/` (output di
esecuzioni precedenti, inclusi nella repository).

## Modulo A — riproduzione end-to-end

```bash
cd module_a

# 1. [~8GB di download al primo avvio] estrazione dal manuale tecnico
python3 extract_from_manual.py --pdf manuale.pdf --pages 12 13 --drawing-page 14
#    (per omettere questo passaggio: si riusa data/extracted.json, già presente)

# 2. costruzione dell'URDF (deterministico)
python3 build_extracted.py
python3 build_reference.py

# 3. validazione quantitativa (deterministico)
python3 validate.py
```

Gli indici `--pages`/`--drawing-page` sono a base 0: nel manuale KUKA LBR
iiwa utilizzato per questo dimostratore, le pagine 13–14 (indici 12–13)
contengono la tabella delle specifiche tecniche, mentre la pagina 15
(indice 14) contiene il disegno quotato con le lunghezze dei link.

Risultato atteso del primo passaggio (confermato su Mac M5 Pro, backend
MPS, con lo stesso documento PDF): il modello estrae correttamente nome
del sistema, numero di giunti, payload, portata, massa, ripetibilità e
range/velocità per ciascun giunto dalla tabella; sul disegno quotato non
legge le quote con sufficiente affidabilità e restituisce
`link_dimensions_mm: [null, null]` anziché generare un valore non
verificato (comportamento previsto dal prompt) — lo script segnala
l'avviso corrispondente, e il completamento richiede l'inserimento
manuale dei due valori (spalla–gomito, gomito–polso, in millimetri) in
`data/extracted.json` prima di procedere al secondo passaggio.

Risultato atteso di `validate.py` (con i dati cache forniti, oppure con
i valori 400/400mm inseriti manualmente dopo il primo passaggio):

```
Portata totale — estratta:    800.0 mm
Portata totale — riferimento: 790.0 mm
Errore: 10.0 mm (1.3%)

Equivalenza cinematica su 300 coppie casuali:
  Errore posizione:    media 13.11 mm, max 19.96 mm
  Errore orientazione: media 0.0000°, max 0.0000°
```

**Nota metodologica.** `build_reference.py` non utilizza la somma grezza
dei sette offset di giunto presenti nello xacro pubblico, poiché
mescolerebbe la geometria del piedistallo e della flangia con le
lunghezze dei link, sovrastimando l'errore. Gli offset vengono invece
raggruppati secondo la convenzione DH standard per il KUKA LWR4+/iiwa
(Gaz, Flacco, De Luca — in bibliografia nel report), la medesima
convenzione a due soli offset non nulli (spalla–gomito, gomito–polso)
assunta da `build_extracted.py`. Lo scostamento residuo dell'1.3%
riflette unicamente l'imprecisione del modello nella lettura della
seconda quota dal disegno (400mm letti contro 390mm reali); si veda il
docstring di `build_reference.py` per il dettaglio del raggruppamento.

## Modulo B — riproduzione end-to-end

```bash
cd module_b

# 1. [~8GB di download al primo avvio, oppure riuso della cache se già scaricata per il Modulo A]
python3 generate_scene.py --objective "Spiega le tappe del ciclo di Krebs..." --out data/scene_spec.json

# 2. rendering Three.js (deterministico)
python3 render_scene.py --spec data/scene_spec.json
# aprire ../outputs/scene.html nel browser (doppio clic, oppure "open" su macOS,
# "xdg-open" su Linux), o servirlo con: python3 -m http.server --directory ../outputs
```

In assenza del primo passaggio: `python3 render_scene.py` (senza
`--spec`) utilizza per impostazione predefinita `data/example_scene_spec.json`,
già incluso nella repository.

Risultato atteso del primo passaggio (confermato su Mac M5 Pro, backend
MPS): un JSON valido contenente 2–3 elementi selezionati in funzione
dell'obiettivo fornito (ad esempio, per un obiettivo relativo al volume
operativo: `robot_kuka` con `highlight: joint_limits` e un
`target_marker` raggiungibile) — la combinazione non è fissa.

## Confronto in CoppeliaSim

Prerequisito: [CoppeliaSim](https://www.coppeliarobotics.com/downloads)
(edizione Edu) installato e in esecuzione, con il server zmqRemoteApi
attivo (per impostazione predefinita disponibile su `localhost:23000`,
senza configurazione aggiuntiva su un'installazione standard).

```bash
python3 -m pip install coppeliasim-zmqremoteapi-client
```

**Confronto visivo** — importa i due URDF affiancati nella scena aperta:

```bash
cd coppelia
python3 compare_in_coppeliasim.py

# per una posa piegata (anziché a riposo/distesa), utile al confronto
# visivo affiancato dei due bracci:
python3 set_demo_pose.py
```

È disponibile anche una variante con le mesh CAD reali del KUKA LWR 4+
al posto delle primitive geometriche, a scopo illustrativo:

```bash
python3 compare_with_meshes.py
```

**Validazione quantitativa in simulazione** (secondo l'indicazione
ricevuta in sede di revisione del progetto: non affidarsi al solo
confronto visivo, ma comandare lo stesso valore ai giunti corrispondenti
dei due robot e misurare — leggendola dall'ambiente di simulazione, non
calcolandola offline — la posa di un piccolo utensile all'estremità di
ciascun braccio, così da validare sia la posizione sia l'orientamento):

```bash
python3 measure_toolpose.py --n-poses 20
```

Lo script reimporta i due robot, aggiunge un dummy "tool tip"
all'estremità di `link_7` di ciascuno e, per un campione di pose
casuali entro i limiti di giunto, comanda gli stessi angoli a entrambi e
confronta la posa del tool tip letta dal motore fisico di CoppeliaSim.
Risultato atteso:

```
Errore posizione:    media 10.00 mm, max 10.00 mm
Errore orientamento: media 0.000°, max 0.000°
```

L'errore di posizione è **costante** su tutte le pose (non solo in
media): è interamente spiegato dall'unico scostamento di lunghezza
(10mm sul giunto 5) propagato lungo la catena cinematica — le rotazioni
a valle preservano il modulo di tale vettore d'errore, che risulta
pertanto indipendente dalla configurazione del braccio. L'errore di
orientamento è nullo in ogni posa poiché i due modelli condividono
esattamente gli stessi angoli α: la topologia angolare estratta è
corretta al 100%, e l'unico errore residuo riguarda la singola
lunghezza di link.

## Limiti dichiarati

Si veda la Parte III del report tecnico per la trattazione completa. In
sintesi: nessun affinamento (fine-tuning) del modello, che resta
pre-addestrato generico; un solo documento tecnico e una sola
esecuzione per il Modulo A; nessuna simulazione fisica completa (solo
confronto cinematico/geometrico); validazione del Modulo B qualitativa,
non essendo disponibile un riferimento noto per una scena didattica.
