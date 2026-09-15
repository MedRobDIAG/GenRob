"""
Validazione empirica del Modulo A, suggerita dalla docente di riferimento
del progetto: invece di affidarsi al solo confronto visivo, si comanda lo
STESSO valore ai giunti corrispondenti di extracted_robot e reference_robot,
e si MISURA -- leggendola direttamente dall'ambiente di simulazione, non
calcolandola offline -- la posa (posizione + orientamento) di un piccolo
utensile attaccato all'ultimo link di ciascun braccio.

I giunti vengono impostati in modalita' cinematica (istantanea): qui
interessano solo i valori numerici letti via API, non la resa visiva della
scena (per quella, vedi set_demo_pose.py).

A ogni robot viene aggiunto un piccolo dummy "tool_tip" figlio di link_7,
cosi' da poter leggere anche l'ORIENTAMENTO (non solo la posizione), come
richiesto: un singolo punto non basta a validare la rotazione dell'ultimo
giunto.

Uso:
    python3 measure_toolpose.py [--n-poses 20] [--seed 0]
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from coppeliasim_zmqremoteapi_client import RemoteAPIClient

HERE = Path(__file__).parent
IMPORT_OPTIONS = (1 << 1) | (1 << 3) | (1 << 7)  # showJoints + createVisualIfNone + alternateLocalRespondableMasks


def import_robot(sim, simURDF, urdf_path, x_offset):
    imp = getattr(simURDF, "import")
    robot_name, handles = imp(str(urdf_path), IMPORT_OPTIONS)
    sim.setObjectPosition(handles[0], -1, [x_offset, 0, 0])
    return robot_name, handles[0]


def find_joints(sim, root_handle):
    """joint_1..joint_7, nell'ordine, appartenenti al sottoalbero di root_handle."""
    joints = {}
    for h in sim.getObjectsInTree(root_handle, sim.handle_all, 0):
        alias = sim.getObjectAlias(h)
        if alias.startswith("joint_"):
            joints[int(alias.split("_")[1])] = h
    return [joints[i] for i in sorted(joints)]


def find_link(sim, root_handle, name):
    for h in sim.getObjectsInTree(root_handle, sim.handle_all, 0):
        if sim.getObjectAlias(h) == name:
            return h
    raise SystemExit(f"Oggetto '{name}' non trovato sotto root={root_handle}")


def attach_tool_tip(sim, root_handle, tool_length_m=0.08):
    """Piccolo dummy figlio dell'ultimo link (link_7_respondable -- il vero
    frame rigido del link, di cui link_7_visual e' figlio/sotto-shape),
    spostato lungo il suo asse Z locale: rappresenta un utensile minimale,
    cosi' la sua posa (posizione + orientamento) e' distinguibile dal solo
    frame del giunto."""
    parent = find_link(sim, root_handle, "link_7_respondable")
    tool = sim.createDummy(0.03)
    sim.setObjectParent(tool, parent, True)
    sim.setObjectPosition(tool, parent, [0, 0, tool_length_m])
    sim.setObjectOrientation(tool, parent, [0, 0, 0])
    return tool


def set_pose(sim, joints, angles_rad):
    for h, q in zip(joints, angles_rad):
        sim.setJointMode(h, sim.jointmode_kinematic, 0)
        sim.setJointPosition(h, q)


def quat_angle_deg(q1, q2):
    """Angolo (gradi) tra due orientamenti, dati come quaternioni [x,y,z,w]."""
    dot = abs(sum(a * b for a, b in zip(q1, q2)))
    dot = min(1.0, max(-1.0, dot))
    return np.degrees(2 * np.arccos(dot))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-poses", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--outputs", default=str(HERE.parent / "outputs"))
    args = ap.parse_args()

    out_dir = Path(args.outputs)
    extracted_urdf = out_dir / "extracted_robot.urdf"
    reference_urdf = out_dir / "reference_robot.urdf"
    for p in (extracted_urdf, reference_urdf):
        if not p.exists():
            raise SystemExit(f"Manca {p} — esegui prima module_a/build_extracted.py e build_reference.py")

    print("Connessione a CoppeliaSim...")
    client = RemoteAPIClient()
    sim = client.require("sim")
    simURDF = client.require("simURDF")

    sim.stopSimulation()
    time.sleep(0.3)
    sim.closeScene()
    time.sleep(0.3)

    _, extracted_root = import_robot(sim, simURDF, extracted_urdf, x_offset=-0.6)
    _, reference_root = import_robot(sim, simURDF, reference_urdf, x_offset=0.6)
    print("Robot importati (estratto a sinistra, riferimento a destra).")

    extracted_joints = find_joints(sim, extracted_root)
    reference_joints = find_joints(sim, reference_root)
    assert len(extracted_joints) == len(reference_joints) == 7

    extracted_tool = attach_tool_tip(sim, extracted_root)
    reference_tool = attach_tool_tip(sim, reference_root)
    print("Tool tip aggiunto a entrambi i bracci (dummy 3cm all'estremita' di link_7).\n")

    # limiti di giunto (gradi) coerenti con extract_from_manual.py / KUKA LWR4+
    JOINT_LIMITS_DEG = [170, 120, 170, 120, 170, 120, 175]

    rng = np.random.default_rng(args.seed)
    results = []

    # prima posa: quella "zero" (a riposo) come caso di controllo
    test_poses_deg = [[0] * 7]
    for _ in range(args.n_poses - 1):
        test_poses_deg.append([rng.uniform(-lim, lim) for lim in JOINT_LIMITS_DEG])

    print(f"{'#':>3} {'pos.err (mm)':>14} {'orient.err (deg)':>18}")
    for i, pose_deg in enumerate(test_poses_deg):
        angles_rad = np.radians(pose_deg)

        set_pose(sim, extracted_joints, angles_rad)
        set_pose(sim, reference_joints, angles_rad)

        p_ext = sim.getObjectPosition(extracted_tool, -1)
        p_ref = sim.getObjectPosition(reference_tool, -1)
        # rimuovi l'offset di piazzamento x (i due robot sono affiancati nella
        # scena solo per comodita' visiva, non fa parte del confronto cinematico)
        p_ext = [p_ext[0] + 0.6, p_ext[1], p_ext[2]]
        p_ref = [p_ref[0] - 0.6, p_ref[1], p_ref[2]]
        pos_err_mm = 1000 * np.linalg.norm(np.array(p_ext) - np.array(p_ref))

        q_ext = sim.getObjectQuaternion(extracted_tool, -1)
        q_ref = sim.getObjectQuaternion(reference_tool, -1)
        orient_err_deg = quat_angle_deg(q_ext, q_ref)

        print(f"{i:>3} {pos_err_mm:>14.2f} {orient_err_deg:>18.3f}")
        results.append({
            "pose_deg": pose_deg,
            "position_extracted_m": p_ext,
            "position_reference_m": p_ref,
            "position_error_mm": pos_err_mm,
            "orientation_error_deg": orient_err_deg,
        })

    pos_errs = [r["position_error_mm"] for r in results]
    orient_errs = [r["orientation_error_deg"] for r in results]
    summary = {
        "n_poses": len(results),
        "position_error_mean_mm": float(np.mean(pos_errs)),
        "position_error_max_mm": float(np.max(pos_errs)),
        "orientation_error_mean_deg": float(np.mean(orient_errs)),
        "orientation_error_max_deg": float(np.max(orient_errs)),
        "poses": results,
    }
    out_path = out_dir / "toolpose_validation_report.json"
    out_path.write_text(json.dumps(summary, indent=2))

    print(f"\nErrore posizione:    media {summary['position_error_mean_mm']:.2f} mm, "
          f"max {summary['position_error_max_mm']:.2f} mm")
    print(f"Errore orientamento: media {summary['orientation_error_mean_deg']:.3f}°, "
          f"max {summary['orientation_error_max_deg']:.3f}°")
    print(f"\nReport scritto in {out_path}")


if __name__ == "__main__":
    main()
