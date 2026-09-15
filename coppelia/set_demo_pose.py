"""
Applica una posa "piegata" (angoli di giunto non-zero) ai due robot gia'
importati da compare_in_coppeliasim.py, per un confronto visivo piu'
naturale della posa a riposo (che con questa architettura, a_i=0 per tutti
i link, e' un braccio completamente disteso -- vedi il disegno Fig. 4-1 del
manuale KUKA, che raffigura lo stesso robot esteso in verticale).

Usa gli stessi angoli del render Three.js del notebook/dimostratore
(q = [40,-60,-20,70,30,-30,15] gradi), applicati a entrambi i robot cosi' il
confronto resta equo.

I giunti vengono comandati come motorizzati (setJointTargetPosition) e la
simulazione viene fatta girare per un paio di secondi e poi messa in pausa
(mai fermata: lo stop riporterebbe il robot alla posa iniziale) -- questo
garantisce che il rendering nel viewport rifletta correttamente la posa
comandata.

Prerequisiti: compare_in_coppeliasim.py gia' eseguito in questa sessione di
CoppeliaSim (i robot extracted_robot/reference_robot devono gia' esistere
nella scena).

Uso:
    python3 set_demo_pose.py
"""
import time

import numpy as np
from coppeliasim_zmqremoteapi_client import RemoteAPIClient

DEMO_POSE_DEG = [55, -55, 35, 75, -20, 40, -10]
SETTLE_SECONDS = 2.5  # tempo di simulazione per lasciar convergere il controllo di posizione


def root_ancestor(sim, handle):
    """Risale la gerarchia fino all'oggetto senza genitore -- identifica in
    modo stabile a quale dei due robot importati appartiene un giunto,
    indipendentemente dalla posa corrente (la posizione nello spazio cambia
    quando i giunti si piegano, l'albero degli oggetti no)."""
    h = handle
    parent = sim.getObjectParent(h)
    while parent != -1:
        h = parent
        parent = sim.getObjectParent(h)
    return h


def main():
    client = RemoteAPIClient()
    sim = client.require("sim")

    # raggruppa i joint_N per robot di appartenenza (radice della gerarchia)
    all_joints = {}
    for h in sim.getObjectsInTree(sim.handle_scene, sim.handle_all, 0):
        alias = sim.getObjectAlias(h)
        if alias.startswith("joint_"):
            idx = int(alias.split("_")[1])
            root = root_ancestor(sim, h)
            all_joints.setdefault(root, {})[idx] = h

    if not all_joints:
        raise SystemExit("Nessun giunto trovato in scena — esegui prima compare_in_coppeliasim.py")

    print(f"Trovati {len(all_joints)} robot in scena")
    for root, joints in all_joints.items():
        for idx, deg in enumerate(DEMO_POSE_DEG, start=1):
            if idx in joints:
                sim.setJointTargetPosition(joints[idx], np.radians(deg))
        print(f"  robot (root={root}): target impostato su {len(joints)} giunti")

    print(f"\nFaccio girare la simulazione per {SETTLE_SECONDS}s per raggiungere la posa...")
    sim.startSimulation()
    time.sleep(SETTLE_SECONDS)
    sim.pauseSimulation()

    print("\nFatto. Guarda la finestra di CoppeliaSim: entrambi i bracci ora sono nella stessa posa piegata.")


if __name__ == "__main__":
    main()
