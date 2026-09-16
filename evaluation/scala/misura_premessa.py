#!/usr/bin/env python3
"""
DEMIURGE / F2 — STEP 0: misura della PREMESSA della coerenza di scala.

Domanda: i disegni delle schede tecniche rispettano davvero le proporzioni?
Non si assume: si stima.

Metodo, per ogni pagina:
  1. si estraggono i numeri (testo) con posizione e direzione
  2. si estraggono i segmenti rettilinei (grafica vettoriale)
  3. ogni numero viene appaiato al segmento PARALLELO alla sua direzione piu' vicino
     (e' l'euristica della linea di quota: nei disegni il testo e' ruotato per seguirla)
  4. per ogni coppia si calcola la SCALA IMPLICATA  s = valore_dichiarato / lunghezza_disegnata
  5. si istogramma log(s): se la pagina e' in scala, le coppie corrette si accumulano
     su un picco stretto; gli appaiamenti sbagliati si disperdono.

L'ALTEZZA e la LARGHEZZA del picco sono la misura cercata.
Nessuna ground truth esterna: si usano solo i numeri stampati sul disegno stesso.
"""
import pymupdf, math, re, sys, json
import numpy as np
from collections import defaultdict

# --- percorsi risolti rispetto a questo file, non assoluti ---------------------
import pathlib as _pl
_QUI = _pl.Path(__file__).resolve().parent
def _pdf_default():
    """Brochure Yaskawa GP: non versionata (64 MB). Vedi scala/README.md."""
    import os, sys
    for a in sys.argv[1:]:
        if a.lower().endswith(".pdf"):
            return a
    p = os.environ.get("YASKAWA_PDF")
    if p:
        return p
    return str(_QUI / "documenti" / "Yas_GP_Serie_Gesamt_E.pdf")


MIN_LEN_PT = 6.0        # segmenti piu' corti non sono linee di quota
MAX_DIST_PT = 16.0      # distanza massima testo -> linea di quota
TOLL_REL = 0.01         # 1%: due scale entro l'1% sono "la stessa scala"


def carica(pg):
    """numeri con posizione/direzione, e segmenti rettilinei deduplicati"""
    numeri = []
    for b in pg.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                t = s["text"].strip().replace(",", ".")
                m = re.fullmatch(r"[Ø\-]?\s*(\d{2,4}(?:\.\d)?)", t)
                if not m:
                    continue
                v = float(m.group(1))
                if not (10 <= v <= 6000):        # fuori range per una quota in mm
                    continue
                x0, y0, x1, y1 = s["bbox"]
                numeri.append(dict(v=v, cx=(x0+x1)/2, cy=(y0+y1)/2, dir=l["dir"]))

    segs = set()
    for g in pg.get_drawings():
        for it in g["items"]:
            if it[0] == "l":
                p, q = it[1], it[2]
                a, b_ = (round(p.x, 1), round(p.y, 1)), (round(q.x, 1), round(q.y, 1))
                if a != b_:
                    segs.add((a, b_) if a < b_ else (b_, a))
    S = []
    for (x0, y0), (x1, y1) in segs:
        L = math.hypot(x1-x0, y1-y0)
        if L >= MIN_LEN_PT:
            S.append((x0, y0, x1, y1, L))
    return numeri, np.array(S) if S else np.zeros((0, 5))


def appaia(numeri, S):
    """ogni numero -> segmento parallelo alla direzione del testo, piu' vicino"""
    if len(S) == 0:
        return []
    x0, y0, x1, y1, L = S[:, 0], S[:, 1], S[:, 2], S[:, 3], S[:, 4]
    sx, sy = (x1-x0)/L, (y1-y0)/L
    mx, my = (x0+x1)/2, (y0+y1)/2
    out = []
    for n in numeri:
        dx, dy = n["dir"]
        par = np.abs(sx*dx + sy*dy) > 0.985             # parallelo entro ~10 gradi
        if not par.any():
            continue
        # distanza punto-segmento (approssimata col punto piu' vicino fra estremi e centro)
        d = np.minimum.reduce([np.hypot(x0-n["cx"], y0-n["cy"]),
                               np.hypot(x1-n["cx"], y1-n["cy"]),
                               np.hypot(mx-n["cx"], my-n["cy"])])
        d = np.where(par, d, np.inf)
        vicini = d <= MAX_DIST_PT
        if not vicini.any():
            continue
        cand = np.where(vicini)[0]
        i = cand[np.argmax(L[cand])]                    # fra i vicini, il piu' lungo
        out.append((n["v"], float(L[i]), n["v"]/float(L[i])))
    return out


def picco(scale):
    """
    Trova il picco dominante nella distribuzione delle scale implicate.
    Ritorna (scala_modale, frazione_di_coppie_entro_TOLL_REL, n_totale).
    """
    if len(scale) < 8:
        return None
    a = np.sort(np.array(scale))
    best_c, best_s = 0, None
    for s in a:                                        # ogni valore come centro candidato
        c = int(np.sum(np.abs(a/s - 1.0) <= TOLL_REL))
        if c > best_c:
            best_c, best_s = c, s
    dentro = a[np.abs(a/best_s - 1.0) <= TOLL_REL]
    return float(np.median(dentro)), best_c/len(a), len(a), float(np.std(dentro)/np.mean(dentro))


if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else _pdf_default()
    d = pymupdf.open(pdf)
    righe = []
    print(f"{'pag':>4} {'robot':<18} {'coppie':>7} {'scala 1:':>9} {'nel picco':>10} {'disp.':>7}")
    print("-" * 62)
    for i, pg in enumerate(d):
        testo = pg.get_text()
        m = re.search(r"MOTOMAN\s+(G[PG]\d+[A-Z\-0-9]*)", testo)
        if not m or pg.get_text().count("\n") < 5:
            continue
        numeri, S = carica(pg)
        if len(numeri) < 10 or len(S) < 50:
            continue
        cp = appaia(numeri, S)
        p = picco([c[2] for c in cp])
        if not p:
            continue
        s, frac, n, disp = p
        nome = m.group(1)
        print(f"{i+1:>4} {nome:<18} {n:>7} {s:>9.3f} {100*frac:>9.0f}% {100*disp:>6.2f}%")
        righe.append(dict(pagina=i+1, robot=nome, coppie=n, scala=s,
                          frazione_picco=frac, dispersione_interna=disp))
    json.dump(righe, open(str(_QUI / "premessa_yaskawa.json"), "w"), indent=1)
    if righe:
        f = [r["frazione_picco"] for r in righe]
        print("-" * 62)
        print(f"pagine misurate: {len(righe)}   frazione nel picco: "
              f"mediana {100*np.median(f):.0f}%  min {100*min(f):.0f}%  max {100*max(f):.0f}%")
