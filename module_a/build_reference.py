"""
Costruzione dell'URDF di riferimento (ground truth) per la validazione del
Modulo A, a partire dallo xacro pubblico del KUKA LWR 4+
(github.com/CentroEPiaggio/kuka-lwr). Deterministico: parsing XML + la stessa
geometria a primitive di build_extracted.py, non le mesh STL originali (che
richiederebbero il pacchetto xacro/ROS completo).

Nota metodologica importante: gli offset z grezzi tra giunti consecutivi nel
xacro NON sono direttamente parametri DH -- includono geometria strutturale
(pedestal, alloggiamenti dei giunti) che va raggruppata secondo la
convenzione standard usata in letteratura per il KUKA LWR4+/iiwa (paper Gaz,
Flacco, De Luca -- vedi bibliografia del report), che assume un'architettura
spalla+gomito+polso con un solo offset non nullo tra spalla e gomito (d3) e
uno tra gomito e polso (d5), esattamente la stessa struttura assunta da
build_extracted.py. Raggruppando i 7 offset grezzi dello xacro (spalla+base,
gomito1+gomito2, polso1+polso2, flangia) si ottiene infatti d3=400mm e
d5=390mm -- i valori standard noti in letteratura, e la stessa grandezza che
il Modulo A prova a leggere dal disegno quotato.

Uso:
    python3 build_reference.py [--xacro data/kuka_lwr.urdf.xacro] [--out ../outputs]

Se data/kuka_lwr.urdf.xacro non esiste, lo scarica da GitHub.
"""
import argparse
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from urdf_builder import dh_table_to_urdf

HERE = Path(__file__).parent
REFERENCE_URDF_URL = (
    "https://raw.githubusercontent.com/CentroEPiaggio/kuka-lwr/master/"
    "lwr_description/model/kuka_lwr.urdf.xacro"
)
ALPHAS_KNOWN_DEG = [90, -90, -90, 90, 90, -90, 0]


def fetch_or_load_xacro(path: Path) -> str:
    if path.exists():
        return path.read_text()
    print(f"{path} non trovato, scarico da {REFERENCE_URDF_URL} ...")
    xacro = urllib.request.urlopen(REFERENCE_URDF_URL, timeout=15).read().decode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xacro)
    return xacro


def parse_joint_z_offsets(xacro_text: str):
    root = ET.fromstring(xacro_text)
    offsets_m, names = [], []
    for joint in root.iter("joint"):
        name = joint.attrib.get("name", "")
        if "base_joint" in name:
            continue  # giunto fisso che attacca il robot al mondo, escluso
        origin = joint.find("origin")
        if origin is not None and "xyz" in origin.attrib:
            xyz = origin.attrib["xyz"].split()
            if len(xyz) == 3:
                try:
                    offsets_m.append(float(xyz[2]))
                    names.append(name)
                except ValueError:
                    pass
    return offsets_m, names


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xacro", default=str(HERE / "data" / "kuka_lwr.urdf.xacro"))
    ap.add_argument("--out", default=str(HERE.parent / "outputs"))
    args = ap.parse_args()

    xacro_text = fetch_or_load_xacro(Path(args.xacro))
    offsets_m, names = parse_joint_z_offsets(xacro_text)
    print("Giunti trovati (offset grezzi dallo xacro):", names)
    print("Offset z grezzi (m):", offsets_m)

    if len(offsets_m) < 7:
        raise SystemExit(f"Attesi 7 offset di giunto, trovati {len(offsets_m)} — xacro inatteso.")

    # Raggruppamento nella convenzione DH standard (vedi docstring): spalla+base
    # (esclusa dal confronto, non e' un link del braccio), gomito1+gomito2 -> d3,
    # polso1+polso2 -> d5, flangia (esclusa dal confronto).
    d3_m = offsets_m[2] + offsets_m[3]
    d5_m = offsets_m[4] + offsets_m[5]
    print(f"Raggruppati: d3 (spalla->gomito) = {d3_m * 1000:.1f} mm, "
          f"d5 (gomito->polso) = {d5_m * 1000:.1f} mm")

    link_dimensions_mm = [round(d3_m * 1000, 3), round(d5_m * 1000, 3)]
    ds_mm = [0, 0, link_dimensions_mm[0], 0, link_dimensions_mm[1], 0, 0]
    dh_table = [
        {"i": i + 1, "alpha_deg": ALPHAS_KNOWN_DEG[i], "a_mm": 0, "d_mm": ds_mm[i]}
        for i in range(7)
    ]
    urdf = dh_table_to_urdf(
        dh_table, robot_name="reference_robot",
        color="0.18 0.35 0.32 1", joint_color="0.16 0.5 0.45 1",
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reference_robot.urdf").write_text(urdf)
    (out_dir / "reference_dh_table.json").write_text(json.dumps(dh_table, indent=2))
    (out_dir / "reference_joint_offsets.json").write_text(
        json.dumps({
            "joint_names": names,
            "z_offsets_raw_m": offsets_m,
            "grouped_link_dimensions_mm": link_dimensions_mm,
        }, indent=2)
    )

    print(urdf)
    print(f"\nScritto {out_dir / 'reference_robot.urdf'}")


if __name__ == "__main__":
    main()
