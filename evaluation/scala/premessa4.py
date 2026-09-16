#!/usr/bin/env python3
"""
DEMIURGE / F2 — STEP 0 v4: premessa misurata SOLO su linee di quota validate.

v1 misurava l'euristica di appaiamento (un segmento rivendicato da 6 numeri).
v2/v3 saturavano: con ~500 lunghezze distinte ogni numero trova un segmento
(stesso difetto delle 21.731 quaterne, in altra forma).

Qui si riduce drasticamente l'insieme dei candidati tenendo SOLO le coppie
(numero, segmento) in cui il segmento ha DUE linee di estensione perpendicolari
agli estremi — la firma geometrica di una linea di quota vera — e in cui il
segmento non e' conteso da piu' numeri.

Su quelle coppie, e solo su quelle, si guarda se la scala implicata e' costante.
"""
import sys, math, json
import numpy as np
sys.path.insert(0, "/home/claude/grounding")
import quote, re, pymupdf

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


PDF = _pdf_default()
TOLL = 0.01          # 1%


def coppie_validate(path, pagina):
    testi, seg = quote.estrai(path, pagina)
    seg = [s for s in seg if s[4] >= 8.0]
    ris = quote.trova_quote(testi, seg, dist_max=12.0, len_min=12.0)
    grezze = []
    for T, c in ris:
        if not c or c[2] < 2:                     # solo 2 linee di estensione
            continue
        m = re.fullmatch(r"[ØR]?\s*(\d+(?:[.,]\d+)?)\s*°?", T["t"].strip())
        if not m or "°" in T["t"]:
            continue
        v = float(m.group(1).replace(",", "."))
        if not (10 <= v <= 6000):
            continue
        grezze.append((v, c[1], c[0]))
    # scarta i segmenti contesi da piu' numeri: non sappiamo quale sia giusto
    conta = {}
    for v, L, key in grezze:
        conta[key] = conta.get(key, 0) + 1
    return [(v, L, v/L) for v, L, key in grezze if conta[key] == 1]


def gruppi(scale, toll=TOLL):
    """raggruppa le scale implicate in cluster entro toll; ritorna i cluster ordinati"""
    a = np.sort(np.array(scale))
    cl, cur = [], [a[0]]
    for x in a[1:]:
        if x / cur[0] - 1 <= 2 * toll:
            cur.append(x)
        else:
            cl.append(cur); cur = [x]
    cl.append(cur)
    return sorted(cl, key=len, reverse=True)


if __name__ == "__main__":
    pagine = [int(x) for x in sys.argv[1:]] or [10, 12, 24, 42, 60]
    d = pymupdf.open(PDF)
    tot_c = tot_v = 0
    out = []
    print(f"{'pag':>4} {'robot':<12} {'quote validate':>15} {'nel cluster max':>16} "
          f"{'%':>5}  {'scala':>8}  {'2o cluster':>11}")
    print("-" * 80)
    for p in pagine:
        nome_m = re.search(r"MOTOMAN\s+(G[PG]\d+[A-Z\-0-9]*)", d[p-1].get_text())
        cp = coppie_validate(PDF, p-1)
        if len(cp) < 5:
            print(f"{p:>4} {(nome_m.group(1) if nome_m else ''):<12} {len(cp):>15}  (troppo poche)")
            continue
        cl = gruppi([c[2] for c in cp])
        top = cl[0]
        sec = len(cl[1]) if len(cl) > 1 else 0
        frac = len(top) / len(cp)
        tot_c += len(top); tot_v += len(cp)
        nome = nome_m.group(1) if nome_m else f"p{p}"
        print(f"{p:>4} {nome:<12} {len(cp):>15} {len(top):>16} {100*frac:>4.0f}% "
              f"{np.median(top):>9.3f} {sec:>11}")
        out.append(dict(pagina=p, robot=nome, quote_validate=len(cp), cluster_max=len(top),
                        frazione=frac, scala=float(np.median(top)), secondo_cluster=sec,
                        dettaglio=[(v, round(L, 2), round(r, 4)) for v, L, r in sorted(cp, key=lambda x: x[2])]))
    if tot_v:
        print("-" * 80)
        print(f"TOTALE: {tot_c}/{tot_v} quote validate nel cluster dominante della loro pagina "
              f"= {100*tot_c/tot_v:.0f}%")
    json.dump(out, open(str(_QUI / "premessa4.json"), "w"), indent=1)
