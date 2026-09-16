#!/usr/bin/env python3
"""
DEMIURGE / F2 — STEP 0, versione 2: misura della premessa SENZA appaiamento.

Il test v1 misurava l'euristica di appaiamento, non il disegno (un segmento veniva
rivendicato da sei numeri diversi). Questa versione elimina l'appaiamento.

DOMANDA POSTA ALLA PAGINA:
  esiste una scala s tale che MOLTI dei numeri stampati v trovino un segmento
  di lunghezza L ~ v/s, con assegnazione UNO A UNO (un segmento serve un solo numero)?

Non si chiede QUALE segmento: solo se ne esiste uno. Il problema di grounding
resta irrisolto, ma la premessa diventa misurabile.

CONTROLLO NULLO — indispensabile, perche' con molti segmenti qualunque scala
spiega qualcosa: si ripete la procedura con numeri FINTI, estratti a caso dallo
stesso intervallo dei numeri veri. La differenza fra reale e nullo e' il segnale.
Senza questo controllo il test si auto-conferma, che e' l'errore gia' commesso
con la firma di simmetria.
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


TOLL = 0.004          # 0,4% — una quota disegnata bene sta molto dentro questo
N_NULL = 40           # ripetizioni del modello nullo


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
    return np.array(val), np.array(L)


def spiegati(valori, L, s):
    """quanti valori trovano un segmento a lunghezza v/s, assegnazione uno-a-uno"""
    usati = np.zeros(len(L), bool)
    n = 0
    for v in np.sort(valori)[::-1]:          # dai piu' grandi (piu' selettivi)
        tgt = v/s
        ok = (~usati) & (np.abs(L/tgt - 1.0) <= TOLL)
        if ok.any():
            usati[np.argmax(ok)] = True
            n += 1
    return n


def analizza(valori, L, rng=None):
    """miglior scala e numero di valori spiegati; candidate = tutti i rapporti v/L"""
    if len(valori) < 8 or len(L) < 20:
        return 0, None
    cand = np.unique(np.round((valori[:, None] / L[None, :]).ravel(), 4))
    cand = cand[(cand > 0.05) & (cand < 100)]
    if len(cand) > 40000:
        cand = rng.choice(cand, 40000, replace=False) if rng is not None else cand[::len(cand)//40000+1]
    best_n, best_s = 0, None
    for s in cand:
        n = spiegati(valori, L, s)
        if n > best_n:
            best_n, best_s = n, s
    return best_n, best_s


if __name__ == "__main__":
    pdf = _pdf_default()
    pagine = [int(x) for x in sys.argv[1:]] or [10, 12, 24, 42, 60]
    rng = np.random.default_rng(0)
    d = pymupdf.open(pdf)
    out = []
    print(f"{'pag':>4} {'robot':<12} {'num':>4} {'segm':>6} {'REALE':>7} {'NULLO med':>10} {'NULLO max':>10} {'scala':>8}")
    print("-"*68)
    for p in pagine:
        pg = d[p-1]
        m = re.search(r"MOTOMAN\s+(G[PG]\d+[A-Z\-0-9]*)", pg.get_text())
        valori, L = estrai(pg)
        n_real, s_real = analizza(valori, L, rng)
        # --- modello nullo: numeri finti nello stesso intervallo, stessa numerosita' ---
        nulli = []
        lo, hi = valori.min(), valori.max()
        for _ in range(N_NULL):
            fake = np.round(rng.uniform(lo, hi, len(valori)))
            nulli.append(analizza(fake, L, rng)[0])
        nulli = np.array(nulli)
        nome = m.group(1) if m else f"p{p}"
        print(f"{p:>4} {nome:<12} {len(valori):>4} {len(L):>6} {n_real:>7} "
              f"{np.median(nulli):>10.1f} {nulli.max():>10} {s_real if s_real else 0:>8.3f}")
        out.append(dict(pagina=p, robot=nome, n_valori=int(len(valori)), n_segmenti=int(len(L)),
                        spiegati_reale=int(n_real), nullo_mediana=float(np.median(nulli)),
                        nullo_max=int(nulli.max()), scala=float(s_real or 0)))
    json.dump(out, open(str(_QUI / "premessa2.json"), "w"), indent=1)
