# evaluation — banco di misura del Modulo A

Questa cartella contiene il **banco di misura** dell'estrazione di parametri
cinematici da documentazione tecnica: la parte di ricerca che sta a monte di
`module_a/`. Non fa parte della pipeline di generazione — serve a stabilire
**quanto bene** l'estrazione funziona, con numeri riproducibili invece che con
un confronto visivo.


Vale qui lo stesso principio della repository: un solo script invoca un modello
generativo (`esegui_locale.py`); punteggio, predicati di validazione e
aggregazione sono codice deterministico, eseguibile ovunque senza GPU.

**Per riprodurre le misure partendo da un clone: [`RIPRODUCIBILITA.md`](RIPRODUCIBILITA.md).**
In sintesi:

```bash
python3 -m pip install -r requirements-analisi.txt
./riproduci.sh
```

Dieci secondi, nessuna GPU, e ogni cifra della Parte II della relazione viene
ricalcolata dai risultati versionati e confrontata con il valore dichiarato.

---

## Esiti principali

| | |
|---|---|
| accuratezza, modello 8B a 4 bit, con immagine | 4/20 (20%) |
| baseline solo testo | 1/20 (5%) |
| grandezze tentate, con immagine contro solo testo | 16/20 contro 1/20 |
| astensione dove il dato non c'è | 0 casi su 2 |
| collaudo dei predicati sui valori ufficiali | 3 estrazioni corrette su 5 respinte |
| auto-coerenza, precisione / richiamo | 8/8 e 8/13 |
| risorse | 8,6 GB di memoria video, ~72 s per documento |

Il campione è piccolo e ottimisticamente distorto: i robot con descrizione
pubblica sono anche i meglio documentati. I limiti sono dichiarati per esteso
nella relazione. Il risultato sull'auto-coerenza dipende da una sola grandezza
su otto — `verifica_numeri.py` lo segnala da solo.

---

## Contenuto

```
ground_truth.yaml         riferimento di misura: 5 robot ancorati a URDF ufficiali
                          (KUKA KR 4 R600 e LBR iisy 8 R930, Yaskawa GP7 e GP8,
                          ABB IRB 6400PE) piu' 2 casi solo comportamentali.
                          20 grandezze misurabili. Ogni valore riporta la fonte.
catalogo_famiglie.yaml    5 famiglie cinematiche su 3 livelli: firma di
                          riconoscimento, tabella DH parametrica, predicati

prompt_estrazione.md      il compito dato al modello, identico per tutti i modelli
schema_estrazione.json    schema JSON della risposta attesa

controlla.py              verifica preliminare della macchina (GPU, disco, rete)
esegui_locale.py          [GPU] esecuzione della campagna
valuta.py                 scorer: corretta / errata / omessa / allucinata /
                          correttamente astenuta, tolleranza 2 mm; applica anche
                          i predicati di validazione, che non usano la ground truth
verifica_numeri.py        ricalcola le cifre della relazione dai risultati versionati
riproduci.sh              punto di ingresso unico

pagine/                   le pagine date in pasto al modello (7 documenti)
testo/                    i livelli di testo estratti dai PDF, per la baseline

risultati/
  qwen8_4bit_base/          campagna con immagine
  qwen8_4bit_solo_testo/    baseline senza immagine, stesse 20 grandezze
  qwen8_4bit_ripetuto/      3 ripetizioni, 2 robot — primo esito auto-coerenza
  ripetuto_5robot/          3 ripetizioni, 5 robot — replica: non regge
  _oracolo/                 collaudo dei predicati sui valori ufficiali

scala/                    Step 0: misura della fedelta' metrica dei disegni
                          (vedi scala/README.md)
docs/
  IN_LABORATORIO.md       procedura per la campagna su GPU non compressa
```

## Note di lettura

**Il riferimento di misura non è una lettura dei disegni.** Le grandezze del
livello A sono ricavate per composizione cinematica dagli URDF ufficiali
pubblicati dai costruttori o da ROS-Industrial, e ogni fonte è validata
verificando che i limiti di giunto della descrizione coincidano con quelli della
scheda tecnica. Una versione precedente, basata su letture manuali «verificate»
con un controllo interno, si era rivelata corretta per metà.

**I predicati di validazione non usano la ground truth.** Sono controlli interni
al documento; `_oracolo/` contiene il loro collaudo, cioè cosa succede quando si
danno loro in pasto i valori ufficiali. Tre estrazioni corrette su cinque
vengono respinte: è uno dei risultati negativi della relazione, ed è
riproducibile.

**Le risposte grezze non valide sono conservate** accanto ai risultati, nei file
`.raw.txt`. Non sono un guasto, sono dati.
