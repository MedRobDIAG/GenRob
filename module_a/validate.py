"""
Modulo A, passo 3/3: validazione quantitativa dell'URDF estratto contro
l'URDF di riferimento. Due metriche complementari:

1. Confronto sulla portata totale (somma degli offset d_i) -- semplice,
   robusto alla convenzione DH, ma grossolano.
2. Equivalenza cinematica Monte Carlo -- confronta la trasformazione
   relativa base->end-effector su N coppie di configurazioni casuali,
   indipendente dalla convenzione di frame scelta.

Richiede che build_extracted.py e build_reference.py siano gia' stati
eseguiti (legge outputs/extracted_dh_table.json e reference_dh_table.json).

Uso:
    python3 validate.py [--outputs ../outputs] [--n-pairs 300]
"""
import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent


def dh_forward_kinematics(dh_table, joint_values_rad):
    T = np.eye(4)
    for row, q in zip(dh_table, joint_values_rad):
        al, d = np.radians(row["alpha_deg"]), row["d_mm"]
        ct, st, ca, sa = np.cos(q), np.sin(q), np.cos(al), np.sin(al)
        A = np.array([
            [ct, -st * ca, st * sa, 0],
            [st, ct * ca, -ct * sa, 0],
            [0, sa, ca, d],
            [0, 0, 0, 1],
        ])
        T = T @ A
    return T


def rotation_angle_deg(R):
    return np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))


def kinematic_equivalence(dh_a, dh_b, n_pairs=300, seed=0):
    rng = np.random.default_rng(seed)
    dof = len(dh_a)
    pos_err, rot_err = [], []
    for _ in range(n_pairs):
        q1 = rng.uniform(-np.pi, np.pi, dof)
        q2 = rng.uniform(-np.pi, np.pi, dof)
        rel_a = np.linalg.inv(dh_forward_kinematics(dh_a, q1)) @ dh_forward_kinematics(dh_a, q2)
        rel_b = np.linalg.inv(dh_forward_kinematics(dh_b, q1)) @ dh_forward_kinematics(dh_b, q2)
        pos_err.append(np.linalg.norm(rel_a[:3, 3] - rel_b[:3, 3]))
        rot_err.append(rotation_angle_deg(rel_a[:3, :3].T @ rel_b[:3, :3]))
    return float(np.mean(pos_err)), float(np.max(pos_err)), float(np.mean(rot_err)), float(np.max(rot_err))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outputs", default=str(HERE.parent / "outputs"))
    ap.add_argument("--n-pairs", type=int, default=300)
    args = ap.parse_args()
    out_dir = Path(args.outputs)

    extracted_dh = json.loads((out_dir / "extracted_dh_table.json").read_text())
    reference_dh = json.loads((out_dir / "reference_dh_table.json").read_text())

    # entrambe le tabelle DH seguono ormai la stessa architettura a 2 offset non
    # nulli (spalla->gomito, gomito->polso, vedi build_reference.py) -- confronto
    # diretto, senza bisogno di escludere base/flangia "a posteriori".
    extracted_total_mm = sum(row["d_mm"] for row in extracted_dh)
    reference_total_mm = sum(row["d_mm"] for row in reference_dh)
    err_mm = abs(extracted_total_mm - reference_total_mm)

    print(f"Portata totale — estratta:    {extracted_total_mm:.1f} mm")
    print(f"Portata totale — riferimento: {reference_total_mm:.1f} mm")
    print(f"Errore: {err_mm:.1f} mm ({100 * err_mm / reference_total_mm:.1f}%)")

    mean_pos, max_pos, mean_rot, max_rot = kinematic_equivalence(
        extracted_dh, reference_dh, n_pairs=args.n_pairs
    )
    print(f"\nEquivalenza cinematica su {args.n_pairs} coppie casuali:")
    print(f"  Errore posizione:    media {mean_pos:.2f} mm, max {max_pos:.2f} mm")
    print(f"  Errore orientazione: media {mean_rot:.4f}°, max {max_rot:.4f}°")

    report = {
        "reach_extracted_mm": extracted_total_mm,
        "reach_reference_mm": reference_total_mm,
        "reach_error_mm": err_mm,
        "reach_error_pct": 100 * err_mm / reference_total_mm,
        "kinematic_pos_error_mean_mm": mean_pos,
        "kinematic_pos_error_max_mm": max_pos,
        "kinematic_rot_error_mean_deg": mean_rot,
        "kinematic_rot_error_max_deg": max_rot,
        "n_pairs": args.n_pairs,
    }
    (out_dir / "validation_report.json").write_text(json.dumps(report, indent=2))
    print(f"\nReport scritto in {out_dir / 'validation_report.json'}")


if __name__ == "__main__":
    main()
