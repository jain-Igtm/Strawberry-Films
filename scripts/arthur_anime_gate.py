#!/usr/bin/env python3
"""Build the real anime-body quality gate for Arthur.

It builds a reusable rigged anime character, renders visual checkpoints, and saves
the animated transformation scene for the automated motion proof.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import sys
import types
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


SKIN_LIGHT = (0.82, 0.51, 0.34, 1.0)
SKIN_BASE = (0.58, 0.27, 0.16, 1.0)
SKIN_SHADOW = (0.22, 0.075, 0.055, 1.0)


def cli() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--mblab", required=True, help="Path to the MB-Lab checkout")
    parser.add_argument("--output", required=True, help="Directory for diagnostic PNGs")
    parser.add_argument("--blend", required=True, help="Path for the generated scene")
    return parser.parse_args(values)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.cameras, bpy.data.lights, bpy.data.curves):
        for datablock in list(datablocks):
            datablocks.remove(datablock)


def cel_material(
    name: str,
    shadow: tuple[float, float, float, float],
    base: tuple[float, float, float, float],
    light: tuple[float, float, float, float],
    texture_image: bpy.types.Image | None = None,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = base
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    diffuse = nodes.new("ShaderNodeBsdfDiffuse")
    shader_to_rgb = nodes.new("ShaderNodeShaderToRGB")
    ramp = nodes.new("ShaderNodeValToRGB")
    emission = nodes.new("ShaderNodeEmission")
    output = nodes.new("ShaderNodeOutputMaterial")
    diffuse.inputs["Color"].default_value = base
    diffuse.inputs["Roughness"].default_value = 0.75
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
    shade = ramp.color_ramp.elements[0]
    shade.position = 0.28
    shade.color = shadow
    middle = ramp.color_ramp.elements.new(0.52)
    middle.color = base
    highlight = ramp.color_ramp.elements.new(0.78)
    highlight.color = light
    links.new(diffuse.outputs["BSDF"], shader_to_rgb.inputs["Shader"])
    links.new(shader_to_rgb.outputs["Color"], ramp.inputs["Fac"])
    if texture_image is not None:
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = texture_image
        texture.interpolation = "Linear"
        multiply = nodes.new("ShaderNodeMixRGB")
        multiply.blend_type = "MULTIPLY"
        multiply.inputs[0].default_value = 1.0
        links.new(ramp.outputs["Color"], multiply.inputs[1])
        links.new(texture.outputs["Color"], multiply.inputs[2])
        links.new(multiply.outputs["Color"], emission.inputs["Color"])
    else:
        links.new(ramp.outputs["Color"], emission.inputs["Color"])
    emission.inputs["Strength"].default_value = 0.82
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def textured_eye_material(
    source: bpy.types.Material | None,
    albedo: bpy.types.Image | None,
) -> bpy.types.Material:
    material = bpy.data.materials.new("Arthur_AnimeEyes")
    material.diffuse_color = (0.12, 0.64, 0.72, 1.0)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (0.82, 0.93, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 0.38

    image = albedo or bpy.data.images.get("Anime_mblab_eys_albedo")
    if image is None and source and source.use_nodes:
        image_node = next(
            (node for node in source.node_tree.nodes if node.type == "TEX_IMAGE" and node.image),
            None,
        )
        image = image_node.image if image_node else None
    if image is not None:
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        texture.interpolation = "Linear"
        links.new(texture.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def find_first_image(source: bpy.types.Material | None) -> bpy.types.Image | None:
    if source and source.use_nodes:
        node = next(
            (candidate for candidate in source.node_tree.nodes if candidate.type == "TEX_IMAGE" and candidate.image),
            None,
        )
        return node.image if node else None
    return None


def replace_legacy_materials(
    body: bpy.types.Object,
    albedo: bpy.types.Image | None,
) -> None:
    source_skin = next(
        (material for material in body.data.materials if material and "skin" in material.name.lower()),
        None,
    )
    skin = cel_material(
        "Arthur_CelSkin",
        SKIN_SHADOW,
        SKIN_BASE,
        SKIN_LIGHT,
        albedo or bpy.data.images.get("Anime_mblab_skn_albedo") or find_first_image(source_skin),
    )
    mouth = cel_material(
        "Arthur_Mouth",
        (0.025, 0.008, 0.012, 1.0),
        (0.16, 0.035, 0.045, 1.0),
        (0.42, 0.12, 0.13, 1.0),
    )
    eye_source = next(
        (material for material in body.data.materials if material and "eye" in material.name.lower()),
        None,
    )
    eyes = textured_eye_material(eye_source, albedo)

    for index, original in enumerate(list(body.data.materials)):
        original_name = original.name if original else "<empty>"
        lowered = original_name.lower()
        if "eye" in lowered:
            replacement = eyes
        elif any(word in lowered for word in ("mouth", "teeth", "tongue")):
            replacement = mouth
        else:
            replacement = skin
        body.data.materials[index] = replacement
        polygon_count = sum(1 for polygon in body.data.polygons if polygon.material_index == index)
        print(
            "ANIME_MATERIAL",
            f"slot={index}",
            f"source={original_name}",
            f"replacement={replacement.name}",
            f"faces={polygon_count}",
        )


def assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    obj.data.materials.append(material)


def emission_material(
    name: str,
    color: tuple[float, float, float, float],
    strength: float = 1.0,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength
    output = nodes.new("ShaderNodeOutputMaterial")
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def cube_object(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    material: bpy.types.Material,
    bevel_width: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location, scale=scale)
    obj = bpy.context.object
    obj.name = name
    assign_material(obj, material)
    if bevel_width:
        bevel = obj.modifiers.new("Anime_Edge_Soften", "BEVEL")
        bevel.width = bevel_width
        bevel.segments = 2
    return obj


def mesh_object(
    name: str,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    material: bpy.types.Material,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    assign_material(obj, material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return obj


def ring_shell(
    name: str,
    rings: list[tuple[float, float, float]],
    material: bpy.types.Material,
    sides: int = 32,
) -> bpy.types.Object:
    vertices: list[tuple[float, float, float]] = []
    for z, radius_x, radius_y in rings:
        for index in range(sides):
            angle = math.tau * index / sides
            vertices.append((radius_x * math.cos(angle), radius_y * math.sin(angle), z))
    faces: list[tuple[int, ...]] = []
    for ring in range(len(rings) - 1):
        for index in range(sides):
            following = (index + 1) % sides
            current = ring * sides + index
            faces.append((current, ring * sides + following, (ring + 1) * sides + following, (ring + 1) * sides + index))
    faces.append(tuple(reversed(range(sides))))
    last = (len(rings) - 1) * sides
    faces.append(tuple(last + index for index in range(sides)))
    return mesh_object(name, vertices, faces, material)


def hair_cap(material: bpy.types.Material) -> bpy.types.Object:
    # The cap hugs MB-Lab's anime cranium.  Oversizing this shell turns the
    # silhouette into a helmet once the head pitches forward.
    center = Vector((0.0, -0.055, 1.605))
    radius_x, radius_y, radius_z = 0.158, 0.142, 0.175
    rings = 10
    sides = 40
    vertices: list[tuple[float, float, float]] = []
    for ring in range(rings):
        theta = (math.pi * 0.44) * ring / (rings - 1)
        radial = math.sin(theta)
        for side in range(sides):
            phi = math.tau * side / sides
            x = center.x + radius_x * radial * math.cos(phi)
            y = center.y + radius_y * radial * math.sin(phi)
            z = center.z + radius_z * math.cos(theta)
            # A raised, asymmetric front edge prevents a helmet-shaped hairline.
            frontness = max(0.0, -math.sin(phi))
            z += frontness * (0.064 + 0.012 * math.sin(phi * 3.0)) * (ring / (rings - 1)) ** 3
            vertices.append((x, y, z))
    faces: list[tuple[int, ...]] = []
    for ring in range(rings - 1):
        for side in range(sides):
            following = (side + 1) % sides
            faces.append((ring * sides + side, ring * sides + following, (ring + 1) * sides + following, (ring + 1) * sides + side))
    cap = mesh_object("Arthur_HairCap", vertices, faces, material)
    bevel = cap.modifiers.new("Soft_Hair_Edges", "BEVEL")
    bevel.width = 0.004
    bevel.segments = 2
    return cap


def hair_blade(
    name: str,
    centers: list[tuple[float, float, float]],
    widths: list[float],
    material: bpy.types.Material,
    depth: float = 0.025,
) -> bpy.types.Object:
    if len(centers) != len(widths):
        raise ValueError("A hair blade needs one width per center")
    vertices: list[tuple[float, float, float]] = []
    for center, width in zip(centers, widths):
        x, y, z = center
        vertices.extend(
            [
                (x - width, y - depth, z),
                (x + width, y - depth, z),
                (x - width * 0.84, y + depth, z + depth * 0.18),
                (x + width * 0.84, y + depth, z + depth * 0.18),
            ]
        )
    faces: list[tuple[int, ...]] = []
    for section in range(len(centers) - 1):
        a = section * 4
        b = (section + 1) * 4
        faces.extend(
            [
                (a, a + 1, b + 1, b),
                (a + 2, b + 2, b + 3, a + 3),
                (a, b, b + 2, a + 2),
                (a + 1, a + 3, b + 3, b + 1),
            ]
        )
    faces.append((0, 2, 3, 1))
    end = (len(centers) - 1) * 4
    faces.append((end, end + 1, end + 3, end + 2))
    blade = mesh_object(name, vertices, faces, material)
    bevel = blade.modifiers.new("Rounded_Lock", "BEVEL")
    bevel.width = 0.006
    bevel.segments = 2
    return blade


def create_hair() -> list[bpy.types.Object]:
    hair = cel_material(
        "Arthur_CelHair",
        (0.012, 0.006, 0.014, 1.0),
        (0.055, 0.018, 0.032, 1.0),
        (0.19, 0.055, 0.075, 1.0),
    )
    pieces = [hair_cap(hair)]
    # Wide, curved locks read as drawn anime hair and can later lift independently.
    locks = [
        ("Fringe_L1", [(-0.112, -0.135, 1.73), (-0.122, -0.198, 1.695), (-0.102, -0.232, 1.655)], [0.032, 0.025, 0.005]),
        ("Fringe_L2", [(-0.058, -0.145, 1.75), (-0.062, -0.207, 1.71), (-0.040, -0.238, 1.67)], [0.032, 0.025, 0.005]),
        ("Fringe_C", [(-0.005, -0.150, 1.758), (0.000, -0.214, 1.718), (0.015, -0.241, 1.68)], [0.033, 0.025, 0.005]),
        ("Fringe_R1", [(0.050, -0.145, 1.75), (0.060, -0.205, 1.71), (0.080, -0.235, 1.67)], [0.031, 0.024, 0.005]),
        ("Fringe_R2", [(0.100, -0.132, 1.73), (0.112, -0.192, 1.695), (0.125, -0.224, 1.655)], [0.030, 0.023, 0.004]),
        ("Crown_L", [(-0.090, -0.035, 1.75), (-0.118, -0.048, 1.795), (-0.132, -0.005, 1.825)], [0.034, 0.025, 0.005]),
        ("Crown_C", [(-0.018, -0.025, 1.77), (-0.012, -0.035, 1.815), (0.012, 0.000, 1.842)], [0.036, 0.026, 0.005]),
        ("Crown_R", [(0.060, -0.028, 1.76), (0.088, -0.035, 1.802), (0.118, 0.005, 1.828)], [0.034, 0.024, 0.005]),
        ("Temple_L", [(-0.135, -0.075, 1.69), (-0.151, -0.112, 1.655), (-0.145, -0.145, 1.615)], [0.023, 0.017, 0.004]),
        ("Temple_R", [(0.135, -0.072, 1.69), (0.150, -0.108, 1.655), (0.145, -0.142, 1.615)], [0.023, 0.017, 0.004]),
    ]
    pieces.extend(hair_blade(name, centers, widths, hair) for name, centers, widths in locks)
    return pieces


def create_costume(body: bpy.types.Object) -> list[bpy.types.Object]:
    cloth = cel_material(
        "Arthur_LabCoat",
        (0.018, 0.035, 0.075, 1.0),
        (0.045, 0.12, 0.22, 1.0),
        (0.15, 0.34, 0.55, 1.0),
    )
    trim = cel_material(
        "Arthur_CostumeTrim",
        (0.015, 0.025, 0.04, 1.0),
        (0.10, 0.16, 0.22, 1.0),
        (0.28, 0.42, 0.52, 1.0),
    )
    trousers = cel_material(
        "Arthur_Trousers",
        (0.012, 0.018, 0.032, 1.0),
        (0.035, 0.055, 0.085, 1.0),
        (0.10, 0.15, 0.21, 1.0),
    )
    shoes = cel_material(
        "Arthur_Shoes",
        (0.004, 0.005, 0.009, 1.0),
        (0.014, 0.019, 0.028, 1.0),
        (0.06, 0.075, 0.09, 1.0),
    )
    cloth_index = len(body.data.materials)
    body.data.materials.append(cloth)
    trouser_index = len(body.data.materials)
    body.data.materials.append(trousers)
    shoe_index = len(body.data.materials)
    body.data.materials.append(shoes)
    for polygon in body.data.polygons:
        # Slot 3 is the modeled eye surface; the legacy toon/generic slots also
        # contain scattered body faces and must follow the same costume mask.
        if polygon.material_index == 3:
            continue
        center = sum((body.data.vertices[index].co for index in polygon.vertices), Vector()) / len(polygon.vertices)
        if center.z < 0.12:
            polygon.material_index = shoe_index
        elif center.z < 0.885:
            polygon.material_index = trouser_index
        elif center.z < 1.48 and (center.z < 1.415 or abs(center.x) > 0.105):
            polygon.material_index = cloth_index

    pieces = [
        ring_shell(
            "Arthur_HighCollar",
            [(1.39, 0.112, 0.088), (1.47, 0.118, 0.091), (1.492, 0.107, 0.086)],
            trim,
        )
    ]
    # A narrow graphic seam follows the front plane without becoming body geometry.
    bpy.ops.mesh.primitive_cube_add(location=(0.0, -0.151, 1.075), scale=(0.006, 0.006, 0.285))
    seam = bpy.context.object
    seam.name = "Arthur_JacketSeam"
    assign_material(seam, trim)
    pieces.append(seam)
    return pieces


def rig_anime_body(
    body: bpy.types.Object,
    mblab_root: Path,
    character_name: str = "Arthur",
) -> bpy.types.Object:
    """Attach MB-Lab's fitted deformation skeleton without enabling its UI add-on."""
    package_name = "strawberry_mblab_vendor"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(mblab_root)]
        package.__package__ = package_name
        sys.modules[package_name] = package
    file_ops = importlib.import_module(f"{package_name}.file_ops")
    skeletonengine = importlib.import_module(f"{package_name}.skeletonengine")
    file_ops.set_data_path("data")
    with (mblab_root / "data" / "characters_config.json").open(encoding="utf-8") as handle:
        character_config = json.load(handle)["m_an01"]
    skeleton = skeletonengine.SkeletonEngine(body, character_config, "base")
    skeleton.fit_joints()
    armature = skeleton.get_armature()
    if not armature:
        raise RuntimeError("MB-Lab did not create Arthur's armature")
    armature.name = f"{character_name}_AnimeRig"
    armature.show_in_front = True
    armature.hide_render = True
    print(
        "ANIME_RIG",
        f"bones={len(armature.data.bones)}",
        f"vertex_groups={len(body.vertex_groups)}",
        f"modifiers={len(body.modifiers)}",
    )
    return armature


def parent_keep_transform(obj: bpy.types.Object, parent: bpy.types.Object) -> None:
    world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = world


def create_character_root(
    character_name: str,
    body: bpy.types.Object,
    armature: bpy.types.Object,
) -> bpy.types.Object:
    root = bpy.data.objects.new(f"{character_name}_MotionRoot", None)
    bpy.context.collection.objects.link(root)
    root.rotation_mode = "XYZ"
    parent_keep_transform(body, root)
    parent_keep_transform(armature, root)
    return root


def bone_parent(obj: bpy.types.Object, armature: bpy.types.Object, bone_name: str) -> None:
    world = obj.matrix_world.copy()
    obj.parent = armature
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    obj.matrix_world = world


def load_pose(armature: bpy.types.Object, pose_path: Path) -> None:
    with pose_path.open(encoding="utf-8") as handle:
        pose = json.load(handle)
    applied = 0
    for name, values in pose.items():
        bone = armature.pose.bones.get(name)
        if not bone:
            continue
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion = Quaternion(values)
        applied += 1
    bpy.context.view_layer.update()
    print("ANIME_POSE", pose_path.name, f"bones={applied}")


def create_anime_lab() -> list[bpy.types.Object]:
    wall = cel_material(
        "Lab_Wall",
        (0.025, 0.045, 0.075, 1.0),
        (0.09, 0.17, 0.25, 1.0),
        (0.32, 0.52, 0.68, 1.0),
    )
    floor = cel_material(
        "Lab_Floor",
        (0.012, 0.017, 0.026, 1.0),
        (0.035, 0.055, 0.075, 1.0),
        (0.11, 0.18, 0.23, 1.0),
    )
    frame = cel_material(
        "Lab_Frame",
        (0.008, 0.012, 0.020, 1.0),
        (0.03, 0.05, 0.075, 1.0),
        (0.12, 0.18, 0.24, 1.0),
    )
    cyan = emission_material("Lab_Cyan", (0.025, 0.36, 0.60, 1.0), 0.7)
    objects = [
        cube_object("Lab_Floor", (0.0, 0.35, -0.08), (4.4, 3.7, 0.08), floor),
        cube_object("Lab_BackWall", (0.0, 2.7, 1.65), (4.4, 0.09, 1.75), wall),
        cube_object("Lab_Window", (0.0, 2.58, 1.9), (2.45, 0.02, 0.72), cyan, 0.025),
        cube_object("Window_Top", (0.0, 2.52, 2.65), (2.58, 0.08, 0.055), frame),
        cube_object("Window_Bottom", (0.0, 2.52, 1.15), (2.58, 0.08, 0.055), frame),
    ]
    for x in (-2.56, 2.56):
        objects.append(cube_object(f"Window_Side_{x}", (x, 2.52, 1.9), (0.055, 0.08, 0.80), frame))
    for x in (-3.4, -2.6, 2.6, 3.4):
        objects.append(cube_object(f"Lab_Console_{x}", (x, 2.12, 0.66), (0.32, 0.38, 0.65), frame, 0.035))
        objects.append(cube_object(f"Console_Glow_{x}", (x, 1.72, 0.90), (0.22, 0.018, 0.16), cyan, 0.018))
    return objects


def create_floating_equipment() -> list[bpy.types.Object]:
    metal = cel_material(
        "Lab_Equipment",
        (0.015, 0.022, 0.032, 1.0),
        (0.07, 0.11, 0.15, 1.0),
        (0.27, 0.38, 0.46, 1.0),
    )
    pieces: list[bpy.types.Object] = []
    positions = [
        (-1.6, 0.45, 0.05), (1.55, 0.65, 0.05), (-2.3, 1.15, 0.12),
        (2.2, 1.35, 0.08), (-1.2, 1.85, 0.12), (1.0, 1.95, 0.12),
        (-2.8, 2.0, 0.75), (2.9, 1.85, 0.80),
    ]
    for index, position in enumerate(positions):
        if index % 3 == 0:
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.055, depth=0.28, location=position)
            obj = bpy.context.object
        else:
            obj = cube_object(f"Floating_Instrument_{index}", position, (0.10, 0.045, 0.035), metal, 0.012)
        obj.name = f"Floating_Equipment_{index}"
        if not obj.data.materials:
            assign_material(obj, metal)
        start = obj.location.copy()
        obj.keyframe_insert(data_path="location", frame=1)
        obj.keyframe_insert(data_path="rotation_euler", frame=1)
        obj.keyframe_insert(data_path="location", frame=45 + index)
        obj.keyframe_insert(data_path="rotation_euler", frame=45 + index)
        angle = math.tau * index / len(positions)
        obj.location = Vector((math.cos(angle) * (0.65 + index % 3 * 0.18), 0.20 + math.sin(angle) * 0.42, 1.12 + (index % 4) * 0.19))
        obj.rotation_euler = (math.radians(38 + index * 13), math.radians(index * 21), math.radians(index * 33))
        obj.keyframe_insert(data_path="location", frame=78 + index)
        obj.keyframe_insert(data_path="rotation_euler", frame=78 + index)
        obj.keyframe_insert(data_path="location", frame=110)
        obj.keyframe_insert(data_path="rotation_euler", frame=110)
        pieces.append(obj)
    return pieces


def create_guard_uniform(
    body: bpy.types.Object,
    character_name: str,
    accent: tuple[float, float, float, float],
) -> None:
    uniform = cel_material(
        f"{character_name}_Uniform",
        (0.010, 0.014, 0.022, 1.0),
        (0.028, 0.045, 0.070, 1.0),
        accent,
    )
    boots = cel_material(
        f"{character_name}_Boots",
        (0.003, 0.004, 0.006, 1.0),
        (0.010, 0.014, 0.020, 1.0),
        (0.055, 0.070, 0.085, 1.0),
    )
    uniform_index = len(body.data.materials)
    body.data.materials.append(uniform)
    boot_index = len(body.data.materials)
    body.data.materials.append(boots)
    for polygon in body.data.polygons:
        if polygon.material_index == 3:
            continue
        center = sum((body.data.vertices[index].co for index in polygon.vertices), Vector()) / len(polygon.vertices)
        if center.z < 0.15:
            polygon.material_index = boot_index
        elif center.z < 1.49:
            polygon.material_index = uniform_index


def create_guard_gear(
    character_name: str,
    armature: bpy.types.Object,
    accent: tuple[float, float, float, float],
) -> tuple[list[bpy.types.Object], bpy.types.Object]:
    armor = cel_material(
        f"{character_name}_Armor",
        (0.008, 0.012, 0.020, 1.0),
        (0.040, 0.065, 0.095, 1.0),
        accent,
    )
    visor_material = emission_material(
        f"{character_name}_Visor",
        (0.04, 0.38, 0.52, 1.0),
        0.65,
    )
    gear: list[bpy.types.Object] = []

    helmet = hair_cap(armor)
    helmet.name = f"{character_name}_Helmet"
    bone_parent(helmet, armature, "head")
    gear.append(helmet)

    visor = cube_object(
        f"{character_name}_Visor",
        (0.0, -0.204, 1.678),
        (0.137, 0.015, 0.048),
        visor_material,
        0.012,
    )
    bone_parent(visor, armature, "head")
    gear.append(visor)

    chest = cube_object(
        f"{character_name}_ChestPlate",
        (0.0, -0.118, 1.22),
        (0.145, 0.025, 0.19),
        armor,
        0.025,
    )
    bone_parent(chest, armature, "spine03")
    gear.append(chest)
    for side, x in (("L", -0.178), ("R", 0.178)):
        shoulder = cube_object(
            f"{character_name}_Shoulder_{side}",
            (x, -0.015, 1.40),
            (0.060, 0.082, 0.042),
            armor,
            0.022,
        )
        bone_parent(shoulder, armature, f"upperarm_{side}")
        gear.append(shoulder)

    baton = None
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16,
        radius=0.022,
        depth=0.52,
        location=(0.34, -0.12, 1.02),
    )
    baton = bpy.context.object
    baton.name = f"{character_name}_Baton"
    assign_material(baton, armor)
    baton.rotation_euler = (math.radians(78.0), 0.0, math.radians(8.0))
    bone_parent(baton, armature, "hand_R")
    gear.append(baton)
    return gear, baton


def create_anime_guard(
    mblab_root: Path,
    character_name: str,
    accent: tuple[float, float, float, float],
) -> tuple[bpy.types.Object, bpy.types.Object, bpy.types.Object, bpy.types.Object]:
    body = append_anime_body(mblab_root, character_name)
    create_guard_uniform(body, character_name, accent)
    armature = rig_anime_body(body, mblab_root, character_name)
    gear, baton = create_guard_gear(character_name, armature, accent)
    root = create_character_root(character_name, body, armature)
    for object_ in gear:
        if object_.parent is None:
            parent_keep_transform(object_, root)
    return body, armature, root, baton


def key_rig_pose(armature: bpy.types.Object, frame: int) -> None:
    for bone in armature.pose.bones:
        bone.rotation_mode = "QUATERNION"
        bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)
        bone.keyframe_insert(data_path="location", frame=frame)


def key_root_pose(
    root: bpy.types.Object,
    frame: int,
    location: tuple[float, float, float],
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    root.location = location
    root.rotation_euler = rotation
    root.keyframe_insert(data_path="location", frame=frame)
    root.keyframe_insert(data_path="rotation_euler", frame=frame)


def key_pose_file(
    armature: bpy.types.Object,
    pose_path: Path,
    frame: int,
) -> None:
    load_pose(armature, pose_path)
    key_rig_pose(armature, frame)


def animate_fight(
    arthur_armature: bpy.types.Object,
    arthur_root: bpy.types.Object,
    guard_one: tuple[bpy.types.Object, bpy.types.Object],
    guard_two: tuple[bpy.types.Object, bpy.types.Object],
    mblab_root: Path,
) -> None:
    scene = bpy.context.scene
    scene.frame_end = 290
    poses = mblab_root / "data" / "poses" / "male_poses"
    guard_one_armature, guard_one_root = guard_one
    guard_two_armature, guard_two_root = guard_two

    # Arthur barely moves: a short redirect for the baton, then a turn made
    # before the second guard reaches him.
    key_pose_file(arthur_armature, poses / "evil_waiting_orders01.json", 110)
    key_pose_file(arthur_armature, poses / "evil_waiting_orders01.json", 138)
    key_pose_file(arthur_armature, poses / "evil_explains.json", 158)
    key_pose_file(arthur_armature, poses / "evil_waiting_orders02.json", 184)
    key_pose_file(arthur_armature, poses / "evil_waiting_orders02.json", 212)
    key_pose_file(arthur_armature, poses / "evil_explains.json", 232)
    key_pose_file(arthur_armature, poses / "evil_waiting_orders01.json", 254)
    key_pose_file(arthur_armature, poses / "evil_waiting_orders01.json", 290)
    key_root_pose(arthur_root, 1, (0.0, 0.0, 0.0))
    key_root_pose(arthur_root, 138, (0.0, 0.0, 0.0))
    key_root_pose(arthur_root, 162, (0.08, 0.03, 0.0), (0.0, 0.0, math.radians(-9.0)))
    key_root_pose(arthur_root, 184, (0.0, 0.0, 0.0))
    key_root_pose(arthur_root, 212, (0.0, 0.0, 0.0))
    key_root_pose(arthur_root, 235, (-0.05, 0.02, 0.0), (0.0, 0.0, math.radians(12.0)))
    key_root_pose(arthur_root, 254, (0.0, 0.0, 0.0))
    key_root_pose(arthur_root, 290, (0.0, 0.0, 0.0))

    # Guard one enters from camera-left, commits to the baton strike, and is
    # redirected into the padded side of the laboratory.
    key_pose_file(guard_one_armature, poses / "standing_basic.json", 1)
    key_pose_file(guard_one_armature, poses / "standing_basic.json", 110)
    key_pose_file(guard_one_armature, poses / "standing_hero01.json", 132)
    key_pose_file(guard_one_armature, poses / "evil_beast.json", 154)
    key_pose_file(guard_one_armature, poses / "flying01.json", 169)
    key_pose_file(guard_one_armature, poses / "flying02.json", 188)
    key_pose_file(guard_one_armature, poses / "flying02.json", 290)
    key_root_pose(guard_one_root, 1, (-3.1, 0.36, 0.0))
    key_root_pose(guard_one_root, 110, (-3.1, 0.36, 0.0))
    key_root_pose(guard_one_root, 132, (-2.15, 0.30, 0.0))
    key_root_pose(guard_one_root, 154, (-0.78, 0.10, 0.0))
    key_root_pose(guard_one_root, 166, (-0.58, 0.08, 0.02), (0.0, 0.0, math.radians(-12.0)))
    key_root_pose(guard_one_root, 184, (-2.62, 0.62, 0.16), (0.0, math.radians(-74.0), math.radians(-28.0)))
    key_root_pose(guard_one_root, 202, (-2.88, 0.72, 0.05), (0.0, math.radians(-86.0), math.radians(-34.0)))
    key_root_pose(guard_one_root, 290, (-2.88, 0.72, 0.05), (0.0, math.radians(-86.0), math.radians(-34.0)))

    # Guard two waits on the opposite side, charges after the first impact,
    # locks in mid-motion, and drops rather than being struck by Arthur.
    key_pose_file(guard_two_armature, poses / "standing_basic.json", 1)
    key_pose_file(guard_two_armature, poses / "standing_basic.json", 166)
    key_pose_file(guard_two_armature, poses / "standing_hero02.json", 194)
    key_pose_file(guard_two_armature, poses / "evil_beast.json", 222)
    key_pose_file(guard_two_armature, poses / "captured01.json", 238)
    key_pose_file(guard_two_armature, poses / "flying02.json", 259)
    key_pose_file(guard_two_armature, poses / "flying02.json", 290)
    key_root_pose(guard_two_root, 1, (3.2, 0.62, 0.0), (0.0, 0.0, math.radians(180.0)))
    key_root_pose(guard_two_root, 166, (3.2, 0.62, 0.0), (0.0, 0.0, math.radians(180.0)))
    key_root_pose(guard_two_root, 194, (2.22, 0.40, 0.0), (0.0, 0.0, math.radians(180.0)))
    key_root_pose(guard_two_root, 222, (0.78, 0.12, 0.0), (0.0, 0.0, math.radians(180.0)))
    key_root_pose(guard_two_root, 238, (0.64, 0.10, 0.0), (0.0, 0.0, math.radians(180.0)))
    key_root_pose(guard_two_root, 259, (1.18, 0.44, 0.02), (math.radians(18.0), math.radians(74.0), math.radians(158.0)))
    key_root_pose(guard_two_root, 276, (1.48, 0.62, 0.01), (math.radians(12.0), math.radians(88.0), math.radians(154.0)))
    key_root_pose(guard_two_root, 290, (1.48, 0.62, 0.01), (math.radians(12.0), math.radians(88.0), math.radians(154.0)))

    for target in (arthur_armature, arthur_root, guard_one_armature, guard_one_root, guard_two_armature, guard_two_root):
        if target.animation_data and target.animation_data.action:
            for curve in target.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "BEZIER"
                    point.easing = "EASE_IN_OUT"
    scene.frame_set(1)


def animate_transformation(
    armature: bpy.types.Object,
    hair: list[bpy.types.Object],
    mblab_root: Path,
) -> None:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 110
    scene.render.fps = 15

    lab_pose = mblab_root / "data" / "poses" / "male_poses" / "standing_in_lab.json"
    altered_pose = mblab_root / "data" / "poses" / "male_poses" / "evil_waiting_orders01.json"
    load_pose(armature, lab_pose)
    key_rig_pose(armature, 1)
    key_rig_pose(armature, 43)
    load_pose(armature, altered_pose)
    key_rig_pose(armature, 61)
    key_rig_pose(armature, 110)

    for index, piece in enumerate(hair):
        piece.rotation_mode = "XYZ"
        start_location = piece.location.copy()
        start_rotation = piece.rotation_euler.copy()
        piece.keyframe_insert(data_path="location", frame=1)
        piece.keyframe_insert(data_path="rotation_euler", frame=1)
        piece.keyframe_insert(data_path="location", frame=43 + index % 3)
        piece.keyframe_insert(data_path="rotation_euler", frame=43 + index % 3)
        if piece.name != "Arthur_HairCap":
            piece.location = start_location + Vector((0.0, 0.0, 0.035 + (index % 4) * 0.012))
            piece.rotation_euler = start_rotation.copy()
            piece.rotation_euler.x += math.radians(-9.0 - (index % 3) * 3.5)
            piece.rotation_euler.y += math.radians((-1 if index % 2 else 1) * (2.0 + index % 4))
        rise_frame = 60 + index % 8
        piece.keyframe_insert(data_path="location", frame=rise_frame)
        piece.keyframe_insert(data_path="rotation_euler", frame=rise_frame)
        piece.keyframe_insert(data_path="location", frame=110)
        piece.keyframe_insert(data_path="rotation_euler", frame=110)

    eye_material = bpy.data.materials.get("Arthur_AnimeEyes")
    if eye_material and eye_material.use_nodes:
        emission = next((node for node in eye_material.node_tree.nodes if node.type == "EMISSION"), None)
        if emission:
            strength = emission.inputs["Strength"]
            strength.default_value = 0.38
            strength.keyframe_insert(data_path="default_value", frame=1)
            strength.keyframe_insert(data_path="default_value", frame=43)
            strength.default_value = 0.12
            strength.keyframe_insert(data_path="default_value", frame=58)
            strength.keyframe_insert(data_path="default_value", frame=110)

    # Tight timing reads as an involuntary state change instead of a heroic power-up.
    if armature.animation_data and armature.animation_data.action:
        for curve in armature.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "BEZIER"
                point.easing = "EASE_IN_OUT"
    scene.frame_set(1)


def append_anime_body(
    mblab_root: Path,
    character_name: str = "Arthur",
) -> bpy.types.Object:
    library = mblab_root / "data" / "humanoid_library.blend"
    if not library.is_file():
        raise FileNotFoundError(f"MB-Lab body library is missing: {library}")

    template_name = "MBLab_anime_male"
    with bpy.data.libraries.load(str(library), link=False) as (source, target):
        if template_name not in source.objects:
            raise RuntimeError(
                f"{template_name!r} is absent from {library}; available objects: "
                + ", ".join(source.objects)
            )
        target.objects = [template_name]

    body = target.objects[0]
    if body is None:
        raise RuntimeError("Blender returned an empty MB-Lab anime body")
    bpy.context.collection.objects.link(body)
    body.name = f"{character_name}_AnimeBody"
    body.hide_render = False
    body.hide_viewport = False
    body.select_set(True)
    bpy.context.view_layer.objects.active = body

    for polygon in body.data.polygons:
        polygon.use_smooth = True
    albedo_path = mblab_root / "data" / "textures" / "anime_male_albedo.png"
    albedo = bpy.data.images.load(str(albedo_path), check_existing=True) if albedo_path.is_file() else None
    if albedo:
        albedo.name = "Arthur_Anime_Albedo"
        albedo.colorspace_settings.name = "sRGB"
        print("ANIME_ALBEDO", albedo.filepath, tuple(albedo.size))
    print("ANIME_IMAGES", ", ".join(image.name for image in bpy.data.images))
    replace_legacy_materials(body, albedo)
    print(
        "ANIME_MESH",
        f"vertices={len(body.data.vertices)}",
        f"faces={len(body.data.polygons)}",
        f"materials={len(body.data.materials)}",
    )
    return body


def bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        Vector(tuple(min(point[i] for point in points) for i in range(3))),
        Vector(tuple(max(point[i] for point in points) for i in range(3))),
    )


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area(name: str, location: tuple[float, float, float], energy: float, size: float) -> None:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    lamp = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(lamp)
    lamp.location = location
    look_at(lamp, Vector((0.0, 0.0, 1.0)))


def configure_render() -> bpy.types.Object:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 720
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.look = "AgX - Medium High Contrast"

    scene.world.color = (0.018, 0.024, 0.045)
    if scene.world.use_nodes:
        background = scene.world.node_tree.nodes.get("Background")
        background.inputs["Color"].default_value = (0.012, 0.019, 0.045, 1.0)
        background.inputs["Strength"].default_value = 0.28

    camera_data = bpy.data.cameras.new("GateCamera")
    camera = bpy.data.objects.new("GateCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    camera_data.lens = 58

    add_area("Key", (-3.8, -4.8, 5.7), 1150.0, 4.0)
    add_area("Rim", (3.4, 2.7, 4.9), 900.0, 3.0)
    add_area("Fill", (2.8, -1.8, 2.3), 500.0, 3.5)
    return camera


def render_view(
    camera: bpy.types.Object,
    output: Path,
    label: str,
    center: Vector,
    height: float,
    side_sign: float,
    portrait: bool,
) -> None:
    scene = bpy.context.scene
    distance = height * (0.98 if portrait else 1.32)
    target_z = center.z + (height * (0.31 if portrait else 0.02))
    camera.location = Vector((height * 0.11, side_sign * distance, target_z + height * 0.01))
    look_at(camera, Vector((0.0, 0.0, target_z)))
    camera.data.lens = 62 if portrait else 58
    scene.render.resolution_x = 720 if portrait else 640
    scene.render.resolution_y = 900
    scene.render.filepath = str(output / f"{label}.png")
    bpy.ops.render.render(write_still=True)


def animate_fight_camera(camera: bpy.types.Object) -> None:
    scene = bpy.context.scene
    camera.rotation_mode = "QUATERNION"
    shots = [
        (1, (0.20, -2.05, 1.62), (0.0, 0.0, 1.42), 58.0),
        (104, (0.20, -2.05, 1.62), (0.0, 0.0, 1.42), 58.0),
        (118, (0.00, -5.15, 1.55), (0.0, 0.30, 1.10), 48.0),
        (154, (-0.32, -4.55, 1.40), (-0.45, 0.20, 1.08), 52.0),
        (184, (-0.55, -5.00, 1.58), (-0.70, 0.40, 1.00), 48.0),
        (212, (0.48, -4.70, 1.42), (0.55, 0.20, 1.08), 51.0),
        (244, (0.55, -4.35, 1.38), (0.42, 0.25, 1.02), 53.0),
        (276, (0.00, -5.20, 1.56), (0.0, 0.38, 0.96), 48.0),
        (290, (0.00, -5.20, 1.56), (0.0, 0.38, 0.96), 48.0),
    ]
    for frame, location, target, lens in shots:
        camera.location = location
        camera.rotation_quaternion = (Vector(target) - camera.location).to_track_quat("-Z", "Y")
        camera.data.lens = lens
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_quaternion", frame=frame)
        camera.data.keyframe_insert(data_path="lens", frame=frame)
    for target in (camera, camera.data):
        if target.animation_data and target.animation_data.action:
            for curve in target.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "BEZIER"
                    point.easing = "EASE_IN_OUT"
    scene.frame_set(1)


def main() -> None:
    args = cli()
    mblab = Path(args.mblab).resolve()
    output = Path(args.output).resolve()
    blend = Path(args.blend).resolve()
    output.mkdir(parents=True, exist_ok=True)
    blend.parent.mkdir(parents=True, exist_ok=True)

    clear_scene()
    create_anime_lab()
    create_floating_equipment()
    body = append_anime_body(mblab)
    hair = create_hair()
    costume = create_costume(body)
    armature = rig_anime_body(body, mblab)
    for object_ in hair:
        bone_parent(object_, armature, "head")
    for object_ in costume:
        bone_parent(object_, armature, "spine03")
    arthur_root = create_character_root("Arthur", body, armature)
    guard_one_body, guard_one_armature, guard_one_root, _ = create_anime_guard(
        mblab,
        "GuardOne",
        (0.11, 0.30, 0.42, 1.0),
    )
    guard_two_body, guard_two_armature, guard_two_root, _ = create_anime_guard(
        mblab,
        "GuardTwo",
        (0.34, 0.13, 0.16, 1.0),
    )
    animate_transformation(armature, hair, mblab)
    animate_fight(
        armature,
        arthur_root,
        (guard_one_armature, guard_one_root),
        (guard_two_armature, guard_two_root),
        mblab,
    )
    low, high = bounds(body)
    center = (low + high) * 0.5
    height = high.z - low.z
    print("ANIME_BOUNDS", f"low={tuple(low)}", f"high={tuple(high)}", f"height={height:.4f}")

    camera = configure_render()
    # The first gate confirmed the detailed face is on the negative-Y side.
    render_view(camera, output, "front_y_negative_face", center, height, -1.0, True)
    # The three-quarter gate catches flat hair, bad silhouettes and facial distortion.
    camera.location = Vector((height * 0.38, -height * 0.94, center.z + height * 0.33))
    look_at(camera, Vector((0.0, -0.04, center.z + height * 0.31)))
    camera.data.lens = 62
    bpy.context.scene.render.resolution_x = 720
    bpy.context.scene.render.resolution_y = 900
    bpy.context.scene.render.filepath = str(output / "arthur_three_quarter_face.png")
    bpy.ops.render.render(write_still=True)
    bpy.context.scene.frame_set(70)
    bpy.context.scene.render.filepath = str(output / "arthur_state_changed_face.png")
    bpy.ops.render.render(write_still=True)
    bpy.context.scene.frame_set(1)
    animate_fight_camera(camera)
    # Motion QA uses the same geometry, rig, camera and material colors without
    # recompiling the Eevee cel-shader graph for every sampled pose.
    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.display.shading.light = "STUDIO"
    bpy.context.scene.display.shading.color_type = "MATERIAL"
    bpy.context.scene.display.shading.show_shadows = True
    bpy.context.scene.display.shading.show_cavity = True
    bpy.context.scene.display.shading.cavity_type = "BOTH"
    bpy.context.scene.display.shading.show_specular_highlight = False
    bpy.context.scene.render.resolution_x = 960
    bpy.context.scene.render.resolution_y = 540
    bpy.context.scene.render.resolution_percentage = 50

    bpy.context.scene["arthur_quality_gate"] = "continuous MB-Lab anime male base"
    bpy.context.scene["source_project"] = "https://github.com/animate1978/MB-Lab"
    bpy.context.scene["arthur_rig"] = "MB-Lab base FK with fitted anime joints"
    bpy.context.scene["arthur_pose"] = "standing_in_lab"
    bpy.context.scene["arthur_animation"] = "state change and two-guard fight frames 1-290 at 15 fps"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))


if __name__ == "__main__":
    main()
