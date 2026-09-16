"""
Come measure_toolpose.py, ma con le mesh CAD reali del KUKA LWR 4+
(compare_with_meshes.py) al posto delle primitive, e con un'unica posa
fissa anziche' un campione casuale: pensato per uno screenshot in cui il
tool tip di entrambi i bracci sia visibile, accompagnato dalla lettura
numerica della sua posa.

Uso:
    python3 measure_toolpose_meshes.py
"""
import time
import numpy as np
from coppeliasim_zmqremoteapi_client import RemoteAPIClient

from compare_with_meshes import build_urdf, IMPORT_OPTIONS

DEMO_POSE_DEG = [20, -30, 15, 40, -10, 20, 0]
TOOL_LENGTH_M = 0.10
TOOL_RADIUS_M = 0.02


def find_joints(sim, root_handle):
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


def attach_visible_tool_tip(sim, root_handle, color):
    """Dummy piu' grande e colorato (rispetto a measure_toolpose.py),
    pensato per essere visibile in uno screenshot, non solo leggibile via API."""
    parent = find_link(sim, root_handle, "link_7_respondable")
    tool = sim.createDummy(0.015)
    sim.setObjectParent(tool, parent, True)
    sim.setObjectPosition(tool, parent, [0, 0, TOOL_LENGTH_M])
    sim.setObjectOrientation(tool, parent, [0, 0, 0])

    marker = sim.createPrimitiveShape(sim.primitiveshape_spheroid, [TOOL_RADIUS_M] * 3)
    sim.setShapeColor(marker, None, sim.colorcomponent_ambient_diffuse, color)
    sim.setObjectParent(marker, tool, True)
    sim.setObjectPosition(marker, tool, [0, 0, 0])

    return tool


def quat_angle_deg(q1, q2):
    dot = abs(sum(a * b for a, b in zip(q1, q2)))
    dot = min(1.0, max(-1.0, dot))
    return np.degrees(2 * np.arccos(dot))


def main():
    client = RemoteAPIClient()
    sim = client.require("sim")
    sim.stopSimulation()
    time.sleep(0.3)
    urdf_plugin = client.require("simURDF")
    import_fn = getattr(urdf_plugin, "import")

    extracted_path = "/tmp/extracted_mesh.urdf"
    reference_path = "/tmp/reference_mesh.urdf"
    open(extracted_path, "w").write(build_urdf("extracted_mesh_robot", a5_offset_m=0.20))
    open(reference_path, "w").write(build_urdf("reference_mesh_robot", a5_offset_m=0.19))

    _, handles_ext = import_fn(extracted_path, IMPORT_OPTIONS)
    sim.setObjectPosition(handles_ext[0], -1, [-0.5, 0, 0])

    _, handles_ref = import_fn(reference_path, IMPORT_OPTIONS)
    sim.setObjectPosition(handles_ref[0], -1, [0.5, 0, 0])

    extracted_joints = find_joints(sim, handles_ext[0])
    reference_joints = find_joints(sim, handles_ref[0])

    extracted_tool = attach_visible_tool_tip(sim, handles_ext[0], [1.0, 0.35, 0.0])   # arancio: estratto
    reference_tool = attach_visible_tool_tip(sim, handles_ref[0], [0.15, 0.75, 0.35])  # verde: riferimento

    angles_rad = np.radians(DEMO_POSE_DEG)
    for h, q in zip(extracted_joints, angles_rad):
        sim.setJointMode(h, sim.jointmode_kinematic, 0)
        sim.setJointPosition(h, q)
    for h, q in zip(reference_joints, angles_rad):
        sim.setJointMode(h, sim.jointmode_kinematic, 0)
        sim.setJointPosition(h, q)

    p_ext = sim.getObjectPosition(extracted_tool, -1)
    p_ref = sim.getObjectPosition(reference_tool, -1)
    p_ext_rel = [p_ext[0] + 0.5, p_ext[1], p_ext[2]]
    p_ref_rel = [p_ref[0] - 0.5, p_ref[1], p_ref[2]]
    pos_err_mm = 1000 * np.linalg.norm(np.array(p_ext_rel) - np.array(p_ref_rel))

    q_ext = sim.getObjectQuaternion(extracted_tool, -1)
    q_ref = sim.getObjectQuaternion(reference_tool, -1)
    orient_err_deg = quat_angle_deg(q_ext, q_ref)

    print("Robot importati con mesh reali (estratto sinistra/arancio, riferimento destra/verde).")
    print("Tool tip aggiunto e reso visibile (sfera colorata) all'estremita' di link_7 di entrambi.")
    print(f"\nPosa comandata (gradi): {DEMO_POSE_DEG}")
    print(f"Posizione tool tip — estratto:    {[round(v, 4) for v in p_ext_rel]} m")
    print(f"Posizione tool tip — riferimento: {[round(v, 4) for v in p_ref_rel]} m")
    print(f"\nErrore posizione:    {pos_err_mm:.2f} mm")
    print(f"Errore orientamento: {orient_err_deg:.3f}°")


if __name__ == "__main__":
    main()
