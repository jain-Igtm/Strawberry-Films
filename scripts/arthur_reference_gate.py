#!/usr/bin/env python3
"""Reference-driven Arthur render gate.

This pass keeps the existing choreography and lab pipeline while replacing the
chibi anime base, glowing eyes, helmet hair, and bodysuit silhouette with a
normal-proportioned cel-shaded young male matching the approved reference:
messy black hair, pale restrained face, gray shirt, oversized black jacket,
dark navy trousers, and brown shoes.
"""

from __future__ import annotations

import importlib
import json
import math
import sys
import types
from pathlib import Path

import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import arthur_anime_gate as legacy


ACTIVE_BODY: bpy.types.Object | None = None
ORIGINAL_ANIMATE_TRANSFORMATION = legacy.animate_transformation


def local_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    coordinates = [vertex.co for vertex in obj.data.vertices]
    low = Vector(tuple(min(value[index] for value in coordinates) for index in range(3)))
    high = Vector(tuple(max(value[index] for value in coordinates) for index in range(3)))
    return low, high


def material_palette(character_name: str) -> tuple[bpy.types.Material, bpy.types.Material, bpy.types.Material, bpy.types.Material]:
    skin = legacy.cel_material(
        f"{character_name}_CelSkin",
        (0.24, 0.16, 0.15, 1.0),
        (0.70, 0.52, 0.46, 1.0),
        (0.92, 0.78, 0.72, 1.0),
    )
    mouth = legacy.cel_material(
        f"{character_name}_Mouth",
        (0.06, 0.018, 0.022, 1.0),
        (0.20, 0.055, 0.060, 1.0),
        (0.42, 0.16, 0.15, 1.0),
    )
    eyes_name = "Arthur_AnimeEyes" if character_name == "Arthur" else f"{character_name}_Eyes"
    eyes = legacy.emission_material(eyes_name, (0.045, 0.032, 0.030, 1.0), 0.04)
    eyes.diffuse_color = (0.045, 0.032, 0.030, 1.0)
    lashes = legacy.cel_material(
        f"{character_name}_Lashes",
        (0.004, 0.004, 0.005, 1.0),
        (0.012, 0.012, 0.014, 1.0),
        (0.035, 0.035, 0.040, 1.0),
    )
    return skin, mouth, eyes, lashes


def restyle_material_slots(body: bpy.types.Object, character_name: str) -> None:
    skin, mouth, eyes, lashes = material_palette(character_name)
    for index, original in enumerate(list(body.data.materials)):
        source_name = original.name.lower() if original else ""
        if "lash" in source_name:
            replacement = lashes
        elif "eye" in source_name or "iris" in source_name or "sclera" in source_name:
            replacement = eyes
        elif any(token in source_name for token in ("mouth", "tongue", "teeth", "gum")):
            replacement = mouth
        else:
            replacement = skin
        body.data.materials[index] = replacement
        print("REFERENCE_MATERIAL", character_name, index, source_name, replacement.name)


def slim_reference_body(body: bpy.types.Object) -> None:
    low, high = local_bounds(body)
    height = high.z - low.z
    neck_line = low.z + height * 0.83
    hip_line = low.z + height * 0.48
    for vertex in body.data.vertices:
        z = vertex.co.z
        if z < neck_line:
            vertex.co.y *= 0.94
            if z > hip_line:
                vertex.co.x *= 0.90
            else:
                vertex.co.x *= 0.94
    body.data.update()


def append_reference_body(mblab_root: Path, character_name: str = "Arthur") -> bpy.types.Object:
    global ACTIVE_BODY
    library = mblab_root / "data" / "humanoid_library.blend"
    template_name = "MBLab_human_male"
    if not library.is_file():
        raise FileNotFoundError(f"MB-Lab body library is missing: {library}")
    with bpy.data.libraries.load(str(library), link=False) as (source, target):
        if template_name not in source.objects:
            raise RuntimeError(f"{template_name!r} is absent from {library}")
        target.objects = [template_name]
    body = target.objects[0]
    if body is None:
        raise RuntimeError("Blender returned an empty human male body")
    bpy.context.collection.objects.link(body)
    body.name = f"{character_name}_ReferenceBody"
    body.hide_render = False
    body.hide_viewport = False
    for polygon in body.data.polygons:
        polygon.use_smooth = True
    slim_reference_body(body)
    restyle_material_slots(body, character_name)
    ACTIVE_BODY = body
    low, high = local_bounds(body)
    print("REFERENCE_BODY", character_name, tuple(low), tuple(high), "vertices", len(body.data.vertices))
    return body


def rig_reference_body(
    body: bpy.types.Object,
    mblab_root: Path,
    character_name: str = "Arthur",
) -> bpy.types.Object:
    package_name = "strawberry_mblab_reference_vendor"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(mblab_root)]
        package.__package__ = package_name
        sys.modules[package_name] = package
    file_ops = importlib.import_module(f"{package_name}.file_ops")
    skeletonengine = importlib.import_module(f"{package_name}.skeletonengine")
    file_ops.set_data_path("data")
    with (mblab_root / "data" / "characters_config.json").open(encoding="utf-8") as handle:
        character_config = json.load(handle)["m_ca01"]
    skeleton = skeletonengine.SkeletonEngine(body, character_config, "base")
    skeleton.fit_joints()
    armature = skeleton.get_armature()
    if not armature:
        raise RuntimeError("MB-Lab did not create the human-male armature")
    armature.name = f"{character_name}_ReferenceRig"
    armature.show_in_front = True
    armature.hide_render = True
    print("REFERENCE_RIG", character_name, "bones", len(armature.data.bones))
    return armature


def reference_hair_cap(material: bpy.types.Material) -> bpy.types.Object:
    if ACTIVE_BODY is None:
        raise RuntimeError("Hair requested before a body was created")
    low, high = local_bounds(ACTIVE_BODY)
    height = high.z - low.z
    center = Vector((0.0, -height * 0.008, high.z - height * 0.105))
    radius_x = height * 0.094
    radius_y = height * 0.084
    radius_z = height * 0.112
    rings = 11
    sides = 40
    vertices: list[tuple[float, float, float]] = []
    for ring in range(rings):
        theta = (math.pi * 0.47) * ring / (rings - 1)
        radial = math.sin(theta)
        for side in range(sides):
            phi = math.tau * side / sides
            x = center.x + radius_x * radial * math.cos(phi)
            y = center.y + radius_y * radial * math.sin(phi)
            z = center.z + radius_z * math.cos(theta)
            vertices.append((x, y, z))
    faces: list[tuple[int, ...]] = []
    for ring in range(rings - 1):
        for side in range(sides):
            following = (side + 1) % sides
            faces.append(
                (
                    ring * sides + side,
                    ring * sides + following,
                    (ring + 1) * sides + following,
                    (ring + 1) * sides + side,
                )
            )
    cap = legacy.mesh_object("Arthur_HairCap", vertices, faces, material)
    bevel = cap.modifiers.new("Soft_Hair_Edges", "BEVEL")
    bevel.width = height * 0.0025
    bevel.segments = 2
    return cap


def reference_hair() -> list[bpy.types.Object]:
    if ACTIVE_BODY is None:
        raise RuntimeError("Hair requested before a body was created")
    low, high = local_bounds(ACTIVE_BODY)
    height = high.z - low.z
    top = high.z + height * 0.012
    center_z = high.z - height * 0.105
    front_y = -height * 0.080
    hair = legacy.cel_material(
        "Arthur_CelHair",
        (0.003, 0.003, 0.004, 1.0),
        (0.012, 0.012, 0.016, 1.0),
        (0.060, 0.060, 0.075, 1.0),
    )
    pieces = [reference_hair_cap(hair)]

    fringe_offsets = [-0.072, -0.052, -0.033, -0.014, 0.006, 0.026, 0.047, 0.067]
    for index, x_factor in enumerate(fringe_offsets):
        x = height * x_factor
        sway = height * (0.010 if index % 2 else -0.008)
        end_drop = height * (0.058 + 0.010 * (index % 3))
        centers = [
            (x * 0.72, -height * 0.020, top - height * 0.012),
            (x + sway * 0.30, front_y * 0.72, center_z + height * 0.055),
            (x + sway, front_y * 1.10, center_z + height * 0.005),
            (x + sway * 1.25, front_y * 1.20, center_z - end_drop),
        ]
        widths = [height * 0.020, height * 0.018, height * 0.014, height * 0.003]
        pieces.append(legacy.hair_blade(f"Fringe_{index:02d}", centers, widths, hair, depth=height * 0.011))

    side_specs = [
        (-0.092, -0.030, -0.020),
        (-0.105, 0.000, -0.045),
        (-0.086, 0.032, -0.060),
        (0.092, -0.030, -0.018),
        (0.105, 0.002, -0.044),
        (0.086, 0.034, -0.058),
    ]
    for index, (xf, yf, zf) in enumerate(side_specs):
        sign = -1.0 if xf < 0 else 1.0
        centers = [
            (height * xf * 0.55, height * yf * 0.2, top - height * 0.010),
            (height * xf * 0.85, height * yf, center_z + height * 0.045),
            (height * xf, -height * 0.012, center_z + height * zf),
            (height * (xf + sign * 0.008), -height * 0.045, center_z + height * (zf - 0.035)),
        ]
        widths = [height * 0.019, height * 0.017, height * 0.012, height * 0.003]
        pieces.append(legacy.hair_blade(f"SideLock_{index:02d}", centers, widths, hair, depth=height * 0.012))

    crown_specs = [(-0.050, 0.020), (-0.018, 0.038), (0.022, 0.035), (0.055, 0.015)]
    for index, (xf, yf) in enumerate(crown_specs):
        centers = [
            (height * xf * 0.45, height * yf * 0.2, top - height * 0.006),
            (height * xf, height * yf, top + height * 0.018),
            (height * (xf * 1.20), height * (yf + 0.015), top - height * 0.012),
        ]
        widths = [height * 0.018, height * 0.015, height * 0.003]
        pieces.append(legacy.hair_blade(f"CrownLock_{index:02d}", centers, widths, hair, depth=height * 0.012))
    return pieces


def open_jacket_shell(body: bpy.types.Object, material: bpy.types.Material) -> bpy.types.Object:
    low, high = local_bounds(body)
    height = high.z - low.z
    z_values = [low.z + height * 0.47, low.z + height * 0.60, low.z + height * 0.72, low.z + height * 0.80]
    radii = [
        (height * 0.155, height * 0.090),
        (height * 0.160, height * 0.092),
        (height * 0.172, height * 0.098),
        (height * 0.180, height * 0.104),
    ]
    gap = math.radians(36.0)
    sides = 30
    angles = [(-math.pi / 2 + gap) + (math.tau - 2 * gap) * i / sides for i in range(sides + 1)]
    vertices: list[tuple[float, float, float]] = []
    for z, (rx, ry) in zip(z_values, radii):
        for angle in angles:
            vertices.append((rx * math.cos(angle), ry * math.sin(angle), z))
    faces: list[tuple[int, ...]] = []
    row = len(angles)
    for ring in range(len(z_values) - 1):
        for index in range(len(angles) - 1):
            a = ring * row + index
            faces.append((a, a + 1, a + 1 + row, a + row))
    shell = legacy.mesh_object("Arthur_OversizedJacket", vertices, faces, material)
    solid = shell.modifiers.new("Jacket_Thickness", "SOLIDIFY")
    solid.thickness = height * 0.006
    bevel = shell.modifiers.new("Jacket_Soften", "BEVEL")
    bevel.width = height * 0.004
    bevel.segments = 2
    return shell


def reference_costume(body: bpy.types.Object) -> list[bpy.types.Object]:
    low, high = local_bounds(body)
    height = high.z - low.z
    jacket = legacy.cel_material(
        "Arthur_BlackJacket",
        (0.004, 0.005, 0.007, 1.0),
        (0.018, 0.020, 0.026, 1.0),
        (0.070, 0.075, 0.090, 1.0),
    )
    shirt = legacy.cel_material(
        "Arthur_GrayShirt",
        (0.055, 0.060, 0.067, 1.0),
        (0.20, 0.22, 0.24, 1.0),
        (0.43, 0.45, 0.47, 1.0),
    )
    trousers = legacy.cel_material(
        "Arthur_NavyTrousers",
        (0.008, 0.012, 0.020, 1.0),
        (0.030, 0.045, 0.075, 1.0),
        (0.090, 0.115, 0.160, 1.0),
    )
    shoes = legacy.cel_material(
        "Arthur_BrownShoes",
        (0.030, 0.018, 0.012, 1.0),
        (0.13, 0.075, 0.045, 1.0),
        (0.29, 0.18, 0.11, 1.0),
    )
    jacket_index = len(body.data.materials)
    body.data.materials.append(jacket)
    shirt_index = len(body.data.materials)
    body.data.materials.append(shirt)
    trousers_index = len(body.data.materials)
    body.data.materials.append(trousers)
    shoe_index = len(body.data.materials)
    body.data.materials.append(shoes)

    for polygon in body.data.polygons:
        center = sum((body.data.vertices[index].co for index in polygon.vertices), Vector()) / len(polygon.vertices)
        zf = (center.z - low.z) / height
        if zf < 0.075:
            polygon.material_index = shoe_index
        elif zf < 0.49:
            polygon.material_index = trousers_index
        elif 0.49 <= zf < 0.80:
            is_sleeve = abs(center.x) > height * 0.105
            is_jacket_side_or_back = abs(center.x) > height * 0.075 or center.y > 0.0
            polygon.material_index = jacket_index if (is_sleeve or is_jacket_side_or_back) else shirt_index

    shell = open_jacket_shell(body, jacket)
    front_y = -height * 0.090
    lapels: list[bpy.types.Object] = []
    for side in (-1.0, 1.0):
        lapel = legacy.cube_object(
            f"Arthur_JacketLapel_{'L' if side < 0 else 'R'}",
            (side * height * 0.072, front_y, low.z + height * 0.665),
            (height * 0.025, height * 0.008, height * 0.145),
            jacket,
            height * 0.003,
        )
        lapel.rotation_euler.y = math.radians(side * 8.0)
        lapel.rotation_euler.z = math.radians(side * 7.0)
        lapels.append(lapel)
    return [shell, *lapels]


def reference_transformation(
    armature: bpy.types.Object,
    hair: list[bpy.types.Object],
    mblab_root: Path,
) -> None:
    ORIGINAL_ANIMATE_TRANSFORMATION(armature, hair, mblab_root)
    eye_material = bpy.data.materials.get("Arthur_AnimeEyes")
    if eye_material and eye_material.use_nodes:
        emission = next((node for node in eye_material.node_tree.nodes if node.type == "EMISSION"), None)
        if emission:
            strength = emission.inputs["Strength"]
            strength.default_value = 0.04
            strength.keyframe_insert(data_path="default_value", frame=1)
            strength.keyframe_insert(data_path="default_value", frame=43)
            strength.default_value = 0.0
            strength.keyframe_insert(data_path="default_value", frame=58)
            strength.keyframe_insert(data_path="default_value", frame=110)


def install_reference_overrides() -> None:
    legacy.append_anime_body = append_reference_body
    legacy.rig_anime_body = rig_reference_body
    legacy.hair_cap = reference_hair_cap
    legacy.create_hair = reference_hair
    legacy.create_costume = reference_costume
    legacy.animate_transformation = reference_transformation


def main() -> None:
    install_reference_overrides()
    legacy.main()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.show_specular_highlight = False
    if hasattr(scene.display.shading, "show_outline"):
        scene.display.shading.show_outline = True
        scene.display.shading.outline_color = (0.008, 0.008, 0.012)
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 75
    scene["arthur_quality_gate"] = "approved normal-proportioned reference silhouette"
    scene["arthur_reference"] = "messy black hair, pale face, gray shirt, black oversized jacket, navy trousers, brown shoes"
    args = legacy.cli()
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.blend).resolve()))


if __name__ == "__main__":
    main()
