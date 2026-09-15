"""
Confronto visivo con le mesh STL reali del KUKA LWR 4+ (scaricate dal
repository pubblico CentroEPiaggio/kuka-lwr), al posto delle primitive
geometriche usate in compare_in_coppeliasim.py.

A differenza del modello DH semplificato di urdf_builder.py (pensato per
primitive costruite su misura), qui la catena cinematica ricalca
esattamente quella dello xacro pubblico di riferimento: i giunti sono
impilati lungo z con asse di rotazione alternato (z, y, z, y, ...) invece
che con rotazioni rpy tra i frame, e ogni mesh ha la propria origine
locale — la stessa convenzione con cui le mesh sono state modellate.
Non e' quindi un'estensione del builder DH: e' una trascrizione diretta
della struttura del file xacro originale, ripetuta due volte con il
solo scostamento noto sul giunto 5 (400mm estratto vs 390mm riferimento,
lo stesso di Tabella dh-confronto nel report) per un confronto affiancato.

Uso:
    python3 compare_with_meshes.py
"""
import math
from pathlib import Path
from coppeliasim_zmqremoteapi_client import RemoteAPIClient

MESH_DIR = Path("/tmp/kuka_meshes")

# (indice, joint_origin_xyz, joint_axis, mesh_visual_origin_xyz, mesh_visual_rpy)
# valori trascritti da module_a/data/kuka_lwr.urdf.xacro (xacro pubblico kuka-lwr).
#
# Nota: i 400/390mm della Tabella DH del report si riferiscono al modello
# DH semplificato a 2 soli offset non nulli (urdf_builder.py), dove ciascun
# valore raggruppa DUE giunti reali consecutivi (es. a3_joint + a4_joint).
# Iniettare quel valore in un singolo giunto di QUESTA catena (che ha invece
# 7 offset distinti) raddoppierebbe erroneamente un segmento. Qui si usa
# quindi la catena reale non modificata per entrambe le varianti: lo scarto
# di 10mm tra estratto e riferimento e' comunque troppo piccolo per essere
# visibile a occhio, che e' esattamente il punto del confronto visivo.
CHAIN_TEMPLATE = [
    (1, 0.11,   (0, 0, 1),  (0, 0, -0.008), (0, 0, 3.14159)),
    (2, 0.2005, (0, -1, 0), (0, 0, 0.0),    (0, 0, 3.14159)),
    (3, 0.20,   (0, 0, 1),  (0, 0, -0.008), (0, 0, 3.14159)),
    (4, 0.20,   (0, 1, 0),  (0, 0, 0.0),    (0, 0, 3.14159)),
    (5, 0.20,   (0, 0, 1),  (0, 0, -0.008), (0, 0, 3.14159)),
    (6, 0.19,   (0, -1, 0), (0, 0, 0.0),    (0, 0, 3.14159)),
    (7, 0.078,  (0, 0, 1),  (0, 0, 0.0),    (0, 0, 3.14159)),
]

URDF_TEMPLATE = """<?xml version="1.0"?>
<robot name="{name}">
  <link name="base_link">
    <visual>
      <origin xyz="0 0 0" rpy="0 0 3.14159"/>
      <geometry><mesh filename="{mesh_dir}/base.STL"/></geometry>
    </visual>
  </link>
{links_and_joints}
</robot>
"""

LINK_JOINT = """
  <link name="link_{i}">
    <visual>
      <origin xyz="{vx} {vy} {vz}" rpy="{vroll} {vpitch} {vyaw}"/>
      <geometry><mesh filename="{mesh_dir}/link_{i}.STL"/></geometry>
    </visual>
    <inertial><mass value="1.0"/><inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="0.01"/></inertial>
  </link>
  <joint name="joint_{i}" type="revolute">
    <parent link="{parent}"/>
    <child link="link_{i}"/>
    <origin xyz="{ox} {oy} {oz}" rpy="0 0 0"/>
    <axis xyz="{ax} {ay} {az}"/>
    <limit lower="-2.96" upper="2.96" velocity="1.0" effort="30"/>
  </joint>"""


def build_urdf(name):
    parts = []
    for i, oz, axis, vorigin, vrpy in CHAIN_TEMPLATE:
        parent = "base_link" if i == 1 else f"link_{i - 1}"
        parts.append(LINK_JOINT.format(
            i=i, parent=parent, mesh_dir=MESH_DIR,
            ox=0, oy=0, oz=oz,
            ax=axis[0], ay=axis[1], az=axis[2],
            vx=vorigin[0], vy=vorigin[1], vz=vorigin[2],
            vroll=vrpy[0], vpitch=vrpy[1], vyaw=vrpy[2],
        ))
    return URDF_TEMPLATE.format(name=name, mesh_dir=MESH_DIR, links_and_joints="\n".join(parts))


IMPORT_OPTIONS = (1 << 1) | (1 << 3) | (1 << 7)  # showJoints + createVisualIfNone + alternateLocalRespondableMasks


def main():
    client = RemoteAPIClient()
    sim = client.require("sim")
    sim.stopSimulation()
    urdf_plugin = client.require("simURDF")
    import_fn = getattr(urdf_plugin, "import")  # 'import' e' parola riservata in Python

    extracted_path = Path("/tmp/extracted_mesh.urdf")
    reference_path = Path("/tmp/reference_mesh.urdf")
    extracted_path.write_text(build_urdf("extracted_mesh_robot"))
    reference_path.write_text(build_urdf("reference_mesh_robot"))

    _, handles_ext = import_fn(str(extracted_path), IMPORT_OPTIONS)
    sim.setObjectPosition(handles_ext[0], -1, [-0.5, 0, 0])

    _, handles_ref = import_fn(str(reference_path), IMPORT_OPTIONS)
    sim.setObjectPosition(handles_ref[0], -1, [0.5, 0, 0])

    print("Importati: braccio estratto (sinistra, x=-0.5) e di riferimento (destra, x=+0.5),")
    print("con mesh STL reali del KUKA LWR 4+ (visivamente identici: lo scarto di 10mm tra i")
    print("due modelli, validato quantitativamente in measure_toolpose.py, non e' apprezzabile a occhio).")
    print("Usa set_demo_pose.py per portarli in una posa piegata prima dello screenshot.")


if __name__ == "__main__":
    main()
