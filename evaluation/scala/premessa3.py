#!/usr/bin/env python3
"""
DEMIURGE / F2 — STEP 0 v3: stessa domanda della v2, calcolo vettorizzato.

  quanti DISTINTI numeri stampati sulla pagina trovano un segmento di lunghezza v/s,
  per la migliore scala s?   (finestra scorrevole moltiplicativa sui rapporti v/L)

Con controllo nullo: numeri finti, stesso intervallo, stessa numerosita', stessi segmenti.
"""
import pymupdf, math, re, sys, json
import numpy as np

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


TOLL = 0.004
N_NULL = 30


def estrai(pg):
    val = []
    for b in pg.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                t = s["text"].strip().replace(",", ".")
                m = re.fullmatch(r"[Ø\-]?\s*(\d{2,4}(?:\.\d)?)", t)
                if m:
                    v = float(m.group(1))
                    if 10 <= v <= 6000:
                        val.append(v)
    segs = set()
    for g in pg.get_drawings():
        for it in g["items"]:
            if it[0] == "l":
                p, q = it[1], it[2]
                a, b_ = (round(p.x, 2), round(p.y, 2)), (round(q.x, 2), round(q.y, 2))
                if a != b_:
                    segs.add((a, b_) if a < b_ else (b_, a))
    L = sorted({round(math.hypot(x1-x0, y1-y0), 2)
                for (x0, y0), (x1, y1) in segs
                if math.hypot(x1-x0, y1-y0) >= 5.0})
    return np.array(sorted(set(val))), np.array(L)


def max_spiegati(valori, L):
    """massimo numero di valori distinti compatibili con una sola scala"""
    if len(valori) < 6 or len(L) < 20:
        return 0, None
    R = (valori[:, None] / L[None, :]).ravel()
    I = np.repeat(np.arange(len(valori)), len(L))
    ok = (R > 0.05) & (R < 100)
    R, I = R[ok], I[ok]
    o = np.argsort(R)
    R, I = R[o], I[o]
    W = (1 + TOLL) / (1 - TOLL)          # larghezza relativa della finestra
    cnt = np.zeros(len(valori), int)
    best, best_s, distinti, j = 0, None, 0, 0
    for i in range(len(R)):
        while j < len(R) and R[j] <= R[i] * W:
            if cnt[I[j]] == 0:
                distinti += 1
            cnt[I[j]] += 1
            j += 1
        if distinti > best:
            best, best_s = distinti, math.sqrt(R[i] * R[j-1])
        cnt[I[i]] -= 1
        if cnt[I[i]] == 0:
            distinti -= 1
    return best, best_s


if __name__ == "__main__":
    pdf = _pdf_default()
    pagine = [int(x) for x in sys.argv[1:]]
    rng = np.random.default_rng(0)
    d = pymupdf.open(pdf)
    out = []
    print(f"{'pag':>4} {'robot':<12} {'num':>4} {'segm':>6} | {'REALE':>6} {'nullo med':>9} "
          f"{'nullo max':>9} | {'eccesso':>8} {'scala':>8}")
    print("-" * 80)
    for p in pagine:
        pg = d[p-1]
        m = re.search(r"MOTOMAN\s+(G[PG]\d+[A-Z\-0-9]*)", pg.get_text())
        valori, L = estrai(pg)
        n_real, s_real = max_spiegati(valori, L)
        lo, hi = valori.min(), valori.max()
        nulli = np.array([max_spiegati(np.array(sorted(set(np.round(rng.uniform(lo, hi, len(valori)))))), L)[0]
                          for _ in range(N_NULL)])
        nome = m.group(1) if m else f"p{p}"
        ecc = n_real - np.median(nulli)
        print(f"{p:>4} {nome:<12} {len(valori):>4} {len(L):>6} | {n_real:>6} "
              f"{np.median(nulli):>9.1f} {nulli.max():>9} | {ecc:>+8.1f} {s_real or 0:>8.3f}")
        out.append(dict(pagina=p, robot=nome, n_valori=int(len(valori)), n_segmenti=int(len(L)),
                        reale=int(n_real), nullo_mediana=float(np.median(nulli)),
                        nullo_max=int(nulli.max()), scala=float(s_real or 0)))
    json.dump(out, open(str(_QUI / "premessa3.json"), "w"), indent=1)
