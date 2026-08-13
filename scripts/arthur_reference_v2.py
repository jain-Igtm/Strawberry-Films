#!/usr/bin/env python3
"""Second reference-driven Arthur pass.

Keep the existing lab/fight animation, but fix the character gate: normal human
proportions, readable face, restrained anime eyes, thin messy black hair and a
simple reference-colored wardrobe. No chibi body, glowing cyan eyes, helmet hair,
or oversized jacket geometry.
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector

import arthur_reference_gate as reference

legacy = reference.legacy
ORIGINAL_CONFIGURE_RENDER = legacy.configure_render


def mat(name: str, shadow, base, light):
    material = legacy.cel_material(name, shadow, base, light)
    material.diffuse_color = base
    return material


def fix_face_materials(body: bpy.types.Object, character_name: str) -> None:
    skin = mat(
        f"{character_name}_SkinV2",
        (0.23, 0.15, 0.14, 1.0),
        (0.69, 0.51, 0.45, 1.0),
        (0.91, 0.76, 0.70, 1.0),
    )
    lashes = mat(
        f"{character_name}_LashesV2",
        (0.002, 0.002, 0.003, 1.0),
        (0.008, 0.008, 0.010, 1.0),
        (0.020, 0.020, 0.025, 1.0),
    )
    sclera = mat(
        f"{character_name}_ScleraV2",
        (0.50, 0.46, 0.44, 1.0),
        (0.82, 0.78, 0.75, 1.0),
        (0.95, 0.92, 0.90, 1.0),
    )
    iris_name = "Arthur_AnimeEyes" if character_name == "Arthur" else f"{character_name}_IrisV2"
    iris = mat(
        iris_name,
        (0.010, 0.007, 0.006, 1.0),
        (0.045, 0.030, 0.025, 1.0),
        (0.11, 0.075, 0.060, 1.0),
    )
    pupil = mat(
        f"{character_name}_PupilV2",
        (0.001, 0.001, 0.001, 1.0),
        (0.004, 0.004, 0.005, 1.0),
        (0.012, 0.012, 0.014, 1.0),
    )
    mouth = mat(
        f"{character_name}_MouthV2",
        (0.045, 0.012, 0.016, 1.0),
        (0.15, 0.040, 0.045, 1.0),
        (0.32, 0.095, 0.095, 1.0),
    )

    # MB-Lab human male material slot layout is stable in the pinned 1_8_1 data.
    # 0 lashes, 1 generic skin, 2 pupil, 3 eye/sclera, 4 cornea, 5 iris,
    # 6 skin, 7 tongue, 8 teeth, 9 nails.
    replacements = {
        0: lashes,
        1: skin,
        2: pupil,
        3: sclera,
        4: sclera,
        5: iris,
        6: skin,
        7: mouth,
        8: sclera,
        9: skin,
    }
    for index, replacement in replacements.items():
        if index < len(body.data.materials):
            body.data.materials[index] = replacement


def append_body_v2(mblab_root: Path, character_name: str = "Arthur") -> bpy.types.Object:
    body = reference.append_reference_body(mblab_root, character_name)
    fix_face_materials(body, character_name)
    return body


def clean_hair_cap(material: bpy.types.Material) -> bpy.types.Object:
    # A compact skull cap. It never extends down across the face.
    center = Vector((0.0, -0.015, 1.675))
    radius_x, radius_y, radius_z = 0.165, 0.145, 0.185
    rings = 12
    sides = 44
    vertices = []
    for ring in range(rings):
        theta = (math.pi * 0.50) * ring / (rings - 1)
        radial = math.sin(theta)
        for side in range(sides):
            phi = math.tau * side / sides
            vertices.append(
                (
                    center.x + radius_x * radial * math.cos(phi),
                    center.y + radius_y * radial * math.sin(phi),
                    center.z + radius_z * math.cos(theta),
                )
            )
    faces = []
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
    bevel = cap.modifiers.new("HairCap_Soften", "BEVEL")
    bevel.width = 0.003
    bevel.segments = 2
    return cap


def clean_hair() -> list[bpy.types.Object]:
    hair = mat(
        "Arthur_HairV2",
        (0.002, 0.002, 0.003, 1.0),
        (0.010, 0.010, 0.014, 1.0),
        (0.045, 0.045, 0.060, 1.0),
    )
    pieces = [clean_hair_cap(hair)]

    # Thin overlapping locks, enough to create the messy reference silhouette while
    # leaving the eyes, nose and lower face readable.
    locks = [
        ("Fringe_L3", [(-0.120, -0.075, 1.820), (-0.130, -0.165, 1.755), (-0.115, -0.205, 1.675)], [0.017, 0.013, 0.002]),
        ("Fringe_L2", [(-0.080, -0.082, 1.835), (-0.085, -0.175, 1.760), (-0.072, -0.207, 1.650)], [0.019, 0.014, 0.002]),
        ("Fringe_L1", [(-0.038, -0.086, 1.842), (-0.045, -0.180, 1.770), (-0.034, -0.208, 1.690)], [0.018, 0.013, 0.002]),
        ("Fringe_C",  [(0.005, -0.087, 1.845), (0.000, -0.182, 1.770), (0.014, -0.209, 1.665)], [0.019, 0.014, 0.002]),
        ("Fringe_R1", [(0.048, -0.084, 1.840), (0.055, -0.178, 1.765), (0.067, -0.207, 1.685)], [0.018, 0.013, 0.002]),
        ("Fringe_R2", [(0.090, -0.078, 1.830), (0.100, -0.168, 1.750), (0.112, -0.203, 1.675)], [0.017, 0.012, 0.002]),
        ("Side_L", [(-0.145, -0.035, 1.790), (-0.168, -0.105, 1.720), (-0.165, -0.155, 1.625)], [0.018, 0.013, 0.002]),
        ("Side_R", [(0.145, -0.035, 1.790), (0.168, -0.105, 1.720), (0.165, -0.155, 1.625)], [0.018, 0.013, 0.002]),
        ("Crown_L", [(-0.070, -0.005, 1.835), (-0.095, 0.020, 1.875), (-0.115, 0.015, 1.835)], [0.017, 0.012, 0.002]),
        ("Crown_C", [(0.000, 0.000, 1.850), (0.010, 0.030, 1.890), (0.030, 0.020, 1.845)], [0.018, 0.012, 0.002]),
        ("Crown_R", [(0.065, -0.003, 1.838), (0.095, 0.020, 1.875), (0.115, 0.010, 1.830)], [0.017, 0.012, 0.002]),
    ]
    for name, centers, widths in locks:
        pieces.append(legacy.hair_blade(name, centers, widths, hair, depth=0.006))
    return pieces


def clean_costume(body: bpy.types.Object) -> list[bpy.types.Object]:
    # Use the rigged body itself for the wardrobe silhouette. This keeps animation
    # clean and avoids the giant black shell that swallowed the character in v1.
    low, high = reference.local_bounds(body)
    height = high.z - low.z
    jacket = mat(
        "Arthur_BlackJacketV2",
        (0.004, 0.005, 0.007, 1.0),
        (0.018, 0.020, 0.026, 1.0),
        (0.065, 0.070, 0.082, 1.0),
    )
    shirt = mat(
        "Arthur_GrayShirtV2",
        (0.055, 0.058, 0.064, 1.0),
        (0.21, 0.22, 0.23, 1.0),
        (0.42, 0.43, 0.45, 1.0),
    )
    trousers = mat(
        "Arthur_NavyTrousersV2",
        (0.008, 0.012, 0.020, 1.0),
        (0.030, 0.043, 0.070, 1.0),
        (0.085, 0.105, 0.145, 1.0),
    )
    shoes = mat(
        "Arthur_BrownShoesV2",
        (0.025, 0.015, 0.010, 1.0),
        (0.12, 0.070, 0.040, 1.0),
        (0.27, 0.16, 0.095, 1.0),
    )
    jacket_i = len(body.data.materials); body.data.materials.append(jacket)
    shirt_i = len(body.data.materials); body.data.materials.append(shirt)
    trousers_i = len(body.data.materials); body.data.materials.append(trousers)
    shoes_i = len(body.data.materials); body.data.materials.append(shoes)

    for polygon in body.data.polygons:
        center = sum((body.data.vertices[i].co for i in polygon.vertices), Vector()) / len(polygon.vertices)
        zf = (center.z - low.z) / height
        if zf < 0.075:
            polygon.material_index = shoes_i
        elif zf < 0.49:
            polygon.material_index = trousers_i
        elif zf < 0.80:
            # Sleeves and the side/back planes read as the black outer jacket.
            # The central front plane remains the gray button shirt.
            sleeve = abs(center.x) > 0.115
            front_center = center.y < -0.045 and abs(center.x) < 0.105
            polygon.material_index = shirt_i if (front_center and not sleeve) else jacket_i
    return []


def configure_preview() -> bpy.types.Object:
    camera = ORIGINAL_CONFIGURE_RENDER()
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
        scene.display.shading.outline_color = (0.006, 0.006, 0.008)
    return camera


def main() -> None:
    reference.install_reference_overrides()
    legacy.append_anime_body = append_body_v2
    legacy.hair_cap = clean_hair_cap
    legacy.create_hair = clean_hair
    legacy.create_costume = clean_costume
    legacy.configure_render = configure_preview
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
        scene.display.shading.outline_color = (0.006, 0.006, 0.008)
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 75
    scene["arthur_reference_pass"] = "v2 readable face and normal silhouette"
    args = legacy.cli()
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.blend).resolve()))


if __name__ == "__main__":
    main()
