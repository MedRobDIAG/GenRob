#!/usr/bin/env python3
"""
DEMIURGE — runner LOCALE della campagna VLM.

Gemello di esegui.py (che parla con OpenRouter via HTTP): stessi prompt, stesso schema,
stesse varianti, stessi nomi di file in uscita. Cambia solo COME si raggiunge il modello:
qui gira sulla macchina, non dietro un'API.

Tre differenze sostanziali rispetto alla versione via API, tutte volute:

  1. QUANTIZZAZIONE esplicita (--quant 4 / 8 / none). E' una variabile sperimentale,
     non un dettaglio: la compressione aggressiva degrada proprio il riconoscimento di
     cifre piccole a basso contrasto, che e' il nostro compito.
  2. RISOLUZIONE esplicita (--max-pixels). Stessa ragione: tutto il compito consiste nel
     leggere numeri piccoli su un disegno, quindi la risoluzione va misurata, non subita.
  3. JSON non garantito. L'API imponeva lo schema lato server; qui, senza vLLM, il modello
     puo' produrre testo non valido. Il runner tenta una riparazione e, se fallisce, REGISTRA
     IL FALLIMENTO invece di nasconderlo: "non ha prodotto JSON valido" e' un risultato.

Uso tipico:
    python3 esegui_locale.py --prova                      # prova del fumo, un solo caso
    python3 esegui_locale.py --quant 8                    # campagna completa a 8 bit
    python3 esegui_locale.py --quant 4                    # e a 4 bit, per il confronto
    python3 esegui_locale.py --quant 8 --ripetizioni 3    # auto-coerenza
    python3 esegui_locale.py --variante solo_testo        # baseline senza immagine
    python3 esegui_locale.py --dry-run                    # verifica l'impalcatura senza modello

I risultati vanno in risultati/<etichetta>/<robot>.json e si valutano con valuta.py.
Le misure di consumo (tempo, VRAM di picco) vanno in risultati/<etichetta>/_metriche.json.
"""
import os, sys, json, argparse, pathlib, re, time, traceback

BASE = pathlib.Path(__file__).parent

ROBOT = ["yaskawa_gp8", "yaskawa_gp7", "kuka_iisy8_R930", "kuka_kr4_R600",
         "abb_irb6400pe", "fanuc_r2000i", "comau_smarts2"]

MODELLI = {
    "qwen8":   "Qwen/Qwen3-VL-8B-Instruct",
    "qwen32":  "Qwen/Qwen3-VL-32B-Instruct",
    "molmo":   "allenai/Molmo-2-8B",
}


# ==========================================================================
# prompt e schema — unica copia, condivisa con la versione via API
# ==========================================================================
def prompt_parts():
    md = (BASE / "prompt_estrazione.md").read_text()
    blocchi = re.findall(r"```\n(.*?)\n```", md, re.S)
    if len(blocchi) < 2:
        sys.exit("prompt_estrazione.md: non trovo i due blocchi SYSTEM e USER")
    return blocchi[0].strip(), blocchi[1].strip()


def schema():
    return json.loads((BASE / "schema_estrazione.json").read_text())


def testo_pagina(robot_id):
    p = BASE / "testo" / f"{robot_id}.txt"
    t = p.read_text() if p.exists() else ""
    return t if t.strip() else "(livello di testo non disponibile: documento scansionato)"


# ==========================================================================
# riparazione del JSON — senza decoding guidato il modello puo' sbagliare formato
# ==========================================================================
def estrai_json(testo):
    """Ritorna (oggetto, motivo_fallimento). Non solleva eccezioni."""
    if not testo or not testo.strip():
        return None, "risposta vuota"
    t = testo.strip()
    # 1. recinti markdown
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    # 2. tentativo diretto
    try:
        return json.loads(t), None
    except Exception:
        pass
    # 3. primo oggetto bilanciato
    inizio = t.find("{")
    if inizio < 0:
        return None, "nessun oggetto JSON nella risposta"
    prof, in_str, esc = 0, False, False
    for i in range(inizio, len(t)):
        c = t[i]
        if in_str:
            if esc:            esc = False
            elif c == "\\":    esc = True
            elif c == '"':     in_str = False
            continue
        if c == '"':           in_str = True
        elif c == "{":         prof += 1
        elif c == "}":
            prof -= 1
            if prof == 0:
                try:
                    return json.loads(t[inizio:i + 1]), None
                except Exception as e:
                    return None, f"oggetto bilanciato ma non valido: {e}"
    return None, "oggetto JSON non chiuso (risposta troncata?)"


# ==========================================================================
# NORMALIZZAZIONE — il modello non sempre rispetta lo schema
# ==========================================================================
# Osservato sul campo (Colab, T4, Qwen3-VL-8B a 4 bit, 2026-09-15): il modello ha
# restituito JSON valido ma con le chiavi "PARTE_1..PARTE_4", cioe' i TITOLI DELLE
# SEZIONI della richiesta, invece delle chiavi dello schema. Senza il decoding guidato
# dell'API nessuno glielo impedisce.
#
# Qui si rimappano le deviazioni note e si CONTA quante riparazioni sono servite:
# "il modello ha rispettato lo schema da solo" e' esso stesso una misura, e va nel report.
# Non si correggono MAI errori di contenuto (per esempio min/max invertiti): quelli
# devono restare visibili, e li intercetta il predicato di schema dello scorer.

ALIAS = {
    "identificazione": ["parte_1", "parte1", "identification", "identificazione_robot", "robot"],
    "limiti":          ["parte_2", "parte2", "joint_limits", "limiti_giunto", "limiti_di_giunto",
                        "campo_di_movimentazione", "range"],
    "geometria":       ["parte_3", "parte3", "geometry", "grandezze", "dimensioni"],
    "reach_dichiarato":["parte_4", "parte4", "reach", "raggio_massimo", "raggio_azione"],
}
ALIAS_ID = {"modello": ["nome_modello", "nome", "model"], "costruttore": ["produttore", "manufacturer", "brand"]}


def _num(x):
    """'+170' -> 170.0 ; '330 mm' -> 330.0 ; None resta None. Non altera il segno."""
    if x is None or isinstance(x, (int, float)):
        return x
    if isinstance(x, str):
        m = re.search(r"[-+]?\d+(?:[.,]\d+)?", x.replace(",", "."))
        if m:
            try:
                return float(m.group(0))
            except Exception:
                return None
        return None
    return None


def normalizza(o):
    """Ritorna (oggetto_normalizzato, elenco_riparazioni)."""
    if not isinstance(o, dict):
        return o, ["risposta non e' un oggetto"]
    rip = []
    basso = {k.lower(): k for k in o}

    for canonico, varianti in ALIAS.items():
        if canonico in o:
            continue
        for v in varianti:
            if v in basso:
                o[canonico] = o.pop(basso[v])
                rip.append(f"chiave '{basso[v]}' rinominata in '{canonico}'")
                break

    # assi_controllati puo' essere finito dentro identificazione
    ident = o.get("identificazione")
    if isinstance(ident, dict):
        for c, varianti in ALIAS_ID.items():
            if c not in ident:
                for v in varianti:
                    if v in ident:
                        ident[c] = ident.pop(v); rip.append(f"identificazione.{v} -> {c}"); break
        for k in ("assi_controllati", "assi", "numero_assi"):
            if k in ident and o.get("assi_controllati") is None:
                o["assi_controllati"] = ident.pop(k); rip.append(f"assi_controllati estratto da identificazione")
    o["assi_controllati"] = _num(o.get("assi_controllati"))
    if isinstance(o["assi_controllati"], float):
        o["assi_controllati"] = int(o["assi_controllati"])

    # limiti: numeri come numeri
    lim = o.get("limiti")
    if isinstance(lim, dict):
        for asse, v in list(lim.items()):
            if not isinstance(v, dict):
                lim.pop(asse); rip.append(f"limite '{asse}' scartato: non e' un oggetto"); continue
            for campo in ("min", "max", "ampiezza"):
                prima = v.get(campo)
                dopo = _num(prima)
                if isinstance(prima, str) and dopo is not None:
                    rip.append(f"limiti.{asse}.{campo}: stringa '{prima}' convertita in numero")
                v[campo] = dopo
            v.setdefault("unita", "deg")

    # geometria: il modello a volte mette il numero nudo invece dell'oggetto
    geo = o.get("geometria")
    if isinstance(geo, dict):
        for k in list(geo):
            if k not in ("d1", "a1", "a2", "a3", "d4", "d6"):
                geo.pop(k); continue
            v = geo[k]
            if v is None or isinstance(v, (int, float, str)):
                geo[k] = {"valore": _num(v), "unita": "mm", "source": None,
                          "confidenza": None, "nota": "struttura ricostruita in fase di normalizzazione"}
                rip.append(f"geometria.{k}: valore nudo incapsulato nella struttura attesa")
            elif isinstance(v, dict):
                prima = v.get("valore")
                v["valore"] = _num(prima)
                if isinstance(prima, str) and v["valore"] is not None:
                    rip.append(f"geometria.{k}.valore: stringa '{prima}' convertita in numero")
        for k in ("d1", "a1", "a2", "a3", "d6"):
            geo.setdefault(k, {"valore": None, "unita": None, "source": None,
                               "confidenza": None, "nota": "assente dalla risposta del modello"})

    r = o.get("reach_dichiarato")
    if isinstance(r, dict):                      # a volte incapsulato
        for k in ("valore", "raggio_massimo", "reach"):
            if k in r:
                o["reach_dichiarato"] = r[k]; rip.append("reach estratto da oggetto annidato"); break
        else:
            o["reach_dichiarato"] = None
    o["reach_dichiarato"] = _num(o.get("reach_dichiarato"))

    return o, rip


# ==========================================================================
# backend: transformers (predefinito, stabile) oppure vLLM (piu' veloce, con schema forzato)
# ==========================================================================
class BackendHF:
    nome = "transformers"

    def __init__(self, model_id, quant, max_pixels, dtype=None):
        import torch
        from transformers import AutoProcessor, BitsAndBytesConfig
        self.torch = torch

        # Scelta del formato numerico in base alla GPU.
        # bfloat16 esiste solo da Ampere in poi (capability >= 8.0). Le T4 del Colab
        # gratuito sono Turing (7.5): chiedere bfloat16 lì fa fallire il caricamento o
        # lo rende lentissimo. Su quelle schede si usa float16.
        if torch.cuda.is_available():
            cap = torch.cuda.get_device_capability(0)
            bf16_ok = cap[0] >= 8
            calcolo = torch.bfloat16 if bf16_ok else torch.float16
            print(f"  GPU capability {cap[0]}.{cap[1]} -> uso {'bfloat16' if bf16_ok else 'float16'}")
        else:
            calcolo = torch.float32
            print("  nessuna GPU: si procede su CPU (sarà lentissimo)")
        if dtype is None:
            dtype = calcolo

        kw = {"device_map": "auto", "dtype": dtype}
        if quant in (4, 8):
            try:
                if quant == 4:
                    kw["quantization_config"] = BitsAndBytesConfig(
                        load_in_4bit=True, bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=calcolo,
                        bnb_4bit_use_double_quant=True)
                else:
                    kw["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
            except Exception as e:
                sys.exit(f"Quantizzazione a {quant} bit non disponibile ({e}). "
                         f"Serve il pacchetto bitsandbytes: pip install bitsandbytes")

        self.proc = AutoProcessor.from_pretrained(model_id, trust_remote_code=True,
                                                  max_pixels=max_pixels)
        modello = None
        ultimi = []
        for classe in ("AutoModelForImageTextToText", "AutoModelForVision2Seq", "AutoModelForCausalLM"):
            try:
                import transformers
                C = getattr(transformers, classe)
                modello = C.from_pretrained(model_id, trust_remote_code=True, **kw)
                self.classe = classe
                break
            except Exception as e:
                ultimi.append(f"{classe}: {type(e).__name__}: {e}")
        if modello is None:
            sys.exit("Nessuna classe di transformers ha caricato il modello:\n  " + "\n  ".join(ultimi))
        self.m = modello.eval()

    def genera(self, system, user, img_path, temperatura, max_new=2048):
        from PIL import Image
        contenuto = []
        if img_path:
            contenuto.append({"type": "image", "image": Image.open(img_path).convert("RGB")})
        contenuto.append({"type": "text", "text": user})
        msg = [{"role": "system", "content": [{"type": "text", "text": system}]},
               {"role": "user", "content": contenuto}]
        inputs = self.proc.apply_chat_template(
            msg, add_generation_prompt=True, tokenize=True,
            return_dict=True, return_tensors="pt").to(self.m.device)
        gen = dict(max_new_tokens=max_new)
        if temperatura and temperatura > 0:
            gen.update(do_sample=True, temperature=temperatura, top_p=0.9)
        else:
            gen.update(do_sample=False)
        with self.torch.inference_mode():
            out = self.m.generate(**inputs, **gen)
        nuovi = out[0][inputs["input_ids"].shape[1]:]
        return self.proc.decode(nuovi, skip_special_tokens=True)


class BackendVLLM:
    nome = "vllm"

    def __init__(self, model_id, quant, max_pixels, dtype="auto"):
        from vllm import LLM
        kw = dict(model=model_id, trust_remote_code=True, dtype=dtype,
                  limit_mm_per_prompt={"image": 1},
                  mm_processor_kwargs={"max_pixels": max_pixels})
        if quant == 4:
            kw["quantization"] = "bitsandbytes"
        elif quant == 8:
            kw["quantization"] = "bitsandbytes"
        self.llm = LLM(**kw)
        from transformers import AutoProcessor
        self.proc = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        self.schema = schema()

    def genera(self, system, user, img_path, temperatura, max_new=2048):
        from PIL import Image
        from vllm import SamplingParams
        try:
            from vllm.sampling_params import GuidedDecodingParams
            guided = GuidedDecodingParams(json=self.schema)
        except Exception:
            guided = None
        contenuto = ([{"type": "image"}] if img_path else []) + [{"type": "text", "text": user}]
        msg = [{"role": "system", "content": system}, {"role": "user", "content": contenuto}]
        testo = self.proc.apply_chat_template(msg, add_generation_prompt=True, tokenize=False)
        req = {"prompt": testo}
        if img_path:
            req["multi_modal_data"] = {"image": Image.open(img_path).convert("RGB")}
        sp = SamplingParams(temperature=temperatura or 0.0, max_tokens=max_new,
                            **({"guided_decoding": guided} if guided else {}))
        out = self.llm.generate([req], sp)
        return out[0].outputs[0].text


class BackendFinto:
    """--dry-run: verifica prompt, percorsi, salvataggi e scorer senza caricare nulla."""
    nome = "finto"

    def __init__(self, *a, **k):
        pass

    def genera(self, system, user, img_path, temperatura, max_new=2048):
        rid = re.search(r"robot_id da riportare nella risposta: (\S+)", user)
        rid = rid.group(1) if rid else "sconosciuto"
        return json.dumps({
            "robot_id": rid,
            "identificazione": {"modello": None, "costruttore": None},
            "assi_controllati": 6,
            "limiti": {},
            "geometria": {k: {"valore": None, "unita": "mm", "source": None,
                              "confidenza": 0.0, "nota": "dry-run: nessun modello caricato"}
                          for k in ("d1", "a1", "a2", "a3", "d6")},
            "reach_dichiarato": None,
            "note": "dry-run",
        }, ensure_ascii=False)


# ==========================================================================
def vram_picco(torch_mod):
    try:
        return max(torch_mod.cuda.max_memory_allocated(i) for i in range(torch_mod.cuda.device_count())) / 2**30
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Campagna VLM in locale")
    ap.add_argument("--modello", default="qwen8", help="chiave di MODELLI oppure percorso/id HuggingFace")
    ap.add_argument("--backend", default="hf", choices=["hf", "vllm", "finto"])
    ap.add_argument("--quant", default="8", choices=["4", "8", "none"])
    ap.add_argument("--max-pixels", type=int, default=1568 * 28 * 28,
                    help="risoluzione massima dell'immagine in pixel: e' una variabile sperimentale")
    ap.add_argument("--robot", nargs="*", default=ROBOT)
    ap.add_argument("--variante", default="base", choices=["base", "solo_testo", "senza_lista"])
    ap.add_argument("--ripetizioni", type=int, default=1)
    ap.add_argument("--temperatura", type=float, default=None)
    ap.add_argument("--max-new", type=int, default=2048, help="token massimi in risposta")
    ap.add_argument("--etichetta", default=None, help="nome della cartella dei risultati")
    ap.add_argument("--prova", action="store_true", help="prova del fumo: un solo robot, nessun salvataggio")
    ap.add_argument("--dry-run", action="store_true", help="verifica l'impalcatura senza caricare il modello")
    a = ap.parse_args()

    if a.dry_run:
        a.backend = "finto"
    if a.prova:
        a.robot = ["yaskawa_gp8"]
        a.ripetizioni = 1

    model_id = MODELLI.get(a.modello, a.modello)
    quant = None if a.quant == "none" else int(a.quant)
    temperatura = a.temperatura if a.temperatura is not None else (0.0 if a.ripetizioni == 1 else 0.7)
    etichetta = a.etichetta or f"{a.modello}_{a.quant}bit_{a.variante}"

    system, user_base = prompt_parts()
    if a.variante == "senza_lista":
        user_base = ("Questa è la scheda tecnica di un braccio robotico industriale. "
                     "Estrai le quote geometriche dal disegno e i limiti di giunto, in JSON.")

    print(f"modello    {model_id}")
    print(f"backend    {a.backend}   quantizzazione {a.quant} bit   max_pixels {a.max_pixels}")
    print(f"variante   {a.variante}   ripetizioni {a.ripetizioni}   temperatura {temperatura}")
    print(f"risultati  risultati/{etichetta}/\n")

    t0 = time.time()
    Backend = {"hf": BackendHF, "vllm": BackendVLLM, "finto": BackendFinto}[a.backend]
    try:
        bk = Backend(model_id, quant, a.max_pixels)
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit("\nCaricamento del modello fallito. Se e' un problema di memoria prova --quant 4; "
                 "se manca il pacchetto, installalo e rilancia. Niente e' stato scritto.")
    print(f"modello caricato in {time.time()-t0:.0f}s\n")

    metriche, dest_dir = [], BASE / "risultati" / etichetta
    for rid in a.robot:
        img = None
        if a.variante != "solo_testo":
            p = BASE / "pagine" / f"{rid}.png"
            if p.exists():
                img = p
            else:
                print(f"  !! manca l'immagine {p.name}, salto")
                continue
        u = user_base + f"\n\nrobot_id da riportare nella risposta: {rid}"
        if img is None:
            u += "\n\nLIVELLO DI TESTO DEL DOCUMENTO:\n" + testo_pagina(rid)

        for k in range(a.ripetizioni):
            sfx = "" if a.ripetizioni == 1 else f"_r{k+1}"
            dest = dest_dir / f"{rid}{sfx}.json"
            if dest.exists() and not a.prova:
                print(f"  salto {dest.name} (già presente)")
                continue
            try:
                import torch
                torch.cuda.reset_peak_memory_stats()
            except Exception:
                torch = None
            t1 = time.time()
            try:
                grezzo = bk.genera(system, u, img, temperatura, a.max_new)
            except Exception as e:
                print(f"  ERRORE {rid}{sfx}: {type(e).__name__}: {e}")
                metriche.append(dict(robot=rid, ripetizione=k + 1, errore=f"{type(e).__name__}: {e}"))
                continue
            dt = time.time() - t1
            obj, motivo = estrai_json(grezzo)
            riparazioni = []
            if obj is not None:
                obj, riparazioni = normalizza(obj)
            pic = vram_picco(torch) if torch is not None else None

            if a.prova:
                if riparazioni:
                    print(f"  ATTENZIONE: {len(riparazioni)} riparazioni di struttura necessarie:")
                    for r in riparazioni[:8]:
                        print("    -", r)
                print("--- risposta grezza del modello ---")
                print(grezzo[:1500])
                print("-----------------------------------")
                print(f"JSON valido: {'sì' if obj else 'NO — ' + motivo}")
                print(f"tempo {dt:.1f}s" + (f"   VRAM di picco {pic:.1f} GB" if pic else ""))
                return

            dest.parent.mkdir(parents=True, exist_ok=True)
            if obj is None:
                (dest.with_suffix(".raw.txt")).write_text(grezzo)
                print(f"  {rid}{sfx:<4} JSON NON VALIDO ({motivo}) — risposta salvata in .raw.txt")
            else:
                obj.setdefault("robot_id", rid)
                if riparazioni:
                    obj["_riparazioni"] = riparazioni
                dest.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
                n = sum(1 for v in (obj.get("geometria") or {}).values()
                        if isinstance(v, dict) and v.get("valore") is not None)
                marchio = "ok  " if not riparazioni else f"ok(r{len(riparazioni)})"
                print(f"  {rid}{sfx:<4} {marchio} {dt:5.1f}s   grandezze valorizzate {n}/6"
                      + (f"   VRAM {pic:.1f} GB" if pic else ""))
            metriche.append(dict(robot=rid, ripetizione=k + 1, secondi=round(dt, 2),
                                 vram_picco_gb=round(pic, 2) if pic else None,
                                 json_valido=obj is not None, motivo=motivo,
                                 riparazioni=len(riparazioni), schema_rispettato=not riparazioni))

    if metriche:
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "_metriche.json").write_text(json.dumps(
            dict(modello=model_id, backend=bk.nome, quant=a.quant, max_pixels=a.max_pixels,
                 variante=a.variante, temperatura=temperatura, casi=metriche), indent=1))
        validi = sum(1 for m in metriche if m.get("json_valido"))
        puliti = sum(1 for m in metriche if m.get("schema_rispettato"))
        tempi = [m["secondi"] for m in metriche if m.get("secondi")]
        vram = [m["vram_picco_gb"] for m in metriche if m.get("vram_picco_gb")]
        print(f"\nfatti {len(metriche)} casi · JSON valido {validi}/{len(metriche)}"
              + f" · schema rispettato senza riparazioni {puliti}/{len(metriche)}"
              + (f" · tempo mediano {sorted(tempi)[len(tempi)//2]:.1f}s" if tempi else "")
              + (f" · VRAM di picco {max(vram):.1f} GB" if vram else ""))
        print(f"valuta con:  python3 valuta.py risultati/{etichetta}/*.json")


if __name__ == "__main__":
    main()
