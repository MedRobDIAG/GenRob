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
      <origin xyz="{x:.4f} {y:.4f} {z:.4f}" rpy="{roll:.4f} {pitch:.4f} 0"/>
      <material name="link_mat"><color rgba="{color}"/></material>
    </visual>
    <visual>
      <geometry><sphere radius="0.055"/></geometry>
      <material name="joint_mat"><color rgba="{joint_color}"/></material>
    </visual>
    <collision>
      <geometry><cylinder radius="0.04" length="{length:.4f}"/></geometry>
      <origin xyz="{x:.4f} {y:.4f} {z:.4f}" rpy="{roll:.4f} {pitch:.4f} 0"/>
    </collision>
    <inertial>
      <mass value="1.0"/>
      <origin xyz="{x:.4f} {y:.4f} {z:.4f}" rpy="0 0 0"/>
      <inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="0.01"/>
    </inertial>"""


def _fixed_joint_transform(alpha_deg, d_mm):
    """Trasformazione 4x4 del SOLO scostamento fisso di un giunto DH URDF
    (<origin xyz="0 0 d" rpy="alpha 0 0"/>: prima trasla di d lungo il vecchio
    Z, poi ruota di alpha attorno a X). Non include la rotazione variabile
    del giunto attorno al proprio asse (quella e' un grado di liberta' a
    runtime, qui vogliamo solo il frame di riposo, a giunto zero)."""
    d_m = d_mm / 1000
    al = np.radians(alpha_deg)
    ca, sa = np.cos(al), np.sin(al)
    T = np.eye(4)
    T[:3, :3] = [[1, 0, 0], [0, ca, -sa], [0, sa, ca]]
    T[2, 3] = d_m
    return T


# asse dominante (0=X,1=Y,2=Z) e segno -> (rpy roll,pitch) per orientare il
# cilindro (di default lungo il proprio asse Z locale) lungo quell'asse.
_AXIS_TO_RPY = {
    (2, 1): (0.0, 0.0),
    (2, -1): (0.0, 0.0),          # simmetrico, nessuna rotazione necessaria
    (1, 1): (-np.pi / 2, 0.0),
    (1, -1): (np.pi / 2, 0.0),
    (0, 1): (0.0, np.pi / 2),
    (0, -1): (0.0, -np.pi / 2),
}


def _link_visual_placement(local_vector, d_m):
    """local_vector: vettore (nel frame locale del link) verso il giunto
    precedente. Per l'architettura qui assunta (a_i=0, alpha_i multiplo di
    90 gradi) e' sempre allineato a un asse. Ritorna (x,y,z,roll,pitch) per
    centrare e orientare il cilindro lungo quel verso."""
    if abs(d_m) < 1e-9:
        return 0.0, 0.0, 0.0, 0.0, 0.0  # link "nullo" (giunti coincidenti), nessuna direzione
    axis = int(np.argmax(np.abs(local_vector)))
    sign = 1 if local_vector[axis] >= 0 else -1
    roll, pitch = _AXIS_TO_RPY[(axis, sign)]
    center = local_vector / 2
    return center[0], center[1], center[2], roll, pitch


def dh_table_to_urdf(dh_table, joints_meta=None, robot_name="robot", color="0.2 0.24 0.27 1",
                      joint_color="0.78 0.42 0.12 1"):
    """dh_table: lista di {i, alpha_deg, a_mm, d_mm}. joints_meta (opzionale):
    lista di {index, range_deg, velocity_deg_s, torque_Nm} per i limiti di giunto.

    Il cilindro che rappresenta ciascun link punta, nel proprio frame
    locale, verso il giunto precedente -- una direzione che dipende dalla
    rotazione cumulativa di tutti i giunti attraversati fino a quel punto
    della catena, non solo dall'alpha del giunto stesso. Si ricostruisce
    l'intera catena di trasformazioni fisse (a giunto variabile = 0) per
    calcolare, per ogni link, il verso corretto."""
    joints_meta = joints_meta or []
    parts = ['  <link name="base_link"/>']

    frames = [np.eye(4)]  # frames[k] = trasformazione cumulativa fino al link k (0 = base_link)
    for row in dh_table:
        frames.append(frames[-1] @ _fixed_joint_transform(row["alpha_deg"], row["d_mm"]))

    for k, row in enumerate(dh_table):
        i = row["i"]
        d_m = row["d_mm"] / 1000
        length = max(abs(d_m), 0.03)

        T_i = frames[k + 1]
        P_i, P_prev = T_i[:3, 3], frames[k][:3, 3]
        local_vector = T_i[:3, :3].T @ (P_prev - P_i)
        x, y, z, roll, pitch = _link_visual_placement(local_vector, d_m)

        visual = LINK_VISUAL.format(length=length, x=x, y=y, z=z, roll=roll, pitch=pitch,
                                     color=color, joint_color=joint_color)
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
