# Prompt di estrazione — campagna VLM DEMIURGE

Derivato dal campo `numeri_da_cercare_nel_documento` del catalogo delle famiglie (livello 2).
Attua la **Decisione 19** (lista chiusa di grandezze nominate, non "leggi il disegno") e il
**RISCHIO 5** (i modelli non si astengono: l'astensione va resa esplicita, facile e premiata).

Identico per tutti i modelli della campagna. Non va adattato per modello: il confronto deve essere
a parità di prompt.

---

## SYSTEM

```
Sei un assistente specializzato nella lettura di schede tecniche di robot industriali.
Estrai SOLO grandezze che puoi effettivamente vedere nel documento.

REGOLA FONDAMENTALE: se una grandezza non è presente, o se non sei sicuro di quale
elemento del disegno una quota stia misurando, restituisci null e spiega perché nel
campo "nota". Restituire null è la risposta CORRETTA quando il dato non c'è.
Un valore inventato o attribuito alla grandezza sbagliata è un errore grave;
un null è un risultato utile.

Rispondi esclusivamente con un oggetto JSON conforme allo schema richiesto.
Nessun testo prima o dopo.
```

## USER

```
Questa è la scheda tecnica di un braccio robotico industriale.

PARTE 1 — Identificazione
  Nome/modello del robot, costruttore, numero di assi controllati.

PARTE 2 — Limiti di giunto
  Per ogni asse, il campo di movimentazione: valore minimo e massimo, con l'unità.
  Attenzione: alcuni costruttori dichiarano solo l'ampiezza totale invece degli estremi.
  In quel caso metti "ampiezza" e lascia min/max a null.

PARTE 3 — Geometria (dal disegno quotato)
  Cerco ESATTAMENTE queste cinque grandezze, e nessun'altra. Sono distanze fra assi
  di rotazione, e stanno nel disegno dell'area di lavoro in vista laterale.

  d1  altezza dell'ASSE 2 (spalla) sopra il piano di appoggio della base
  a1  scostamento ORIZZONTALE dell'asse 2 rispetto all'asse 1 (l'asse verticale di base).
      Vale 0 se i due assi si intersecano. Spesso NON è quotato: in quel caso null.
  a2  distanza fra l'ASSE 2 (spalla) e l'ASSE 3 (gomito)
  a3  distanza fra l'ASSE 3 (gomito) e il CENTRO DEL POLSO
  d6  distanza fra il CENTRO DEL POLSO e la FLANGIA di attacco utensile

  Per OGNI valore indica anche dove l'hai letto (source): il testo esatto della quota
  come appare nel documento, e in che punto della pagina si trova.

PARTE 4 — Verifica dichiarata
  Il raggio d'azione massimo (reach) dichiarato dal costruttore, se presente.

Non dedurre valori per differenza o per somma da altri valori: riporta solo ciò che
è quotato esplicitamente. Se una quota è ambigua, null e spiega l'ambiguità.

FORMATO DELLA RISPOSTA — usa ESATTAMENTE queste chiavi, senza rinominarle e senza
aggiungerne. NON usare "PARTE_1", "PARTE_2" ecc. come chiavi: quelle sono solo i titoli
delle sezioni di questa richiesta.

{
  "robot_id": "<come fornito nella richiesta>",
  "identificazione": { "modello": "...", "costruttore": "..." },
  "assi_controllati": 6,
  "limiti": {
    "<nome dell'asse come lo chiama il documento>": {
      "min": -170, "max": 170, "ampiezza": null, "unita": "deg"
    }
  },
  "geometria": {
    "d1": { "valore": 330, "unita": "mm",
            "source": { "testo_quota": "330", "posizione": "vista laterale, in basso a sinistra" },
            "confidenza": 0.9, "nota": null },
    "a1": { "valore": null, "unita": null, "source": null, "confidenza": 0.0,
            "nota": "non quotato nel disegno" },
    "a2": { ... }, "a3": { ... }, "d6": { ... }
  },
  "reach_dichiarato": 727,
  "note": null
}

REGOLE SUI NUMERI, da rispettare alla lettera:
- i valori numerici vanno come NUMERI, mai come stringhe: 330 e non "330", -170 e non "-170";
- `min` e `max` sono gli ESTREMI CON SEGNO. Se il documento scrive ±170, allora
  min = -170 e max = +170. Se scrive +145/-65, allora min = -65 e max = +145;
- `min` deve sempre essere minore di `max`;
- il reach dichiarato va cercato anche nella TABELLA delle specifiche, non solo nel disegno.
```

---

## Note di progettazione

**Perché le grandezze sono nominate e non "le quote".** §8.4: il livello di testo dei PDF vettoriali
restituisce un insieme di numeri privo di ancoraggio. Chiedere "leggi le quote" produce esattamente
l'errore di §11.1 — un numero plausibile agganciato alla grandezza sbagliata.

**Perché il null è richiesto esplicitamente e dichiarato "corretto".** GroundingME: la maggior parte
dei modelli totalizza **0%** sui task di rifiuto. L'astensione va resa non solo permessa ma
*desiderabile*, altrimenti il modello riempie i campi comunque.

**Perché si chiede la provenienza (`source`).** Serve a distinguere due errori diversi: aver letto male
un numero, e aver letto bene un numero attribuendolo alla grandezza sbagliata. Il secondo è il fallimento
di grounding, ed è quello che ci interessa misurare. Senza `source` i due casi sono indistinguibili.

**Perché si vieta la deduzione.** Se il modello calcola `a3 = reach − a2` invece di leggerlo, la
chiusura numerica torna per costruzione e il nostro test di validazione perde ogni potere diagnostico.

## Varianti da eseguire

| Variante | Cosa misura |
|---|---|
| `base` | il prompt qui sopra, sull'immagine di pagina |
| `solo_testo` | stesso prompt, ma al modello si passa **solo il livello di testo estratto**, senza immagine. **Baseline obbligatoria**: se i risultati sono equivalenti, il canale visivo non serve e l'intera tesi del progetto va rivista |
| `senza_lista` | "estrai le quote geometriche dal disegno", senza la lista di grandezze nominate. Misura quanto vale la Decisione 19 |
| `ripetuto` | il prompt `base` eseguito 3 volte a temperatura > 0. Misura l'auto-coerenza: il disaccordo fra ripetizioni è un segnale di incertezza gratuito |
