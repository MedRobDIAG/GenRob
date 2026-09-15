"""
Costruzione URDF a partire da una tabella di parametri Denavit-Hartenberg.

Deterministico: nessuna chiamata a un modello generativo in questo file.
Condiviso da build_extracted.py e build_reference.py, cosi' i due URDF messi
a confronto usano esattamente la stessa geometria a primitive (cilindro per
il link, sfera per il giunto) — un confronto visivo onesto in CoppeliaSim.
"""
import numpy as np

URDF_TEMPLATE = """<?xml version="1.0"?>
<robot name="{robot_name}">
{links_and_joints}
</robot>
"""

LINK_VISUAL = """
    <visual>
      <geometry><cylinder radius="0.04" length="{length:.4f}"/></geometry>
      <origin xyz="0 0 {half:.4f}" rpy="0 0 0"/>
      <material name="link_mat"><color rgba="{color}"/></material>
    </visual>
    <visual>
      <geometry><sphere radius="0.055"/></geometry>
      <material name="joint_mat"><color rgba="{joint_color}"/></material>
    </visual>
    <collision>
      <geometry><cylinder radius="0.04" length="{length:.4f}"/></geometry>
      <origin xyz="0 0 {half:.4f}" rpy="0 0 0"/>
    </collision>
    <inertial>
      <mass value="1.0"/>
      <origin xyz="0 0 {half:.4f}" rpy="0 0 0"/>
      <inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="0.01"/>
    </inertial>"""


def dh_table_to_urdf(dh_table, joints_meta=None, robot_name="robot", color="0.2 0.24 0.27 1",
                      joint_color="0.78 0.42 0.12 1"):
    """dh_table: lista di {i, alpha_deg, a_mm, d_mm}. joints_meta (opzionale):
    lista di {index, range_deg, velocity_deg_s, torque_Nm} per i limiti di giunto.

    Il cilindro che rappresenta il link i punta in AVANTI, lungo il proprio
    asse Z locale, verso il giunto (i+1) -- non all'indietro verso il giunto
    precedente. La differenza e' cruciale: l'offset d_{i+1} e' per
    costruzione espresso nel frame del link i stesso, PRIMA che la
    rotazione alpha_{i+1} lo riorienti per il link successivo (convenzione
    DH: si trasla lungo il vecchio Z, poi si ruota) -- quindi non dipende
    in alcun modo dall'angolo variabile di NESSUN giunto, ne' di questo link
    ne' di altri. Puntare all'indietro (verso il giunto precedente, come in
    una versione geometricamente piu' intuitiva ma errata) dipenderebbe
    invece dall'angolo del giunto corrente quando alpha e' non-nullo,
    rompendo la geometria non appena il giunto si muove dalla posa di
    riposo."""
    joints_meta = joints_meta or []
    parts = ['  <link name="base_link"/>']

    n = len(dh_table)
    for k, row in enumerate(dh_table):
        i = row["i"]
        # lunghezza del cilindro di link_i = offset d del giunto SUCCESSIVO
        # (quello che porta da link_i a link_{i+1}), non del giunto corrente.
        next_d_mm = dh_table[k + 1]["d_mm"] if k + 1 < n else 0
        length = max(abs(next_d_mm) / 1000, 0.03)
        visual = LINK_VISUAL.format(length=length, half=length / 2, color=color, joint_color=joint_color)
        parts.append(f'  <link name="link_{i}">{visual}\n  </link>')

        jmeta = next((j for j in joints_meta if j.get("index") == i), {})
        lo = jmeta.get("range_deg")
        vel = jmeta.get("velocity_deg_s")
        eff = jmeta.get("torque_Nm")
        if lo is not None:
            lo_rad, hi_rad = -np.radians(lo), np.radians(lo)
            limit_attrs = (
                f'<limit lower="{lo_rad:.4f}" upper="{hi_rad:.4f}" '
                f'velocity="{np.radians(vel) if vel else 0:.4f}" effort="{eff or 30}"/>'
            )
        else:
            limit_attrs = '<limit lower="-3.14" upper="3.14" velocity="1.0" effort="30"/>'

        parts.append(
            f'  <joint name="joint_{i}" type="revolute">\n'
            f'    <parent link="{"base_link" if i == 1 else f"link_{i - 1}"}"/>\n'
            f'    <child link="link_{i}"/>\n'
            f'    <origin xyz="0 0 {row["d_mm"] / 1000:.4f}" rpy="{np.radians(row["alpha_deg"]):.4f} 0 0"/>\n'
            f'    <axis xyz="0 0 1"/>\n'
            f'    {limit_attrs}\n'
            f'  </joint>'
        )
    return URDF_TEMPLATE.format(robot_name=robot_name, links_and_joints="\n".join(parts))
