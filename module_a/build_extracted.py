"""
Modulo A, passo 2/3: dai parametri estratti dal manuale (data/extracted.json)
alla tabella DH e all'URDF. Deterministico -- nessuna AI qui, solo lo script
di assemblaggio che nel report tecnico (S1.9) resta separato dal VLM.

Uso:
    python3 build_extracted.py [--input data/extracted.json] [--out ../outputs]
"""
import argparse
import json
from pathlib import Path

from urdf_builder import dh_table_to_urdf

HERE = Path(__file__).parent
ALPHAS_KNOWN_DEG = [90, -90, -90, 90, 90, -90, 0]  # architettura nota: spalla+gomito+polso


def build_dh_table(link_dimensions_mm, num_joints=7):
    if not link_dimensions_mm or len(link_dimensions_mm) < 2:
        raise ValueError("Servono almeno 2 lunghezze di link estratte (upper arm, forearm)")
    d_upper, d_fore = link_dimensions_mm[0], link_dimensions_mm[1]
    ds = [0, 0, d_upper, 0, d_fore, 0, 0]
    return [
        {"i": i + 1, "alpha_deg": ALPHAS_KNOWN_DEG[i], "a_mm": 0, "d_mm": ds[i]}
        for i in range(num_joints)
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default=str(HERE / "data" / "extracted.json"))
    ap.add_argument("--out", default=str(HERE.parent / "outputs"))
    args = ap.parse_args()

    with open(args.input) as f:
        extracted = json.load(f)

    dh_table = build_dh_table(extracted["link_dimensions_mm"], extracted.get("num_joints") or 7)
    urdf = dh_table_to_urdf(dh_table, extracted.get("joints", []), robot_name="extracted_robot")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "extracted_robot.urdf").write_text(urdf)
    (out_dir / "extracted_dh_table.json").write_text(json.dumps(dh_table, indent=2))

    print(urdf)
    print(f"\nScritto {out_dir / 'extracted_robot.urdf'}")


if __name__ == "__main__":
    main()
