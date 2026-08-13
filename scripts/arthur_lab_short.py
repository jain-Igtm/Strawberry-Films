#!/usr/bin/env python3
"""Build the first Strawberry Films short entirely through Blender Python.

The scene is a 30-second, dialogue-free action proof: Arthur changes into a
cold dissociative state in a laboratory, his hair lifts, loose equipment rises,
and two guards attempt to contain him.  It is deliberately self-contained so
GitHub Actions can render it without any hand-authored .blend file.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

import bpy
from mathutils import Vector


FPS = 15
FRAME_END = 450
DEG = math.pi / 180.0


@dataclass
class Palette:
    skin: object
    hair: object
    shirt: object
    trousers: object
    shoes: object
    sclera: object
    eyes: object
    pupils: object
    brows: object


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", required=True, help="Destination .blend file")
    parser.add_argument("--preview", action="store_true", help="Render frame 240 after building")
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def material(
    name: str,
    color: Tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.45,
    emission: Tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
    alpha: float = 1.0,
) -> object:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    if emission is not None:
        for socket_name in ("Emission Color", "Emission"):
            if socket_name in bsdf.inputs:
                bsdf.inputs[socket_name].default_value = emission
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        mat.diffuse_color = (color[0], color[1], color[2], alpha)
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
        if hasattr(mat, "use_transparency_overlap"):
            mat.use_transparency_overlap = False
    return mat


def apply_material(obj: object, mat: object) -> None:
    if hasattr(obj.data, "materials"):
        obj.data.materials.append(mat)


def bevel(obj: object, width: float = 0.04, segments: int = 3) -> None:
    mod = obj.modifiers.new("softened edges", "BEVEL")
    mod.width = width
    mod.segments = segments


def cube(
    name: str,
    location: Sequence[float],
    scale: Sequence[float],
    mat: object,
    *,
    parent: object | None = None,
    bevel_width: float = 0.04,
) -> object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0) if parent else location)
    obj = bpy.context.object
    obj.name = name
    if parent:
        obj.parent = parent
        obj.location = location
    obj.scale = scale
    apply_material(obj, mat)
    if bevel_width:
        bevel(obj, bevel_width)
    return obj


def sphere(
    name: str,
    location: Sequence[float],
    scale: Sequence[float],
    mat: object,
    *,
    parent: object | None = None,
    segments: int = 32,
) -> object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=max(12, segments // 2), location=(0, 0, 0) if parent else location)
    obj = bpy.context.object
    obj.name = name
    if parent:
        obj.parent = parent
        obj.location = location
    obj.scale = scale
    apply_material(obj, mat)
    bpy.ops.object.shade_smooth()
    return obj


def cylinder(
    name: str,
    location: Sequence[float],
    radius: float,
    depth: float,
    mat: object,
    *,
    parent: object | None = None,
    vertices: int = 24,
) -> object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=(0, 0, 0) if parent else location)
    obj = bpy.context.object
    obj.name = name
    if parent:
        obj.parent = parent
        obj.location = location
    apply_material(obj, mat)
    bevel(obj, min(radius * 0.25, 0.03), 2)
    return obj


def cone(
    name: str,
    location: Sequence[float],
    radius: float,
    depth: float,
    mat: object,
    *,
    parent: object | None = None,
) -> object:
    bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=radius, radius2=0.012, depth=depth, location=(0, 0, 0) if parent else location)
    obj = bpy.context.object
    obj.name = name
    if parent:
        obj.parent = parent
        obj.location = location
    apply_material(obj, mat)
    bpy.ops.object.shade_smooth()
    return obj


def empty(name: str, location: Sequence[float], parent: object | None = None) -> object:
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.12
    obj.parent = parent
    obj.location = location
    return obj


def segment(name: str, joint: object, length: float, radius: float, mat: object) -> object:
    part = sphere(name, (0, 0, -length / 2), (radius, radius * 0.82, length / 2), mat, parent=joint, segments=32)
    return part


def profile_mesh(
    name: str,
    location: Sequence[float],
    rings: Sequence[Tuple[float, float, float]],
    mat: object,
    *,
    parent: object | None = None,
    sides: int = 32,
) -> object:
    """Create a smooth tapered form from (z, x-radius, y-radius) rings."""
    vertices: List[Tuple[float, float, float]] = []
    for z, radius_x, radius_y in rings:
        for index in range(sides):
            angle = math.tau * index / sides
            vertices.append((math.cos(angle) * radius_x, math.sin(angle) * radius_y, z))
    faces: List[Tuple[int, ...]] = []
    for ring in range(len(rings) - 1):
        start = ring * sides
        next_start = (ring + 1) * sides
        for index in range(sides):
            following = (index + 1) % sides
            faces.append((start + index, start + following, next_start + following, next_start + index))
    faces.append(tuple(reversed(range(sides))))
    last = (len(rings) - 1) * sides
    faces.append(tuple(last + index for index in range(sides)))
    mesh = bpy.data.meshes.new(f"{name} mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.location = location
    apply_material(obj, mat)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    bevel(obj, 0.018, 2)
    return obj


def curve_line(
    name: str,
    points: Sequence[Sequence[float]],
    thickness: float,
    mat: object,
    *,
    parent: object | None = None,
) -> object:
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = thickness
    curve.bevel_resolution = 3
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, coordinate in zip(spline.bezier_points, points):
        point.co = coordinate
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    apply_material(obj, mat)
    return obj


def hair_lock(
    name: str,
    base: Sequence[float],
    length: float,
    radius: float,
    mat: object,
    *,
    parent: object,
) -> object:
    rings = [
        (0.00, radius, radius * 0.55),
        (length * 0.32, radius * 0.86, radius * 0.48),
        (length * 0.66, radius * 0.55, radius * 0.34),
        (length, 0.008, 0.005),
    ]
    return profile_mesh(name, base, rings, mat, parent=parent, sides=12)


def key_location(obj: object, frame: int, xyz: Sequence[float]) -> None:
    obj.location = xyz
    obj.keyframe_insert(data_path="location", frame=frame)


def key_rotation(obj: object, frame: int, xyz_degrees: Sequence[float]) -> None:
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = tuple(v * DEG for v in xyz_degrees)
    obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def key_scale(obj: object, frame: int, xyz: Sequence[float]) -> None:
    obj.scale = xyz
    obj.keyframe_insert(data_path="scale", frame=frame)


def key_energy(light: object, frame: int, energy: float) -> None:
    light.data.energy = energy
    light.data.keyframe_insert(data_path="energy", frame=frame)


def set_interpolation(obj: object, interpolation: str = "BEZIER") -> None:
    if not obj.animation_data or not obj.animation_data.action:
        return
    for curve in obj.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = interpolation


def make_palette(
    prefix: str,
    shirt_color: Tuple[float, float, float, float],
    hair_color=(0.025, 0.018, 0.015, 1),
    skin_color=(0.62, 0.39, 0.29, 1),
) -> Palette:
    return Palette(
        skin=material(f"{prefix} skin", skin_color, roughness=0.53),
        hair=material(f"{prefix} hair", hair_color, roughness=0.68),
        shirt=material(f"{prefix} shirt", shirt_color, roughness=0.62),
        trousers=material(f"{prefix} trousers", (0.035, 0.045, 0.055, 1), roughness=0.72),
        shoes=material(f"{prefix} shoes", (0.012, 0.014, 0.018, 1), roughness=0.5),
        sclera=material(f"{prefix} sclera", (0.72, 0.72, 0.68, 1), roughness=0.28),
        eyes=material(f"{prefix} irises", (0.055, 0.13, 0.12, 1), roughness=0.22),
        pupils=material(f"{prefix} pupils", (0.003, 0.004, 0.004, 1), roughness=0.2),
        brows=material(f"{prefix} brows", hair_color, roughness=0.7),
    )


def create_character(name: str, location: Sequence[float], palette: Palette, *, size: float = 1.0, young: bool = False) -> Dict[str, object]:
    root = empty(f"{name} root", location)
    root.scale = (size, size, size)

    body_width = 0.285 if young else 0.335
    pelvis = profile_mesh(
        f"{name} pelvis",
        (0, 0, 0),
        ((0.78, 0.20, 0.145), (0.91, 0.27, 0.18), (1.05, 0.25, 0.17)),
        palette.trousers,
        parent=root,
    )
    torso = profile_mesh(
        f"{name} torso",
        (0, 0, 0),
        (
            (1.00, body_width * 0.76, 0.145),
            (1.20, body_width * 0.88, 0.16),
            (1.48, body_width, 0.175),
            (1.64, body_width * 1.06, 0.18),
            (1.70, body_width * 0.70, 0.14),
        ),
        palette.shirt,
        parent=root,
    )
    cube(f"{name} belt", (0, -0.012, 1.02), (0.245, 0.16, 0.025), palette.shoes, parent=root, bevel_width=0.012)
    neck = cylinder(f"{name} neck", (0, 0, 1.73), 0.072, 0.18, palette.skin, parent=root, vertices=32)
    head_joint = empty(f"{name} head joint", (0, 0, 1.93), root)
    jaw = profile_mesh(
        f"{name} jaw",
        (0, 0, 0),
        ((-0.245, 0.095, 0.115), (-0.17, 0.165, 0.16), (-0.02, 0.213, 0.19), (0.10, 0.218, 0.19)),
        palette.skin,
        parent=head_joint,
        sides=40,
    )
    cranium = sphere(f"{name} cranium", (0, 0.018, 0.105), (0.222, 0.196, 0.205), palette.skin, parent=head_joint, segments=40)
    ear_l = sphere(f"{name} ear L", (-0.218, 0.003, -0.005), (0.029, 0.022, 0.061), palette.skin, parent=head_joint, segments=24)
    ear_r = sphere(f"{name} ear R", (0.218, 0.003, -0.005), (0.029, 0.022, 0.061), palette.skin, parent=head_joint, segments=24)

    eye_l = sphere(f"{name} eye white L", (-0.080, -0.184, 0.034), (0.052, 0.018, 0.031), palette.sclera, parent=head_joint, segments=28)
    eye_r = sphere(f"{name} eye white R", (0.080, -0.184, 0.034), (0.052, 0.018, 0.031), palette.sclera, parent=head_joint, segments=28)
    sphere(f"{name} iris L", (-0.080, -0.201, 0.034), (0.022, 0.008, 0.021), palette.eyes, parent=head_joint, segments=24)
    sphere(f"{name} iris R", (0.080, -0.201, 0.034), (0.022, 0.008, 0.021), palette.eyes, parent=head_joint, segments=24)
    sphere(f"{name} pupil L", (-0.080, -0.208, 0.034), (0.009, 0.005, 0.011), palette.pupils, parent=head_joint, segments=20)
    sphere(f"{name} pupil R", (0.080, -0.208, 0.034), (0.009, 0.005, 0.011), palette.pupils, parent=head_joint, segments=20)
    nose = cone(f"{name} nose", (0, -0.205, -0.018), 0.032, 0.125, palette.skin, parent=head_joint)
    nose.rotation_euler.x = 90 * DEG
    mouth_mat = material(f"{name} mouth", (0.18, 0.035, 0.025, 1), roughness=0.7)
    mouth = curve_line(
        f"{name} mouth",
        ((-0.060, -0.198, -0.114), (0, -0.207, -0.120), (0.060, -0.198, -0.114)),
        0.008,
        mouth_mat,
        parent=head_joint,
    )
    brow_l = curve_line(
        f"{name} brow L",
        ((-0.137, -0.190, 0.095), (-0.082, -0.205, 0.108), (-0.030, -0.195, 0.102)),
        0.010,
        palette.brows,
        parent=head_joint,
    )
    brow_r = curve_line(
        f"{name} brow R",
        ((0.030, -0.195, 0.102), (0.082, -0.205, 0.108), (0.137, -0.190, 0.095)),
        0.010,
        palette.brows,
        parent=head_joint,
    )

    # A fitted crown replaces the old cone helmet; Arthur's locks sit over it.
    hair_cap = sphere(f"{name} fitted hair", (0, 0.025, 0.185), (0.221, 0.191, 0.118), palette.hair, parent=head_joint, segments=40)
    curve_line(f"{name} left hairline", ((-0.205, -0.13, 0.13), (-0.16, -0.17, 0.19), (-0.09, -0.185, 0.22)), 0.016, palette.hair, parent=head_joint)
    curve_line(f"{name} right hairline", ((0.205, -0.13, 0.13), (0.16, -0.17, 0.19), (0.09, -0.185, 0.22)), 0.016, palette.hair, parent=head_joint)

    joints: Dict[str, object] = {"head": head_joint}
    for side, sx in (("L", -1), ("R", 1)):
        shoulder = empty(f"{name} shoulder {side}", ((body_width + 0.055) * sx, 0, 1.59), root)
        sphere(f"{name} shoulder cap {side}", (0, 0, -0.025), (0.105, 0.105, 0.13), palette.shirt, parent=shoulder, segments=28)
        upper_arm = segment(f"{name} upper arm {side}", shoulder, 0.39, 0.085, palette.shirt)
        elbow = empty(f"{name} elbow {side}", (0, 0, -0.39), shoulder)
        sphere(f"{name} elbow form {side}", (0, 0, 0), (0.077, 0.068, 0.075), palette.skin, parent=elbow, segments=24)
        forearm = segment(f"{name} forearm {side}", elbow, 0.36, 0.069, palette.skin)
        wrist = empty(f"{name} wrist {side}", (0, 0, -0.36), elbow)
        sphere(f"{name} palm {side}", (0, -0.005, -0.070), (0.074, 0.047, 0.108), palette.skin, parent=wrist, segments=28)
        finger_offsets = (-0.047, -0.016, 0.016, 0.047)
        for finger_index, offset in enumerate(finger_offsets):
            sphere(
                f"{name} finger {side} {finger_index}",
                (offset, -0.008, -0.155 + abs(offset) * 0.22),
                (0.014, 0.014, 0.060 - abs(offset) * 0.18),
                palette.skin,
                parent=wrist,
                segments=16,
            )
        thumb = sphere(f"{name} thumb {side}", (0.074 * sx, -0.005, -0.060), (0.035, 0.026, 0.055), palette.skin, parent=wrist, segments=18)
        thumb.rotation_euler.y = -32 * sx * DEG
        hip = empty(f"{name} hip {side}", (0.135 * sx, 0, 1.00), root)
        sphere(f"{name} hip form {side}", (0, 0, -0.02), (0.135, 0.125, 0.14), palette.trousers, parent=hip, segments=28)
        thigh = segment(f"{name} thigh {side}", hip, 0.48, 0.115, palette.trousers)
        knee = empty(f"{name} knee {side}", (0, 0, -0.48), hip)
        sphere(f"{name} knee form {side}", (0, -0.005, 0), (0.095, 0.087, 0.10), palette.trousers, parent=knee, segments=24)
        shin = segment(f"{name} shin {side}", knee, 0.42, 0.088, palette.trousers)
        foot = sphere(f"{name} foot {side}", (0, -0.072, -0.43), (0.105, 0.180, 0.082), palette.shoes, parent=knee, segments=28)
        joints.update({f"shoulder_{side}": shoulder, f"elbow_{side}": elbow, f"hip_{side}": hip, f"knee_{side}": knee})

    hair: List[object] = []
    if young:
        hair_layout = [
            (-0.170, -0.050, 0.245, 72, -20, 0.29, 0.052),
            (-0.115, -0.115, 0.265, 80, -13, 0.34, 0.058),
            (-0.055, -0.145, 0.280, 84, -6, 0.37, 0.060),
            (0.015, -0.150, 0.284, 86, 3, 0.38, 0.061),
            (0.082, -0.132, 0.274, 82, 11, 0.36, 0.058),
            (0.145, -0.082, 0.255, 76, 19, 0.32, 0.054),
            (-0.175, 0.025, 0.258, 48, -28, 0.31, 0.054),
            (-0.095, 0.060, 0.285, 37, -16, 0.36, 0.060),
            (-0.010, 0.075, 0.298, 29, -4, 0.39, 0.062),
            (0.080, 0.065, 0.288, 35, 12, 0.37, 0.060),
            (0.160, 0.025, 0.260, 48, 25, 0.32, 0.054),
            (0.020, 0.135, 0.266, -24, 5, 0.33, 0.056),
        ]
        for index, (x, y, z, rx, rz, length, radius) in enumerate(hair_layout):
            strand = hair_lock(f"{name} hair lock {index:02d}", (x, y, z), length, radius, palette.hair, parent=head_joint)
            strand.rotation_euler = (rx * DEG, 0, rz * DEG)
            hair.append(strand)

    return {
        "root": root,
        "head": head_joint,
        "torso": torso,
        "pelvis": pelvis,
        "mouth": mouth,
        "brow_l": brow_l,
        "brow_r": brow_r,
        "eye_l": eye_l,
        "eye_r": eye_r,
        "hair": hair,
        "joints": joints,
    }


def create_lab() -> Dict[str, object]:
    floor_mat = material("sealed charcoal floor", (0.075, 0.085, 0.094, 1), metallic=0.12, roughness=0.34)
    wall_mat = material("laboratory walls", (0.26, 0.30, 0.32, 1), metallic=0.08, roughness=0.55)
    trim_mat = material("dark steel trim", (0.025, 0.032, 0.038, 1), metallic=0.72, roughness=0.25)
    white_mat = material("equipment enamel", (0.58, 0.63, 0.65, 1), metallic=0.18, roughness=0.31)
    glass_mat = material("safety glass", (0.16, 0.34, 0.38, 0.24), metallic=0.05, roughness=0.12, alpha=0.24)
    cyan = material("monitor cyan", (0.01, 0.08, 0.10, 1), roughness=0.25, emission=(0.02, 0.55, 0.7, 1), emission_strength=4.0)
    amber = material("warning amber", (0.18, 0.055, 0.005, 1), roughness=0.3, emission=(1.0, 0.13, 0.015, 1), emission_strength=7.0)
    ceiling_glow = material("ceiling diffuser", (0.52, 0.62, 0.67, 1), roughness=0.2, emission=(0.70, 0.88, 1.0, 1), emission_strength=2.2)

    cube("floor", (0, 0, -0.17), (7.5, 5.5, 0.17), floor_mat, bevel_width=0.03)
    cube("back wall", (0, 5.45, 2.6), (7.5, 0.12, 2.75), wall_mat, bevel_width=0.02)
    cube("left wall", (-7.45, 0, 2.6), (0.12, 5.5, 2.75), wall_mat, bevel_width=0.02)
    cube("right wall", (7.45, 0, 2.6), (0.12, 5.5, 2.75), wall_mat, bevel_width=0.02)
    cube("laboratory ceiling", (0, 0, 5.35), (7.5, 5.5, 0.12), wall_mat, bevel_width=0.02)
    for x in (-5.0, -2.5, 0, 2.5, 5.0):
        cube(f"ceiling rib {x}", (x, 0, 5.25), (0.07, 5.4, 0.09), trim_mat, bevel_width=0.015)
    for index, x in enumerate((-4.8, -1.6, 1.6, 4.8)):
        cube(f"visible ceiling light {index}", (x, 0.2, 5.20), (0.88, 0.48, 0.025), ceiling_glow, bevel_width=0.015)

    # Broad inset panels keep the laboratory readable instead of falling into black voids.
    for x in (-6.1, -4.9, 1.0, 2.2, 3.4, 6.2):
        cube(f"back wall panel {x}", (x, 5.29, 3.25), (0.50, 0.035, 1.55), white_mat, bevel_width=0.025)
    for side in (-1, 1):
        x = 7.29 * side
        for y in (-3.9, -2.3, -0.7, 0.9, 2.5, 4.1):
            cube(f"side wall panel {side} {y}", (x, y, 2.6), (0.035, 0.66, 1.95), white_mat, bevel_width=0.025)

    # Observation window and the reinforced test-room door.
    cube("observation glass", (-2.3, 5.28, 3.1), (2.15, 0.035, 1.28), glass_mat, bevel_width=0.01)
    cube("observation frame top", (-2.3, 5.20, 4.42), (2.30, 0.10, 0.07), trim_mat)
    cube("observation frame bottom", (-2.3, 5.20, 1.78), (2.30, 0.10, 0.07), trim_mat)
    cube("door", (4.9, 5.19, 2.15), (1.15, 0.14, 2.15), trim_mat)
    cube("door inset", (4.9, 5.02, 2.4), (0.78, 0.03, 1.25), glass_mat, bevel_width=0.02)

    # Lab benches and equipment banks.
    for index, x in enumerate((-5.4, -3.6, 3.7, 5.4)):
        cube(f"bench {index}", (x, 3.35, 0.72), (0.75, 0.75, 0.72), white_mat)
        cube(f"bench dark top {index}", (x, 3.35, 1.48), (0.78, 0.78, 0.055), trim_mat)
        screen = cube(f"monitor {index}", (x, 3.03, 2.05), (0.50, 0.055, 0.34), cyan, bevel_width=0.025)
        screen.rotation_euler.x = 8 * DEG
    for x in (-6.8, 6.8):
        for z in (0.7, 1.8, 2.9, 4.0):
            cube(f"cabinet {x} {z}", (x, 3.85, z), (0.45, 0.55, 0.46), white_mat)

    # Arthur's test platform and sensor arch.
    cylinder("test dais", (0, 0, 0.05), 1.12, 0.10, trim_mat, vertices=64)
    cylinder("dais light", (0, 0, 0.115), 0.88, 0.035, cyan, vertices=64)
    for x in (-1.35, 1.35):
        cylinder(f"sensor upright {x}", (x, 0.25, 1.45), 0.07, 2.9, trim_mat)
        sphere(f"sensor eye {x}", (x, -0.02, 2.65), (0.15, 0.10, 0.15), cyan, segments=24)
    cube("sensor bridge", (0, 0.25, 2.90), (1.42, 0.08, 0.07), trim_mat)

    # Warning strips make the floor readable during the fight.
    for x in (-2.0, 2.0):
        for y in (-2.5, -1.8, -1.1, -0.4, 0.3, 1.0, 1.7, 2.4):
            marker = cube(f"hazard {x} {y}", (x, y, 0.012), (0.38, 0.055, 0.012), amber, bevel_width=0.005)
            marker.rotation_euler.z = 22 * DEG

    return {"floor": floor_mat, "trim": trim_mat, "equipment": white_mat, "cyan": cyan, "amber": amber}


def create_lighting() -> Dict[str, object]:
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.008, 0.012, 0.018, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.32

    lights: Dict[str, object] = {}
    for index, x in enumerate((-4.8, -1.6, 1.6, 4.8)):
        data = bpy.data.lights.new(f"ceiling light {index}", "AREA")
        data.energy = 1080
        data.color = (0.68, 0.84, 1.0)
        data.shape = "RECTANGLE"
        data.size = 2.2
        data.size_y = 0.6
        obj = bpy.data.objects.new(f"ceiling light {index}", data)
        bpy.context.collection.objects.link(obj)
        obj.location = (x, 0.2, 4.95)
        obj.rotation_euler = (0, 0, 0)
        lights[f"ceiling_{index}"] = obj

    data = bpy.data.lights.new("Arthur underlight", "POINT")
    data.energy = 70
    data.color = (0.04, 0.55, 0.85)
    data.shadow_soft_size = 0.9
    under = bpy.data.objects.new("Arthur underlight", data)
    bpy.context.collection.objects.link(under)
    under.location = (0, 0, 0.35)
    lights["under"] = under

    data = bpy.data.lights.new("red emergency", "AREA")
    data.energy = 0
    data.color = (1.0, 0.015, 0.008)
    data.shape = "DISK"
    data.size = 5.0
    red = bpy.data.objects.new("red emergency", data)
    bpy.context.collection.objects.link(red)
    red.location = (0, 2.0, 4.8)
    red.rotation_euler = (0, 0, 0)
    lights["red"] = red

    data = bpy.data.lights.new("soft camera fill", "AREA")
    data.energy = 620
    data.color = (0.78, 0.86, 1.0)
    data.shape = "DISK"
    data.size = 4.0
    fill = bpy.data.objects.new("soft camera fill", data)
    bpy.context.collection.objects.link(fill)
    fill.location = (0, -4.2, 3.2)
    look_at(fill, (0, 0.2, 1.25))
    lights["fill"] = fill
    return lights


def create_debris(materials: Dict[str, object]) -> List[object]:
    rng = random.Random(1701)
    debris: List[object] = []
    source_positions = [
        (-5.4, 3.0, 1.65), (-4.9, 3.4, 1.62), (-3.7, 3.1, 1.68),
        (3.6, 3.0, 1.66), (4.0, 3.5, 1.62), (5.2, 3.2, 1.64),
        (-3.0, -1.5, 0.10), (3.0, -1.2, 0.10), (-4.2, 0.7, 0.10),
        (4.4, 0.2, 0.10), (-2.5, 2.0, 0.10), (2.7, 2.1, 0.10),
    ]
    for index in range(24):
        source = source_positions[index % len(source_positions)]
        jittered = (source[0] + rng.uniform(-0.28, 0.28), source[1] + rng.uniform(-0.22, 0.22), source[2])
        if index % 3 == 0:
            obj = cylinder(f"floating canister {index:02d}", jittered, 0.055, 0.32, materials["equipment"], vertices=16)
        else:
            obj = cube(f"floating instrument {index:02d}", jittered, (0.10, 0.06, 0.035), materials["trim"], bevel_width=0.015)
        debris.append(obj)
    return debris


def animate_arthur(arthur: Dict[str, object]) -> None:
    root = arthur["root"]
    head = arthur["head"]
    joints = arthur["joints"]

    key_location(root, 1, (0, 0, 0))
    key_rotation(root, 1, (0, 0, 0))
    key_rotation(head, 1, (-8, 0, 0))
    key_rotation(head, 58, (-8, 0, 0))
    key_rotation(head, 66, (5, 0, 0))
    key_rotation(head, 78, (-2, 0, 0))
    key_rotation(head, 150, (-2, 0, 0))

    # His shoulders settle rather than flaring into a conventional fighting pose.
    key_rotation(joints["shoulder_L"], 1, (2, 0, -3))
    key_rotation(joints["shoulder_R"], 1, (2, 0, 3))
    key_rotation(joints["shoulder_L"], 74, (0, 0, -7))
    key_rotation(joints["shoulder_R"], 74, (0, 0, 7))
    key_rotation(joints["shoulder_L"], 220, (-10, 0, -12))
    key_rotation(joints["shoulder_R"], 220, (7, 0, 10))

    # The hair lies across the crown, then rises in staggered clumps.
    for index, strand in enumerate(arthur["hair"]):
        initial = tuple(v / DEG for v in strand.rotation_euler)
        key_rotation(strand, 1, initial)
        key_rotation(strand, 64 + index % 3, initial)
        upright = (rng_sign(index) * (2 + index % 4), rng_sign(index + 1) * (1 + index % 3), initial[2] * 0.22)
        key_rotation(strand, 70 + index % 4, upright)
        # Each lock jitters on its own phase, like separate parts of one field.
        for pulse_frame in (82, 96, 114, 139, 171, 214, 266, 327, 392, FRAME_END):
            phase = index * 1.71 + pulse_frame * 0.21
            flicker = (
                upright[0] + math.sin(phase) * (2.4 + index % 3),
                upright[1] + math.cos(phase * 0.81) * (1.5 + index % 2),
                upright[2] + math.sin(phase * 0.43) * 3.2,
            )
            key_rotation(strand, pulse_frame + index % 3, flicker)

    # A colder, tighter expression: lowered brows and a nearly erased mouth.
    key_rotation(arthur["brow_l"], 1, (0, 0, 2))
    key_rotation(arthur["brow_r"], 1, (0, 0, -2))
    key_rotation(arthur["brow_l"], 76, (0, 0, -10))
    key_rotation(arthur["brow_r"], 76, (0, 0, 10))
    key_scale(arthur["mouth"], 1, (1.0, 1.0, 1.0))
    key_scale(arthur["mouth"], 78, (0.72, 1.0, 0.58))

    # Small, unnaturally fast reorientations during the attack.
    key_rotation(head, 170, (-2, 0, 0))
    key_rotation(head, 176, (-1, 0, -38))
    key_rotation(head, 205, (-1, 0, -38))
    key_rotation(head, 211, (0, 0, 42))
    key_rotation(head, 270, (0, 0, 42))
    key_rotation(head, 276, (-4, 0, 0))
    key_rotation(head, FRAME_END, (-4, 0, 0))


def rng_sign(index: int) -> int:
    return -1 if index % 2 else 1


def animate_debris(debris: Iterable[object]) -> None:
    for index, obj in enumerate(debris):
        start = obj.location.copy()
        angle = (index / 24.0) * math.tau + (index % 3) * 0.17
        radius = 1.45 + (index % 4) * 0.43
        height = 0.75 + (index % 7) * 0.43
        target = (math.cos(angle) * radius, math.sin(angle) * radius * 0.72, height)
        drift = (math.cos(angle + 0.16) * radius, math.sin(angle + 0.16) * radius * 0.72, height + 0.09 * rng_sign(index))
        key_location(obj, 1, start)
        key_location(obj, 67 + index % 6, start)
        key_location(obj, 132 + index * 2, target)
        key_location(obj, 260, drift)
        key_location(obj, FRAME_END, target)
        key_rotation(obj, 1, (0, 0, index * 13))
        key_rotation(obj, 150, (index * 19, index * 11, index * 31))
        key_rotation(obj, FRAME_END, (index * 31, index * 23, index * 47))


def animate_guard_one(guard: Dict[str, object], baton: object) -> None:
    root = guard["root"]
    j = guard["joints"]
    key_location(root, 1, (5.4, 2.0, 0))
    key_location(root, 145, (5.4, 2.0, 0))
    key_location(root, 175, (2.0, 0.75, 0))
    key_location(root, 192, (1.25, 0.28, 0))
    key_rotation(root, 1, (0, 0, -68))
    key_rotation(root, 192, (0, 0, -68))

    # Running stride and a baton strike that stops short of Arthur.
    for frame, swing in ((145, -18), (155, 24), (165, -24), (175, 20), (185, -12)):
        key_rotation(j["hip_L"], frame, (swing, 0, 0))
        key_rotation(j["hip_R"], frame, (-swing, 0, 0))
        key_rotation(j["shoulder_L"], frame, (-swing * 0.7, 0, 0))
    key_rotation(j["shoulder_R"], 145, (-30, 0, 12))
    key_rotation(j["shoulder_R"], 186, (-92, 0, 18))
    key_rotation(j["shoulder_R"], 198, (-92, 0, 18))

    key_location(baton, 1, (5.1, 1.78, 1.45))
    key_location(baton, 176, (2.0, 0.48, 1.70))
    key_location(baton, 194, (0.72, -0.05, 1.52))
    key_location(baton, 204, (0.72, -0.05, 1.52))
    key_location(baton, 225, (4.9, 3.0, 2.70))
    key_rotation(baton, 1, (0, 0, -68))
    key_rotation(baton, 194, (88, 12, -40))
    key_rotation(baton, 225, (380, 210, 290))

    # Arthur redirects the guard into the padded side wall without pursuing him.
    key_location(root, 199, (1.25, 0.28, 0))
    key_location(root, 216, (5.7, 1.15, 0.62))
    key_rotation(root, 199, (0, 0, -68))
    key_rotation(root, 216, (12, 79, 28))
    key_location(root, 238, (5.9, 1.25, 0.18))
    key_rotation(root, 238, (2, 88, 18))


def animate_guard_two(guard: Dict[str, object]) -> None:
    root = guard["root"]
    j = guard["joints"]
    key_location(root, 1, (-5.8, 1.3, 0))
    key_location(root, 210, (-5.8, 1.3, 0))
    key_location(root, 245, (-1.65, 0.48, 0))
    key_location(root, 263, (-1.05, 0.20, 0))
    key_rotation(root, 1, (0, 0, 70))
    key_rotation(root, 263, (0, 0, 70))
    for frame, swing in ((210, -20), (220, 24), (230, -24), (240, 20), (250, -10)):
        key_rotation(j["hip_L"], frame, (swing, 0, 0))
        key_rotation(j["hip_R"], frame, (-swing, 0, 0))
        key_rotation(j["shoulder_L"], frame, (-swing * 0.8, 0, 0))
        key_rotation(j["shoulder_R"], frame, (swing * 0.8, 0, 0))

    # His momentum disappears mid-step; a head snap precedes a non-lethal collapse.
    key_rotation(guard["head"], 258, (0, 0, 0))
    key_rotation(guard["head"], 264, (-18, 4, -28))
    key_rotation(guard["head"], 272, (10, -3, 22))
    key_location(root, 274, (-1.05, 0.20, 0))
    key_location(root, 292, (-1.35, 0.42, 0.38))
    key_rotation(root, 274, (0, 0, 70))
    key_rotation(root, 292, (84, 12, 68))
    key_location(root, 320, (-1.55, 0.52, 0.16))
    key_rotation(root, 320, (91, 4, 72))


def animate_lights(lights: Dict[str, object]) -> None:
    for index in range(4):
        light = lights[f"ceiling_{index}"]
        key_energy(light, 1, 1080)
        key_energy(light, 62 + index, 1080)
        key_energy(light, 64 + index, 80)
        key_energy(light, 67 + index, 1180)
        key_energy(light, 72 + index, 110)
        key_energy(light, 76 + index, 760)
    key_energy(lights["under"], 1, 70)
    key_energy(lights["under"], 64, 70)
    key_energy(lights["under"], 95, 320)
    key_energy(lights["under"], FRAME_END, 230)
    key_energy(lights["red"], 1, 0)
    key_energy(lights["red"], 75, 0)
    key_energy(lights["red"], 92, 430)
    key_energy(lights["red"], FRAME_END, 250)


def look_at(camera: object, point: Sequence[float]) -> None:
    direction = Vector(point) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def camera_key(camera: object, frame: int, location: Sequence[float], target: Sequence[float], lens: float) -> None:
    camera.location = location
    camera.data.lens = lens
    look_at(camera, target)
    camera.keyframe_insert(data_path="location", frame=frame)
    camera.keyframe_insert(data_path="rotation_euler", frame=frame)
    camera.data.keyframe_insert(data_path="lens", frame=frame)


def create_camera() -> object:
    data = bpy.data.cameras.new("Strawberry camera")
    data.lens = 48
    data.sensor_width = 36
    data.dof.use_dof = True
    data.dof.focus_distance = 10.0
    data.dof.aperture_fstop = 4.0
    cam = bpy.data.objects.new("Strawberry camera", data)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam

    shots = [
        (1, 58, (0.2, -12.8, 4.1), (0.0, -11.8, 3.8), (0, 0.4, 1.25), (0, 0.2, 1.35), 46),
        (59, 104, (-1.6, -4.6, 2.25), (-1.2, -4.0, 2.35), (0, 0, 1.90), (0, 0, 1.98), 66),
        (105, 152, (2.8, -6.0, 1.05), (2.4, -5.5, 1.25), (0, 0.1, 1.55), (0, 0.1, 1.75), 42),
        (153, 238, (0.0, -11.2, 3.4), (0.8, -10.5, 3.1), (0.4, 0.7, 1.2), (0.8, 0.8, 1.25), 39),
        (239, 322, (-0.8, -8.0, 2.4), (-0.2, -7.4, 2.2), (-0.2, 0.4, 1.3), (-0.4, 0.5, 1.15), 50),
        (323, 390, (3.9, -5.2, 2.45), (3.2, -4.7, 2.35), (0, 0.1, 1.80), (0, 0.0, 1.90), 62),
        (391, FRAME_END, (0.0, -10.8, 4.6), (0.0, -9.7, 4.25), (0, 0.5, 1.5), (0, 0.35, 1.55), 43),
    ]
    for start, end, loc_a, loc_b, target_a, target_b, lens in shots:
        camera_key(cam, start, loc_a, target_a, lens)
        camera_key(cam, end, loc_b, target_b, lens)
    set_interpolation(cam, "LINEAR")
    if cam.data.animation_data and cam.data.animation_data.action:
        for curve in cam.data.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    return cam


def add_baton(materials: Dict[str, object]) -> object:
    baton = empty("guard shock baton", (5.1, 1.78, 1.45))
    cylinder("baton shaft", (0, 0, 0), 0.045, 0.66, materials["trim"], parent=baton, vertices=20)
    glow = material("baton electric blue", (0.01, 0.12, 0.18, 1), emission=(0.05, 0.55, 1.0, 1), emission_strength=8.0, roughness=0.2)
    cylinder("baton emitter", (0, 0, 0.32), 0.058, 0.10, glow, parent=baton, vertices=20)
    return baton


def configure_render() -> None:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 32
        scene.eevee.use_gtao = True
        scene.eevee.gtao_distance = 3
        scene.eevee.gtao_factor = 1.2
    scene.render.image_settings.color_mode = "RGB"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            scene.view_settings.look = look
            break
        except Exception:
            continue


def build_scene() -> None:
    reset_scene()
    configure_render()
    materials = create_lab()
    lights = create_lighting()

    arthur_palette = make_palette(
        "Arthur",
        (0.10, 0.14, 0.17, 1),
        hair_color=(0.018, 0.010, 0.008, 1),
        skin_color=(0.58, 0.35, 0.25, 1),
    )
    guard_palette = make_palette(
        "guard",
        (0.045, 0.065, 0.082, 1),
        hair_color=(0.055, 0.038, 0.025, 1),
        skin_color=(0.67, 0.47, 0.36, 1),
    )
    guard_two_palette = make_palette(
        "guard two",
        (0.055, 0.068, 0.080, 1),
        hair_color=(0.014, 0.012, 0.010, 1),
        skin_color=(0.34, 0.20, 0.15, 1),
    )
    arthur = create_character("Arthur", (0, 0, 0), arthur_palette, size=0.94, young=True)
    guard_one = create_character("Guard One", (5.4, 2.0, 0), guard_palette, size=1.04)
    guard_two = create_character("Guard Two", (-5.8, 1.3, 0), guard_two_palette, size=1.01)
    debris = create_debris(materials)
    baton = add_baton(materials)

    animate_arthur(arthur)
    animate_debris(debris)
    animate_guard_one(guard_one, baton)
    animate_guard_two(guard_two)
    animate_lights(lights)
    create_camera()

    for obj in bpy.context.scene.objects:
        if obj.animation_data and obj.animation_data.action and obj.type != "CAMERA":
            set_interpolation(obj, "BEZIER")

    scene = bpy.context.scene
    scene.frame_set(1)
    scene.render.filepath = "//render/frames/frame_"
    scene["strawberry_films_project"] = "Arthur: Lab Break"
    scene["duration_seconds"] = FRAME_END / FPS
    scene["production_note"] = "Procedural first-pass animation; voices and music intentionally omitted."


def main() -> None:
    args = parse_args()
    build_scene()
    destination = os.path.abspath(args.build)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=destination)
    if args.preview:
        bpy.context.scene.frame_set(240)
        preview_path = os.path.splitext(destination)[0] + "-preview.png"
        bpy.context.scene.render.filepath = preview_path
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
