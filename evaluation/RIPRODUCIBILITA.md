# Riprodurre le misure, partendo da un clone

Questa cartella è costruita per essere eseguibile **subito dopo il clone**, senza
file da procurarsi altrove e senza GPU per la parte che conta.

Vale lo stesso principio architetturale della repository: **generativo e
deterministico sono separati**. Un solo script invoca un modello
(`esegui_locale.py`); tutto il resto — punteggio, predicati di validazione,
aggregazione, verifica delle cifre — è codice deterministico che gira su
qualunque elaboratore in pochi secondi.

Ne discendono due livelli di riproduzione, e il primo è quello che stabilisce se
i numeri della relazione sono veri.

---

## Livello 1 — deterministico: ricalcolare le cifre della relazione

Nessuna GPU, nessuna rete, nessun modello da scaricare. Circa **dieci secondi**.

```bash
git clone <url-della-repo>
cd <repo>/evaluation

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements-analisi.txt

./riproduci.sh
```

Lo script fa tre cose:

1. esegue `verifica_numeri.py`, che ricalcola dai risultati versionati **ogni
   cifra citata nella Parte II** e la confronta con il valore dichiarato;
2. stampa il dettaglio per robot della campagna con immagine;
3. stampa il dettaglio della baseline solo testo.

Uscita attesa del primo passaggio:

```
voce                                                ricalcolato    in relazione   esito
---------------------------------------------------------------------------------------
accuratezza, con immagine                            4/20 (20%)            4/20   OK
accuratezza, solo testo                               1/20 (5%)            1/20   OK
grandezze tentate, con immagine                     16/20 (80%)           16/20   OK
grandezze tentate, solo testo                         1/20 (5%)            1/20   OK
astensione dove il dato non c'è                        0/2 (0%)             0/2   OK
auto-coerenza: segnalazioni fondate (precisione)     8/8 (100%)             8/8   OK
auto-coerenza: errori intercettati (richiamo)       8/13 (62%)            8/13   OK
```

`verifica_numeri.py` esce con codice 1 se una qualunque voce diverge. È quindi
utilizzabile come controllo automatico: **se qualcuno modifica i risultati o lo
scorer e le cifre della relazione non tornano più, lo script fallisce.**

I valori dichiarati stanno in un unico dizionario `ATTESI` in cima al file. Se
una misura viene rifatta, va aggiornato lì **e** nella relazione, insieme.

### Una nota di onestà che lo script stampa da solo

In fondo all'uscita compare una sezione *sensibilità alla convenzione di
consolidamento*. Segnala che il risultato sull'auto-coerenza (§5.5) dipende da
**una sola grandezza su otto**: il `d1` del Yaskawa GP7, che nelle tre
ripetizioni vale `[330, 837, 837]` contro un valore atteso di 330.

Consolidando per maggioranza — la convenzione adottata — quella grandezza
risulta errata, e la precisione dell'auto-coerenza è 8/8. Prendendo invece la
prima ripetizione risulta corretta, e la precisione scende a 7/8, il richiamo da
8/13 a 7/12. La convenzione non era dichiarata da nessuna parte: ora lo è, ed è
visibile a chiunque esegua lo script.

---

## Livello 2 — generativo: rilanciare il modello

Richiede una GPU (o molta pazienza su CPU) e circa **17 GB** di scaricamento al
primo avvio, in cache in `~/.cache/huggingface`.

```bash
# torch va installato per la propria piattaforma: vedi requirements-generativo.txt
python3 -m pip install torch --index-url https://download.pytorch.org/whl/cu128
python3 -m pip install -r requirements-generativo.txt

python3 controlla.py               # verifica GPU, spazio su disco, raggiungibilità di HuggingFace
python3 esegui_locale.py --prova   # prova su un solo caso, nulla viene salvato

./riproduci.sh --modello           # campagna completa + baseline, in risultati/riproduzione*/
```

Le pagine di ingresso (`pagine/*.png`) e i livelli di testo (`testo/*.txt`) sono
versionati, quindi il modello riceve **esattamente gli stessi ingressi** della
campagna originale.

### Parametri da non cambiare, se si vuole confrontare

| parametro | valore | perché |
|---|---|---|
| `--max-pixels` | `1229312` | la risoluzione cambia l'accuratezza; confronti a risoluzione diversa non valgono |
| temperatura | 0 (predefinita) | introduce varianza non voluta |
| `prompt_estrazione.md` | invariato | il prompt è parte della misura, non un dettaglio |

### Che cosa aspettarsi

A temperatura nulla l'uscita è **quasi** deterministica, ma non garantita
bit‑per‑bit: versioni diverse di `transformers`, kernel CUDA diversi o una GPU
diversa possono cambiare qualche cifra. Se l'accuratezza complessiva torna a
4/20 e il modo di fallimento è lo stesso (§5.3 — i numeri sciolti della pagina
ABB ridistribuiti fra le grandezze), la riproduzione è riuscita. Se cambia molto,
è un risultato: va confrontata la configurazione, non nascosta la differenza.

Le varianti previste dal runner:

```bash
python3 esegui_locale.py --quant none   --etichetta senza_compressione
python3 esegui_locale.py --quant 8      --etichetta otto_bit
python3 esegui_locale.py --modello qwen32 --quant 4 --etichetta trentadue_miliardi
python3 esegui_locale.py --ripetizioni 3 --etichetta ripetuto
python3 esegui_locale.py --variante solo_testo --etichetta baseline
```

`docs/IN_LABORATORIO.md` è la procedura passo passo per la macchina con GPU da
31,5 GB, comprese le contromisure ai tre errori più probabili.

---

## Livello 3 — Step 0 sulla coerenza di scala

Vedi `scala/README.md`. Gli esiti sono versionati; per rieseguire serve la
brochure Yaskawa GP, che non è versionata perché pesa 64 MB.

---

## Che cosa è versionato, e che cosa no

**Versionato** — tutto ciò che serve a riprodurre:

- `ground_truth.yaml`, il riferimento di misura, con la fonte ufficiale di ogni valore;
- `catalogo_famiglie.yaml`, il catalogo delle famiglie cinematiche;
- `prompt_estrazione.md` e `schema_estrazione.json`, il compito dato al modello;
- `pagine/` e `testo/`, gli ingressi esatti della campagna;
- `risultati/`, tutte le uscite del modello, comprese quelle grezze non valide;
- gli script di esecuzione, punteggio e verifica.

**Non versionato:**

- l'ambiente virtuale e la cache dei modelli (decine di GB, ricostruibili);
- la brochure Yaskawa da 64 MB (pubblica sul sito del costruttore);
- i risultati di riesecuzione (`risultati/riproduzione*/`), per non sovrascrivere
  il riferimento.

La repository è **privata**. Le pagine in `pagine/` sono riproduzioni di schede
tecniche dei costruttori: conservarle per la verifica dei risultati rientra
nell'eccezione di ricerca (artt. 70-*ter* e 70-*quater* L. 633/1941), ma la
**ridistribuzione no**. Se la repository venisse resa pubblica, `pagine/` e
`testo/` vanno rimossi dalla cronologia prima, non solo dall'ultimo commit.
