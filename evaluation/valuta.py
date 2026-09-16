#!/usr/bin/env python3
"""
DEMIURGE — scorer della campagna VLM.

Non misura solo "quanto il modello legge bene". Misura le tre cose che secondo
l'architettura decidono la fattibilita' del progetto:

  1. ACCURATEZZA      quanto sono giusti i valori estratti
  2. ASTENSIONE       quando il dato NON c'e', il modello dice null o inventa?
                      (GroundingME: la maggior parte dei modelli e' allo 0% su questo)
  3. COPERTURA        delle estrazioni SBAGLIATE, quante ne intercettano i predicati
                      di validazione del catalogo?
                      <- e' la metrica decisiva: la tesi del progetto e' che il modello
                         puo' sbagliare purche' la matematica se ne accorga.

Uso:  python3 valuta.py risultati/<modello>/<robot>.json [...]
"""
import json, sys, math, yaml, os, collections

_gt = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "ground_truth.yaml")))
GT = dict(_gt.get("livello_A") or {})            # solo il livello A ha verita' esterna
GT_B = dict(_gt.get("livello_B") or {})          # livello B: si osserva il comportamento, non si misura
TOLL_MM = 2.0          # tolleranza sulle lunghezze: le quote sono intere, 2 mm e' generoso
TOLL_DEG = 0.5


# --------------------------------------------------------------------------
# PREDICATI DI VALIDAZIONE  (livello 3 del catalogo delle famiglie)
# Nessuno di questi usa la ground truth: sono verifiche interne al documento.
# --------------------------------------------------------------------------
def pred_schema(est):
    """Coerenza di base: numero di assi, lower < upper."""
    err = []
    lim = est.get("limiti") or {}
    n = est.get("assi_controllati")
    if n and len(lim) and len(lim) != n:
        err.append(f"assi dichiarati {n} ma limiti forniti per {len(lim)}")
    for ax, v in lim.items():
        lo, hi = (v or {}).get("min"), (v or {}).get("max")
        if lo is not None and hi is not None and lo >= hi:
            err.append(f"asse {ax}: min {lo} >= max {hi}")
    return err


def pred_simmetria(est, famiglia="antropomorfo"):
    """
    Firma di simmetria dell'antropomorfo (Decisione 21, RIVISTA il 2026-09-09).
    Assi 1,4,6 attesi simmetrici; assi 2,3 attesi asimmetrici.

    LIMITE DI APPLICABILITA' scoperto sul UR5e: i cobot senza fermi meccanici hanno
    TUTTI gli assi a +/-360, quindi spalla e gomito risultano simmetrici pur essendo
    l'estrazione corretta. Il predicato era stato validato su 28 Yaskawa, tutti
    industriali con fermi. Va quindi disattivato su ogni asse a rotazione continua.
    """
    err = []
    if famiglia != "antropomorfo":
        return ["non applicabile: predicato definito solo per la famiglia antropomorfa"]
    lim = est.get("limiti") or {}
    ordine = list(lim.keys())
    for idx, attesa in [(0, "sim"), (1, "asim"), (2, "asim"), (3, "sim"), (5, "sim")]:
        if idx >= len(ordine):
            continue
        v = lim[ordine[idx]] or {}
        lo, hi = v.get("min"), v.get("max")
        if lo is None or hi is None:
            continue
        if abs(lo) >= 350 and abs(hi) >= 350:      # giunto a rotazione continua
            continue                                # predicato non applicabile
        simm = abs(abs(lo) - abs(hi)) < TOLL_DEG
        if attesa == "sim" and not simm:
            err.append(f"asse {ordine[idx]} atteso simmetrico ma e' {lo}/{hi}")
        if attesa == "asim" and simm:
            err.append(f"asse {ordine[idx]} atteso ASIMMETRICO ma e' {lo}/{hi}")
    return err


def pred_chiusura(est):
    """
    Chiusura sul reach dichiarato. RIVISTO il 2026-09-09 — declassato.

    DUE ragioni per cui questo predicato vale MOLTO MENO di quanto assunto prima:

    (a) POTERE DISCRIMINANTE QUASI NULLO come selettore. Sulla pagina del GP8 ci sono
        73 numeri: 21.731 quaterne soddisfano la formula entro 2 mm. Dimostrazione
        diretta: per il GP7 la geometria (a2=545, avambraccio=340) chiude a 927,3 e
        quella vera (445, 440) chiude a 926,8. Reach dichiarato 927. Non distingue.

    (b) IL PUNTO DI RIFERIMENTO NON E' NOTO. KUKA KR 4 R600 misura il reach al centro
        polso (602,3 calcolato vs 601 dichiarato); KUKA LBR iisy 8 R930 lo misura alla
        flangia (al centro polso sarebbe 753,6 contro 930 dichiarati). Stesso costruttore.

    Resta utile SOLO come rilevatore di errori grossolani, e solo quando applicato a un
    insieme di grandezze NOMINATE prodotto in modo indipendente (una sola ipotesi, non
    ventunmila). Restituisce quale punto di riferimento e' compatibile, se ce n'e' uno.
    """
    g = est.get("geometria") or {}
    val = lambda k: (g.get(k) or {}).get("valore")
    reach = est.get("reach_dichiarato")
    a1, a2, a3, d4, d6 = (val(k) for k in ("a1", "a2", "a3", "d4", "d6"))
    if reach is None:
        return ["non applicabile: reach non dichiarato nel documento"], None
    if a2 is None or a3 is None:
        return ["non applicabile: geometria incompleta"], None

    base = (a1 or 0) + a2 + (math.hypot(a3, d4) if d4 else a3)
    ipotesi = {"centro polso": base}
    if d6:
        ipotesi["flangia"] = base + d6
    ok = {k: abs(v - reach) for k, v in ipotesi.items() if abs(v - reach) <= TOLL_MM}
    if ok:
        k = min(ok, key=ok.get)
        return [], (ok[k], k)
    dett = " | ".join(f"{k}: {v:.1f}" for k, v in ipotesi.items())
    return ([f"nessun punto di riferimento compatibile con reach {reach} ({dett})"], None)


# --------------------------------------------------------------------------
# CONFRONTO CON LA GROUND TRUTH
# --------------------------------------------------------------------------
def confronta(est, gt):
    """
    Quattro esiti per ogni grandezza:
      corretto     GT presente, valore entro tolleranza
      errato       GT presente, valore fuori tolleranza      <- il modello ha sbagliato
      omesso       GT presente, modello ha risposto null     <- prudente ma incompleto
      allucinato   GT ASSENTE,  modello ha dato un numero    <- il caso peggiore
      astenuto     GT assente,  modello ha risposto null     <- comportamento corretto
    """
    out = collections.Counter()
    dettaglio = []
    g_est = est.get("geometria") or {}
    g_gt = gt.get("geometria_mm") or {}
    for k in ["d1", "a1", "a2", "a3", "d4", "d6"]:
        v_gt = g_gt.get(k)
        v_est = (g_est.get(k) or {}).get("valore")
        if v_gt is not None:
            if v_est is None:
                esito = "omesso"
            elif abs(v_est - v_gt) <= TOLL_MM:
                esito = "corretto"
            else:
                esito = "errato"
        else:
            esito = "allucinato" if v_est is not None else "astenuto"
        if k in g_gt or v_est is not None:
            out[esito] += 1
            dettaglio.append((k, v_gt, v_est, esito))
    return out, dettaglio


def valuta_file(path):
    est = json.load(open(path))
    robot = est.get("robot_id") or os.path.basename(path).replace(".json", "")
    gt = GT.get(robot)
    if gt is None:
        if robot in GT_B:
            print("=" * 78)
            print(f"{robot}   [LIVELLO B — nessuna verita' esterna]")
            e_s, e_y, (e_c, _) = pred_schema(est), pred_simmetria(est), pred_chiusura(est)
            g = est.get("geometria") or {}
            dati = sum(1 for k, x in g.items() if (x or {}).get("valore") is not None)
            print(f"  grandezze geometriche dichiarate dal modello: {dati}/6")
            print("  (su questo caso NON si misura accuratezza: si osserva se il modello si astiene o inventa)")
            for nome, errs in [("schema", e_s), ("simmetria", e_y), ("chiusura", e_c)]:
                print(f"    {nome:<11} {'OK' if not errs else '⚠ ' + '; '.join(errs)}")
            return None
        print(f"!! nessuna ground truth per '{robot}'"); return None

    cnt, dett = confronta(est, gt)
    e_schema = pred_schema(est)
    e_simm = pred_simmetria(est)
    e_chius, esito_ch = pred_chiusura(est)
    # "non applicabile" NON e' una segnalazione: il predicato non ha potuto esprimersi.
    # Contarlo come tale gonfiava artificialmente i falsi positivi (difetto trovato il 2026-09-14).
    def _vere(errs):
        return [x for x in errs if not x.startswith("non applicabile")]
    e_schema, e_simm, e_chius = _vere(e_schema), _vere(e_simm), _vere(e_chius)
    predicati_scattati = bool(e_schema or e_simm or e_chius)
    ci_sono_errori = (cnt["errato"] + cnt["allucinato"]) > 0

    print("=" * 78)
    print(f"{robot}   [{gt['costruttore']}]   file: {os.path.basename(path)}")
    print("-" * 78)
    print(f"{'grandezza':<10}{'attesa':>10}{'estratta':>12}   esito")
    for k, a, b, e in dett:
        f = lambda v: "—" if v is None else f"{v:g}"
        print(f"  {k:<8}{f(a):>10}{f(b):>12}   {e}")
    print(f"\n  corretti {cnt['corretto']} | errati {cnt['errato']} | omessi {cnt['omesso']} | "
          f"ALLUCINATI {cnt['allucinato']} | astenuti correttamente {cnt['astenuto']}")

    print("\n  predicati di validazione (nessuno usa la ground truth):")
    for nome, errs in [("schema", e_schema), ("simmetria", e_simm), ("chiusura", e_chius)]:
        if not errs:
            extra = ""
            if nome == "chiusura" and esito_ch:
                extra = f" (compatibile con reach al {esito_ch[1]}, scarto {esito_ch[0]:.1f} mm — POTERE DISCRIMINANTE BASSO)"
            print(f"    {nome:<11} OK{extra}")
        for x in errs:
            print(f"    {nome:<11} ⚠ {x}")

    noti = cnt["corretto"] + cnt["errato"] + cnt["omesso"]
    if noti and cnt["omesso"] == noti:
        print("\n  >> ESITO: il modello non ha valorizzato NESSUNA grandezza nota "
              "(astensione totale: prudente ma inutile)")
    elif ci_sono_errori:
        print(f"\n  >> ESITO: estrazione con errori, "
              f"{'INTERCETTATA dai predicati ✔' if predicati_scattati else 'NON intercettata ✘ (falso negativo)'}")
    else:
        print(f"\n  >> ESITO: estrazione senza errori, "
              f"{'ma i predicati hanno segnalato (falso positivo)' if predicati_scattati else 'predicati puliti ✔'}")
    return dict(robot=robot, cnt=cnt, errori=ci_sono_errori, intercettata=predicati_scattati)


if __name__ == "__main__":
    ris = [r for r in (valuta_file(p) for p in sys.argv[1:]) if r]
    if len(ris) > 1:
        tot = collections.Counter()
        for r in ris:
            tot.update(r["cnt"])
        con_err = [r for r in ris if r["errori"]]
        cop = sum(1 for r in con_err if r["intercettata"])
        print("\n" + "=" * 78)
        print("RIEPILOGO CAMPAGNA")
        print(f"  robot valutati: {len(ris)}")
        n = sum(tot[k] for k in ("corretto", "errato", "omesso"))
        if n:
            print(f"  accuratezza sulle grandezze note: {tot['corretto']}/{n} = {100*tot['corretto']/n:.0f}%")
        na = tot["allucinato"] + tot["astenuto"]
        if na:
            print(f"  ASTENSIONE corretta dove il dato non c'e': {tot['astenuto']}/{na} = "
                  f"{100*tot['astenuto']/na:.0f}%   (allucinazioni: {tot['allucinato']})")
        if con_err:
            print(f"  COPERTURA DEI PREDICATI: {cop}/{len(con_err)} estrazioni errate intercettate "
                  f"= {100*cop/len(con_err):.0f}%")
            print("     ^ e' la metrica decisiva: il modello puo' sbagliare, purche' ce ne accorgiamo")
        else:
            print("  nessuna estrazione errata: copertura dei predicati non misurabile")
