"""
Modulo B, passo 1/2: l'agente decide la composizione della scena a partire
da un obiettivo di apprendimento in testo libero. Unico passaggio con AI
generativa del Modulo B -- render_scene.py, a valle, e' deterministico.

Gira su GPU NVIDIA (CUDA), su Mac Apple Silicon (backend MPS di PyTorch) o su
CPU (lento) -- il device viene rilevato automaticamente. Su una macchina
senza GPU, usa direttamente data/example_scene_spec.json con render_scene.py
per vedere il risultato del render senza rieseguire il modello.

Uso:
    python3 generate_scene.py --objective "Spiega le tappe del ciclo di Krebs..." \
        --out data/scene_spec.json
"""
import argparse
import json
import re
from pathlib import Path

import torch
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration, BitsAndBytesConfig

MODEL_ID = "Qwen/Qwen3-VL-4B-Instruct"


def pick_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


PROMPT_HEADER = """Sei il modulo di composizione scena di un sistema di training immersivo (DEMIURGE). Dato un obiettivo di apprendimento in testo libero, scegli come comporre uno scenario didattico usando SOLO i seguenti elementi deterministici disponibili (non puoi inventarne altri):

- robot_kuka {"highlight": "joint_limits" | "reach_envelope" | "none"} — un braccio robotico chirurgico a 7 gradi di libertà già modellato
- target_marker {"label": string, "reachable_hint": "reachable" | "unreachable" | "unknown"} — un punto bersaglio nello spazio
- tissue_block {"label": string} — un blocco di tessuto/fantoccio anatomico semplificato
- biochem_diagram {"style": "ciclo" | "catena", "count": intero 4-12, "highlight_index": intero o null, "labels": array di stringhe brevi lunghe quanto count} — schema illustrativo di un ciclo metabolico o di una catena molecolare
- label_card {"text": string} — un cartellino di testo fluttuante nella scena

Rispondi SOLO con un oggetto JSON con questo schema esatto, nessun altro testo:
{
  "domain": "chirurgico" | "biochimico",
  "title": "string breve",
  "rationale": "1-2 frasi che spiega perché hai scelto questi elementi per QUESTO obiettivo",
  "environment": "sala_operatoria" | "laboratorio" | "neutro",
  "camera": "frontale" | "dall_alto" | "laterale",
  "elements": [ {"type": "...", ...} ],
  "annotations": ["...", "..."]
}

Scegli gli elementi e i parametri in modo specifico per l'obiettivo dato — non riusare sempre la stessa combinazione."""

ALLOWED_TYPES = {"robot_kuka", "target_marker", "tissue_block", "biochem_diagram", "label_card"}


def sanitize_spec(raw):
    spec = {
        "domain": raw.get("domain") if raw.get("domain") in ("chirurgico", "biochimico") else "chirurgico",
        "title": str(raw.get("title") or "Scenario"),
        "rationale": str(raw.get("rationale") or ""),
        "environment": raw.get("environment") if raw.get("environment") in (
            "sala_operatoria", "laboratorio", "neutro") else "neutro",
        "camera": raw.get("camera") if raw.get("camera") in ("frontale", "dall_alto", "laterale") else "frontale",
        "elements": [e for e in (raw.get("elements") or []) if isinstance(e, dict) and e.get("type") in ALLOWED_TYPES][:5],
        "annotations": [str(a) for a in (raw.get("annotations") or [])][:3],
    }
    if not spec["elements"]:
        spec["elements"] = [{"type": "label_card", "text": "(nessun elemento valido restituito)"}]
    return spec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--objective", required=True)
    ap.add_argument("--domain-hint", default="auto", choices=["auto", "chirurgico", "biochimico"])
    ap.add_argument("--out", default="data/scene_spec.json")
    args = ap.parse_args()

    device = pick_device()
    print(f"Device: {device}")
    if device == "cpu":
        print("ATTENZIONE: nessuna GPU rilevata (ne' CUDA ne' MPS). Sara' molto lento. "
              "Considera data/example_scene_spec.json + render_scene.py per vedere il "
              "render senza rieseguire il modello.")

    dtype = torch.bfloat16 if device in ("cuda", "mps") else torch.float32
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = Qwen3VLForConditionalGeneration.from_pretrained(MODEL_ID, dtype=dtype).to(device)

    user_prompt = PROMPT_HEADER + "\n\nObiettivo di apprendimento:\n" + args.objective
    if args.domain_hint != "auto":
        user_prompt += f'\n\n(Il dominio è specificato dall\'utente: {args.domain_hint}. Usa "domain": "{args.domain_hint}".)'

    messages = [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], padding=True, return_tensors="pt").to(model.device)
    with torch.no_grad():
        generated = model.generate(**inputs, max_new_tokens=600)
    output_text = processor.batch_decode(
        [o[len(i):] for i, o in zip(inputs.input_ids, generated)], skip_special_tokens=True
    )[0]
    print(output_text)

    match = re.search(r"\{.*\}", output_text, re.S)
    raw_spec = json.loads(match.group(0))
    scene_spec = sanitize_spec(raw_spec)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scene_spec, indent=2, ensure_ascii=False))
    print(f"\nScritto {out_path}")


if __name__ == "__main__":
    main()
