"""
Prossimo incremento della demo (report, S3.8): importa in CoppeliaSim l'URDF
estratto e quello di riferimento e li affianca nella stessa scena, per il
confronto visivo diretto -- passaggio successivo, non sostitutivo, al
confronto puramente numerico di module_a/validate.py.

Il confronto visivo si fa guardando la finestra di CoppeliaSim, aperta sullo
schermo, dopo aver lanciato questo script (ed eventualmente set_demo_pose.py
per una posa piegata anziche' a riposo).

Prerequisiti:
  - CoppeliaSim aperto (qualunque scena), con il server zmqRemoteApi attivo
    (di default lo e' su localhost:23000).
  - pip install coppeliasim-zmqremoteapi-client
  - module_a/build_extracted.py e build_reference.py gia' eseguiti
    (servono outputs/extracted_robot.urdf e outputs/reference_robot.urdf).

Uso:
    python3 compare_in_coppeliasim.py [--outputs ../outputs]
"""
import argparse
import time
from pathlib import Path

from coppeliasim_zmqremoteapi_client import RemoteAPIClient

HERE = Path(__file__).parent

# showJoints(2) + createVisualIfNone(8) + alternateLocalRespondableMasks(128)
IMPORT_OPTIONS = (1 << 1) | (1 << 3) | (1 << 7)


def import_and_place(sim, simURDF, urdf_path: str, x_offset: float):
    import_fn = getattr(simURDF, "import")  # 'import' e' parola riservata in Python
    robot_name, handles = import_fn(urdf_path, IMPORT_OPTIONS)
    base_handle = handles[0]
    sim.setObjectPosition(base_handle, -1, [x_offset, 0, 0])
    return robot_name, base_handle


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outputs", default=str(HERE.parent / "outputs"))
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=23000)
    args = ap.parse_args()

    out_dir = Path(args.outputs)
    extracted_urdf = out_dir / "extracted_robot.urdf"
    reference_urdf = out_dir / "reference_robot.urdf"
    for p in (extracted_urdf, reference_urdf):
        if not p.exists():
            raise SystemExit(f"Manca {p} — esegui prima build_extracted.py e build_reference.py in module_a/")

    print(f"Connessione a CoppeliaSim su {args.host}:{args.port} ...")
    client = RemoteAPIClient(host=args.host, port=args.port)
    sim = client.require("sim")
    simURDF = client.require("simURDF")

    sim.stopSimulation()
    time.sleep(0.3)

    print(f"Import {extracted_urdf} (grigio/arancio, a sinistra, x=-0.6m)")
    import_and_place(sim, simURDF, str(extracted_urdf), x_offset=-0.6)

    print(f"Import {reference_urdf} (verde, a destra, x=+0.6m)")
    import_and_place(sim, simURDF, str(reference_urdf), x_offset=0.6)

    print(
        "\nFatto. I due modelli sono affiancati nella scena di CoppeliaSim, "
        "aperta sullo schermo — guarda la finestra dell'app per il confronto "
        "visivo (i giunti dell'estratto sono arancioni, quelli di riferimento "
        "verdi). Il confronto numerico completo resta in module_a/validate.py "
        "(portata totale + equivalenza cinematica)."
    )


if __name__ == "__main__":
    main()
