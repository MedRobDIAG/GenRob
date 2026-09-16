#!/usr/bin/env python3
"""
Ricalcola, dai risultati versionati in risultati/, tutte le cifre citate nella
relazione, e le confronta con i valori dichiarati.

Non richiede GPU ne' rete ne' il modello: legge solo i JSON gia' presenti nella
repository. E' la verifica che chiunque cloni puo' eseguire in pochi secondi.

    python3 verifica_numeri.py

Uscita: per ogni voce, il valore RICALCOLATO e quello DICHIARATO nella relazione,
con OK se coincidono. Codice di uscita 1 se almeno una voce diverge.
"""
import io, os, sys, json, glob, math, contextlib, collections, pathlib

QUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(QUI))
import valuta  # riusa lo scorer: nessuna logica di punteggio duplicata qui

RIS = QUI / "risultati"

# Valori dichiarati nella relazione (Parte II). Se una misura viene rifatta e
# cambia, va cambiata QUI e nella relazione insieme.
ATTESI = {
    "accuratezza_con_immagine":   (4, 20),
    "accuratezza_solo_testo":     (1, 20),
    "tentate_con_immagine":       (16, 20),
    "tentate_solo_testo":         (1, 20),
    "astensione_corretta":        (0, 2),
    "autocoerenza_segnalazioni_fondate": (8, 8),
    "autocoerenza_errori_intercettati":  (8, 13),
}

righe = []      # (etichetta, ricalcolato_str, atteso_str, ok)
SENSIBILI = []  # grandezze il cui esito dipende dalla convenzione di consolidamento


def _zitto(fn, *a, **k):
    """esegue fn silenziando lo stdout dello scorer"""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def carica_serie(nome):
    """i file .json di una serie, esclusi _metriche e le ripetizioni _rN"""
    d = RIS / nome
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        b = p.name
        if b.startswith("_"):
            continue
        if b[:-5].rsplit("_", 1)[-1].startswith("r") and b[:-5].rsplit("_", 1)[-1][1:].isdigit():
            continue
        out.append(p)
    return out


def conta_serie(nome):
    """somma i conteggi dello scorer su una serie; restituisce anche i dettagli"""
    tot = collections.Counter()
    dettagli = []
    for p in carica_serie(nome):
        r = _zitto(valuta.valuta_file, str(p))
        if r:
            tot.update(r["cnt"])
            dettagli.append(r)
    return tot, dettagli


def confronta(chiave, etichetta, num, den):
    a_num, a_den = ATTESI[chiave]
    ok = (num == a_num and den == a_den)
    pct = f"{100*num/den:.0f}%" if den else "—"
    righe.append((etichetta,
                  f"{num}/{den} ({pct})",
                  f"{a_num}/{a_den}",
                  ok))


# ---------------------------------------------------------------- accuratezza
print("lettura di risultati/ ...\n")

tot_img, det_img = conta_serie("qwen8_4bit_base")
tot_txt, det_txt = conta_serie("qwen8_4bit_solo_testo")

def noti(t):
    return t["corretto"] + t["errato"] + t["omesso"]

def tentate(t):
    return t["corretto"] + t["errato"]

confronta("accuratezza_con_immagine", "accuratezza, con immagine",
          tot_img["corretto"], noti(tot_img))
confronta("accuratezza_solo_testo", "accuratezza, solo testo",
          tot_txt["corretto"], noti(tot_txt))
confronta("tentate_con_immagine", "grandezze tentate, con immagine",
          tentate(tot_img), noti(tot_img))
confronta("tentate_solo_testo", "grandezze tentate, solo testo",
          tentate(tot_txt), noti(tot_txt))

ast = tot_img["astenuto"]
ast_den = tot_img["astenuto"] + tot_img["allucinato"]
confronta("astensione_corretta", "astensione dove il dato non c'e'", ast, ast_den)


# ------------------------------------------------------ auto-coerenza (§5.5)
# Per ogni grandezza con 3 ripetizioni: le risposte concordano o divergono?
# E il valore e' corretto rispetto alla ground truth?
def autocoerenza(nome):
    d = RIS / nome
    per_robot = collections.defaultdict(dict)
    for p in sorted(d.glob("*.json")):
        b = p.name[:-5]
        if b.startswith("_"):
            continue
        base, _, suff = b.rpartition("_")
        if not (suff.startswith("r") and suff[1:].isdigit()):
            continue
        per_robot[base][int(suff[1:])] = json.load(open(p))

    concordi_corretti = concordi_tot = discordi_corretti = discordi_tot = 0
    for robot, reps in per_robot.items():
        gt = valuta.GT.get(robot)
        if gt is None or len(reps) < 2:
            continue
        atteso = gt.get("geometria_mm") or {}
        for k in ["d1", "a1", "a2", "a3", "d4", "d6"]:
            v_gt = atteso.get(k)
            if v_gt is None:
                continue
            vals = []
            for r in reps.values():
                g = (r.get("geometria") or {}).get(k) or {}
                vals.append(g.get("valore"))
            if all(v is None for v in vals):
                continue
            concorde = len({v for v in vals}) == 1
            # Valore consolidato di una grandezza discorde: la MAGGIORANZA delle
            # ripetizioni. In assenza di maggioranza stretta il valore resta
            # indeterminato e non puo' essere corretto. La convenzione va
            # dichiarata perche' su questo campione cambia una cifra: vedi
            # la nota di sensibilita' stampata in fondo.
            cnt = collections.Counter(v for v in vals if v is not None)
            magg = None
            if cnt:
                (val, n), = cnt.most_common(1)
                if n > len(vals) / 2:
                    magg = val
            corretto = (magg is not None and abs(magg - v_gt) <= valuta.TOLL_MM)
            prima = vals[0]
            corretto_prima = (prima is not None and abs(prima - v_gt) <= valuta.TOLL_MM)
            if concorde:
                concordi_tot += 1
                concordi_corretti += corretto
            else:
                discordi_tot += 1
                discordi_corretti += corretto
                if corretto_prima != corretto:
                    SENSIBILI.append((robot, k, vals, v_gt))
    return concordi_corretti, concordi_tot, discordi_corretti, discordi_tot


cc, ct, dc, dt = autocoerenza("ripetuto_5robot")
# segnalazione = grandezza discorde. Fondata = quella grandezza e' davvero errata.
fondate = dt - dc
errori_totali = (ct - cc) + (dt - dc)
confronta("autocoerenza_segnalazioni_fondate",
          "auto-coerenza: segnalazioni fondate (precisione)", fondate, dt)
confronta("autocoerenza_errori_intercettati",
          "auto-coerenza: errori intercettati (richiamo)", fondate, errori_totali)


# ------------------------------------------------------------------- stampa
L = max(len(r[0]) for r in righe) + 2
print(f"{'voce':<{L}}{'ricalcolato':>20}{'in relazione':>16}   esito")
print("-" * (L + 44))
divergenze = 0
for et, ric, att, ok in righe:
    if not ok:
        divergenze += 1
    print(f"{et:<{L}}{ric:>20}{att:>16}   {'OK' if ok else 'DIVERGE'}")

print()
print(f"concordanza fra ripetizioni (5 robot): concordi {cc}/{ct} corretti, "
      f"discordi {dc}/{dt} corretti")
print(f"serie lette: qwen8_4bit_base ({len(det_img)} casi), "
      f"qwen8_4bit_solo_testo ({len(det_txt)} casi), ripetuto_5robot")

if SENSIBILI:
    print("\nSENSIBILITA' ALLA CONVENZIONE DI CONSOLIDAMENTO")
    print("  Le grandezze qui sotto risultano corrette o errate a seconda che si")
    print("  prenda la maggioranza delle ripetizioni (convenzione adottata) oppure")
    print("  la prima. Con la convenzione 'prima ripetizione' la precisione")
    print("  dell'auto-coerenza scende da 8/8 a 7/8 e il richiamo da 8/13 a 7/12.")
    for robot, k, vals, v_gt in SENSIBILI:
        print(f"    {robot} {k}: ripetizioni {vals}, atteso {v_gt}")
    print("  Il risultato del §5.5 dipende quindi da UNA grandezza su otto.")

if divergenze:
    print(f"\n!! {divergenze} voci divergono dai valori dichiarati nella relazione.")
    sys.exit(1)
print("\nTutte le cifre della Parte II sono riprodotte dai risultati versionati.")
