"""
Modulo A, passo 1/3: estrazione generativa dei parametri dal manuale tecnico
(PDF) con un VLM open-weight (Qwen3-VL). Unico passaggio con AI generativa
del Modulo A -- tutto cio' che segue (build_extracted.py) e' deterministico.

Gira su GPU NVIDIA (CUDA, con quantizzazione 4-bit via bitsandbytes), su Mac
Apple Silicon (backend MPS di PyTorch, senza quantizzazione: bitsandbytes e'
CUDA-only) o su CPU (lento). Il device viene rilevato automaticamente. Il
resto della pipeline (build_extracted.py, build_reference.py, validate.py,
coppelia/) non dipende da questo script: data/extracted.json contiene gia'
l'output di un run precedente, cosi' il resto della repo resta riproducibile
anche senza rieseguirlo.

Uso:
    python3 extract_from_manual.py --pdf manuale.pdf --pages 12 13 14 --drawing-page 14 \
        --out data/extracted.json
"""
import argparse
import gc
import json
import re
from pathlib import Path

import fitz  # PyMuPDF -- non richiede il binario di sistema poppler (a differenza di pdf2image)
import torch
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

MODEL_ID = "Qwen/Qwen3-VL-4B-Instruct"


def pick_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def pdf_to_images(pdf_path, dpi=150):
    doc = fitz.open(pdf_path)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    images = []
    for page in doc:
        pix = page.get_pixmap(matrix=matrix)
        images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    return images


PROMPT_SPECS = """Leggi la tabella tecnica in queste pagine. Rispondi SOLO con JSON, nessun altro testo:
{"robot_name": string o null, "num_joints": intero o null, "payload_kg": numero o null,
 "reach_mm": numero o null, "mass_kg": numero o null, "repeatability_mm": numero o null,
 "joints": [{"index": intero, "range_deg": numero o null, "velocity_deg_s": numero o null, "torque_Nm": numero o null}]}
Non indovinare: se un campo non è nel documento, usa null."""

PROMPT_DRAWING = """Questa immagine è un disegno tecnico quotato del braccio robotico (vista laterale con quote in mm).
Leggi le quote verticali che rappresentano le lunghezze dei due segmenti del braccio (dalla spalla al gomito, dal gomito al polso).
Rispondi SOLO con JSON: {"link_dimensions_mm": [numero, numero]} — i due valori in mm nell'ordine spalla->gomito, gomito->polso.
Se non riesci a leggerli con certezza, usa null al posto dell'array."""


def load_model(device):
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    if device == "cuda":
        from transformers import BitsAndBytesConfig
        bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            MODEL_ID, quantization_config=bnb_config, device_map="auto"
        )
    else:
        # MPS/CPU: bitsandbytes non e' disponibile (CUDA-only), niente quantizzazione.
        # bfloat16 su MPS: supportato dalle build recenti di PyTorch/macOS; se il tuo
        # ambiente da' problemi, prova float16.
        dtype = torch.bfloat16 if device == "mps" else torch.float32
        model = Qwen3VLForConditionalGeneration.from_pretrained(MODEL_ID, dtype=dtype).to(device)
    return processor, model


def extract_with_qwen(processor, model, images, prompt, max_new_tokens=500):
    from qwen_vl_utils import process_vision_info

    messages = [{
        "role": "user",
        "content": [{"type": "image", "image": img} for img in images] + [{"type": "text", "text": prompt}],
    }]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(text=[text], images=image_inputs, videos=video_inputs, padding=True,
                        return_tensors="pt").to(model.device)
    with torch.no_grad():
        generated = model.generate(**inputs, max_new_tokens=max_new_tokens)
    out = processor.batch_decode(
        [o[len(i):] for i, o in zip(inputs.input_ids, generated)], skip_special_tokens=True
    )[0]
    del inputs, generated
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    elif torch.backends.mps.is_available():
        torch.mps.empty_cache()
    gc.collect()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True, help="Manuale tecnico in PDF")
    ap.add_argument("--pages", type=int, nargs="+", required=True,
                     help="Indici (0-based) delle pagine con la tabella specifiche")
    ap.add_argument("--drawing-page", type=int, required=True,
                     help="Indice (0-based) della pagina col disegno quotato")
    ap.add_argument("--out", default="data/extracted.json")
    args = ap.parse_args()

    device = pick_device()
    print(f"Device: {device}")
    if device == "cpu":
        print("ATTENZIONE: nessuna GPU rilevata (ne' CUDA ne' MPS). Sara' molto lento.")

    pages = pdf_to_images(args.pdf, dpi=150)
    processor, model = load_model(device)

    out1 = extract_with_qwen(processor, model, [pages[i] for i in args.pages], PROMPT_SPECS)
    print(out1)
    result_1 = json.loads(re.search(r"\{.*\}", out1, re.S).group(0))

    out2 = extract_with_qwen(processor, model, [pages[args.drawing_page]], PROMPT_DRAWING,
                              max_new_tokens=200)
    print(out2)
    result_2 = json.loads(re.search(r"\{.*\}", out2, re.S).group(0))

    extracted = {**result_1, **result_2, "extra_constraints": []}
    if not extracted.get("link_dimensions_mm") or None in extracted["link_dimensions_mm"]:
        print("\nATTENZIONE: il VLM non ha letto le quote dal disegno con sicurezza "
              "sufficiente (null). Inserisci link_dimensions_mm manualmente nel JSON "
              "di output prima di passare a build_extracted.py.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(extracted, indent=2))
    print(f"\nScritto {out_path}")


if __name__ == "__main__":
    main()
