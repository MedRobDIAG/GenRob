#!/usr/bin/env python3
"""
DEMIURGE — controllo preliminare della macchina.

Da eseguire PER PRIMO, prima di installare qualunque cosa. Dieci secondi, e ti dice
se la macchina puo' fare il lavoro oppure no. Serve a non scoprire dopo tre ore che
manca la GPU o che non c'e' internet.

    python3 controlla.py

Non richiede nessun pacchetto: usa solo la libreria standard.
"""
import os, sys, shutil, subprocess, json, platform

OK, NO, WARN = "  [ok] ", "  [NO] ", "  [!!] "
esiti = {}


def titolo(t):
    print(f"\n{t}\n" + "-" * len(t))


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return ""


# ---------------------------------------------------------------- GPU
titolo("1. Scheda grafica — il dato che decide tutto")
gpu_info = sh("nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version "
              "--format=csv,noheader,nounits")
if not gpu_info:
    print(NO + "nvidia-smi non risponde: nessuna GPU NVIDIA visibile da questa macchina.")
    print("       Se e' una macchina virtuale, la GPU potrebbe non essere stata")
    print("       resa visibile alla VM (serve il 'GPU passthrough'). Da chiedere.")
    esiti["gpu"] = False
else:
    vram_tot = 0
    for riga in gpu_info.splitlines():
        p = [x.strip() for x in riga.split(",")]
        nome, tot, usata, drv = p[0], int(p[1]), int(p[2]), p[3]
        libera = tot - usata
        vram_tot += libera
        print(f"  {nome}   memoria {tot/1024:.1f} GB totali, {libera/1024:.1f} GB libere   (driver {drv})")
    esiti["gpu"] = True
    esiti["vram_gb"] = vram_tot / 1024
    print()
    if vram_tot / 1024 >= 40:
        print(OK + f"{vram_tot/1024:.0f} GB liberi: basta per l'inferenza a 8 bit e anche per provare un LoRA.")
    elif vram_tot / 1024 >= 20:
        print(OK + f"{vram_tot/1024:.0f} GB liberi: basta per l'inferenza a 8 bit su un modello da 8B.")
    elif vram_tot / 1024 >= 10:
        print(WARN + f"{vram_tot/1024:.0f} GB liberi: si riesce a 4 bit, a 8 bit probabilmente no.")
    else:
        print(NO + f"solo {vram_tot/1024:.1f} GB liberi: troppo poco. Verificare se qualcun altro sta occupando la scheda.")

# ---------------------------------------------------------------- disco
titolo("2. Spazio su disco")
for punto in [os.getcwd(), os.path.expanduser("~"), "/tmp"]:
    try:
        u = shutil.disk_usage(punto)
        print(f"  {punto:<28} {u.free/2**30:6.1f} GB liberi su {u.total/2**30:.0f}")
    except Exception as e:
        print(f"  {punto:<28} non leggibile ({e})")
libero = shutil.disk_usage(os.getcwd()).free / 2**30
esiti["disco_gb"] = libero
print()
print((OK if libero >= 60 else WARN) +
      f"{libero:.0f} GB nella cartella di lavoro. Un modello da 8B pesa 16-20 GB; "
      f"due modelli piu' la cache ne vogliono ~60.")

# ---------------------------------------------------------------- python e pacchetti
titolo("3. Python e pacchetti")
print(f"  python {platform.python_version()}   ({sys.executable})")
esiti["python"] = platform.python_version()
for pk in ["torch", "transformers", "accelerate", "bitsandbytes", "vllm", "PIL", "jsonschema"]:
    try:
        m = __import__(pk)
        v = getattr(m, "__version__", "?")
        print(OK + f"{pk:<14} {v}")
        esiti[pk] = str(v)
        if pk == "torch":
            print(f"       CUDA disponibile da torch: {m.cuda.is_available()}"
                  f"   dispositivi: {m.cuda.device_count() if m.cuda.is_available() else 0}")
            esiti["torch_cuda"] = bool(m.cuda.is_available())
    except Exception:
        print(f"  [--] {pk:<14} assente")
        esiti[pk] = None

# ---------------------------------------------------------------- rete
titolo("4. Accesso a internet — spesso e' qui che si blocca tutto")
import urllib.request
for nome, url in [("HuggingFace", "https://huggingface.co"),
                  ("PyPI", "https://pypi.org/simple/"),
                  ("CDN HuggingFace", "https://cdn-lfs.huggingface.co")]:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "demiurge-check"})
        urllib.request.urlopen(req, timeout=8)
        print(OK + f"{nome} raggiungibile")
        esiti[f"rete_{nome}"] = True
    except Exception as e:
        print(NO + f"{nome} NON raggiungibile — {type(e).__name__}")
        esiti[f"rete_{nome}"] = False
proxy = {k: v for k, v in os.environ.items() if "proxy" in k.lower()}
if proxy:
    print(f"  variabili proxy impostate: {list(proxy)}")

# ---------------------------------------------------------------- code
titolo("5. Gestore di code (SLURM e simili)")
if shutil.which("sinfo") or shutil.which("squeue"):
    print(WARN + "SLURM presente: la macchina e' un cluster a code.")
    print("       I comandi non si lanciano direttamente, vanno messi in coda (srun / sbatch).")
    print(sh("sinfo -o '%P %G %m %l %D' 2>/dev/null")[:600])
    esiti["slurm"] = True
else:
    print(OK + "nessun gestore di code: la macchina sembra usabile direttamente.")
    esiti["slurm"] = False

# ---------------------------------------------------------------- verdetto
titolo("VERDETTO")
if not esiti.get("gpu"):
    print("  Senza GPU visibile non si puo' procedere. Da chiarire prima di ogni altra cosa.")
elif not esiti.get("rete_HuggingFace"):
    print("  GPU presente ma niente internet: i pesi del modello vanno portati a mano")
    print("  (scaricati altrove e copiati). Fattibile, ma va organizzato.")
else:
    print("  La macchina sembra utilizzabile. Passo successivo: installare i pacchetti")
    print("  e fare la prova del fumo con esegui_locale.py --prova")

json.dump(esiti, open("controlla_esito.json", "w"), indent=1)
print("\n(dettagli salvati in controlla_esito.json — mandamelo e ti preparo i comandi esatti)")
