#!/usr/bin/env python3
"""Build the accepted VRoid-based 3D anime Arthur transformation shot."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


FPS = 15
FRAME_END = 150
TRANSFORM_START = 52
TRANSFORM_END = 88


def cli() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="Path to the CC0 HairSample_Male VRM renamed as GLB")
    parser.add_argument("--output", required=True, help="Directory for review stills")
    parser.add_argument("--blend", required=True, help="Generated Blender scene")
    return parser.parse_args(values)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def make_material(
    name: str,
    color: tuple[float, float, float, float],
    emission: float = 0.0,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = 0.72
    if emission:
        principled.inputs["Emission Color"].default_value = color
        principled.inputs["Emission Strength"].default_value = emission
    return material


def add_cube(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    material: bpy.types.Material,
    bevel: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location, scale=scale)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    if bevel:
        modifier = obj.modifiers.new("Soft_Anime_Edge", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    return obj


def create_lab() -> list[bpy.types.Object]:
    wall = make_material("Lab_Wall", (0.035, 0.070, 0.105, 1.0))
    floor = make_material("Lab_Floor", (0.015, 0.024, 0.036, 1.0))
    dark = make_material("Lab_Trim", (0.008, 0.014, 0.024, 1.0))
    cyan = make_material("Lab_Screen", (0.015, 0.30, 0.48, 1.0), 0.5)
    red = make_material("Lab_Alarm", (0.55, 0.018, 0.028, 1.0), 0.7)
    objects = [
        add_cube("Lab_Floor", (0.0, 0.0, -0.08), (4.5, 3.5, 0.08), floor),
        add_cube("Lab_BackWall", (0.0, -2.75, 1.65), (4.5, 0.10, 1.75), wall),
        add_cube("ObservationGlass", (0.0, -2.62, 2.03), (2.55, 0.025, 0.65), cyan, 0.025),
        add_cube("WindowTop", (0.0, -2.55, 2.72), (2.66, 0.10, 0.055), dark),
        add_cube("WindowBottom", (0.0, -2.55, 1.34), (2.66, 0.10, 0.055), dark),
        add_cube("Platform", (0.0, -0.05, 0.02), (0.74, 0.62, 0.05), dark, 0.04),
    ]
    for x in (-2.65, 2.65):
        objects.append(add_cube(f"WindowSide_{x}", (x, -2.55, 2.03), (0.055, 0.10, 0.74), dark))
    for index, x in enumerate((-3.45, -2.70, 2.70, 3.45)):
        objects.append(add_cube(f"Console_{index}", (x, -2.05, 0.66), (0.29, 0.42, 0.64), dark, 0.035))
        objects.append(add_cube(f"ConsoleScreen_{index}", (x, -1.61, 0.91), (0.20, 0.018, 0.15), cyan, 0.015))
    for x in (-3.72, 3.72):
        alarm = add_cube(f"Alarm_{x}", (x, -2.53, 2.63), (0.13, 0.04, 0.07), red, 0.02)
        alarm.hide_render = False
        objects.append(alarm)
    return objects


def create_equipment() -> list[bpy.types.Object]:
    metal = make_material("Floating_Metal", (0.10, 0.14, 0.18, 1.0))
    glass = make_material("Floating_Glass", (0.04, 0.28, 0.36, 1.0), 0.25)
    starts = [
        (-2.7, -1.35, 0.24),
        (-2.1, -1.12, 0.16),
        (-1.65, -1.50, 0.18),
        (1.62, -1.42, 0.18),
        (2.10, -1.10, 0.16),
        (2.70, -1.35, 0.24),
        (-3.22, -1.75, 1.18),
        (3.22, -1.75, 1.18),
        (-1.15, -2.20, 0.92),
        (1.15, -2.20, 0.92),
    ]
    objects: list[bpy.types.Object] = []
    for index, location in enumerate(starts):
        if index % 3 == 0:
            bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.06, depth=0.30, location=location)
            obj = bpy.context.object
            obj.data.materials.append(glass if index % 2 else metal)
        else:
            obj = add_cube(
                f"Instrument_{index}",
                location,
                (0.12, 0.045, 0.035),
                glass if index % 2 else metal,
                0.012,
            )
        obj.name = f"Floating_Equipment_{index}"
        obj.rotation_mode = "XYZ"
        start_location = obj.location.copy()
        start_rotation = obj.rotation_euler.copy()
        for frame in (1, TRANSFORM_START + index % 4):
            obj.location = start_location
            obj.rotation_euler = start_rotation
            obj.keyframe_insert(data_path="location", frame=frame)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)
        angle = math.tau * index / len(starts)
        obj.location = Vector(
            (
                math.cos(angle) * (1.02 + 0.16 * (index % 3)),
                -0.25 + math.sin(angle) * 0.72,
                1.02 + 0.14 * (index % 5),
            )
        )
        obj.rotation_euler = (
            math.radians(24 + index * 11),
            math.radians(index * 19),
            math.radians(index * 31),
        )
        obj.keyframe_insert(data_path="location", frame=TRANSFORM_END + index % 8)
        obj.keyframe_insert(data_path="rotation_euler", frame=TRANSFORM_END + index % 8)
        obj.location.z += 0.035
        obj.rotation_euler.z += math.radians(8.0)
        obj.keyframe_insert(data_path="location", frame=FRAME_END)
        obj.keyframe_insert(data_path="rotation_euler", frame=FRAME_END)
        objects.append(obj)
    return objects


def import_arthur(model_path: Path) -> tuple[bpy.types.Object, bpy.types.Object, bpy.types.Object, bpy.types.Object]:
    bpy.ops.import_scene.gltf(filepath=str(model_path))
    armature = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    face = bpy.data.objects.get("Face")
    body = bpy.data.objects.get("Body")
    hair = bpy.data.objects.get("Hair001")
    if not face or not body or not hair:
        raise RuntimeError("The CC0 HairSample_Male VRoid did not import with Face, Body, and Hair001 meshes")
    armature.name = "Arthur_VRoid_Rig"
    face.name = "Arthur_Face"
    body.name = "Arthur_Body"
    hair.name = "Arthur_Hair"
    for obj in (face, body, hair):
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    for obj in list(bpy.context.scene.objects):
        if obj.type == "MESH" and not obj.data.materials:
            obj.hide_render = True
            obj.hide_viewport = True
    print(
        "VROID_CHARACTER",
        f"bones={len(armature.data.bones)}",
        f"face_vertices={len(face.data.vertices)}",
        f"body_vertices={len(body.data.vertices)}",
        f"hair_vertices={len(hair.data.vertices)}",
        f"shape_keys={len(face.data.shape_keys.key_blocks) if face.data.shape_keys else 0}",
    )
    return armature, face, body, hair


def set_rotation(armature: bpy.types.Object, bone_name: str, xyz_degrees: tuple[float, float, float]) -> None:
    bone = armature.pose.bones[bone_name]
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = tuple(math.radians(value) for value in xyz_degrees)


def set_base_pose(armature: bpy.types.Object) -> None:
    for bone in armature.pose.bones:
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.location = (0.0, 0.0, 0.0)
    set_rotation(armature, "J_Bip_L_UpperArm", (0.0, 0.0, 72.0))
    set_rotation(armature, "J_Bip_R_UpperArm", (0.0, 0.0, -72.0))
    set_rotation(armature, "J_Bip_L_LowerArm", (0.0, -12.0, 0.0))
    set_rotation(armature, "J_Bip_R_LowerArm", (0.0, 12.0, 0.0))
    set_rotation(armature, "J_Bip_C_Head", (-3.5, 0.0, 0.0))
    set_rotation(armature, "J_Bip_C_Chest", (2.0, 0.0, 0.0))


def set_changed_pose(armature: bpy.types.Object) -> None:
    set_base_pose(armature)
    set_rotation(armature, "J_Bip_L_UpperArm", (-3.0, 2.0, 65.0))
    set_rotation(armature, "J_Bip_R_UpperArm", (-3.0, -2.0, -65.0))
    set_rotation(armature, "J_Bip_L_LowerArm", (0.0, -24.0, -3.0))
    set_rotation(armature, "J_Bip_R_LowerArm", (0.0, 24.0, 3.0))
    set_rotation(armature, "J_Bip_C_Head", (8.0, 0.0, -2.0))
    set_rotation(armature, "J_Bip_C_Neck", (-4.0, 0.0, 1.5))
    set_rotation(armature, "J_Bip_C_Chest", (-3.0, 0.0, 0.0))
    set_rotation(armature, "J_Bip_C_UpperChest", (4.0, 0.0, 0.0))


def key_character_pose(armature: bpy.types.Object, frame: int) -> None:
    for bone in armature.pose.bones:
        bone.keyframe_insert(data_path="rotation_euler", frame=frame)
        bone.keyframe_insert(data_path="location", frame=frame)


def add_psychic_hair_rise(hair: bpy.types.Object) -> None:
    """Create a mesh-level lift so the transformation changes the silhouette."""
    if not hair.data.shape_keys:
        hair.shape_key_add(name="Basis", from_mix=False)
    rise = hair.data.shape_keys.key_blocks.get("Psychic_Hair_Rise")
    if not rise:
        rise = hair.shape_key_add(name="Psychic_Hair_Rise", from_mix=False)

    z_values = [vertex.co.z for vertex in hair.data.vertices]
    z_min = min(z_values)
    z_max = max(z_values)
    threshold = z_min + (z_max - z_min) * 0.10
    span = max(z_max - threshold, 0.001)
    for index, vertex in enumerate(hair.data.vertices):
        weight = max(0.0, min(1.0, (vertex.co.z - threshold) / span))
        weight = weight**1.22
        rise.data[index].co.z += 0.24 * weight
        rise.data[index].co.x *= 1.0 - 0.16 * weight
        rise.data[index].co.y *= 1.0 - 0.08 * weight

    for frame, value in ((1, 0.0), (TRANSFORM_START, 0.0), (TRANSFORM_END, 1.0), (FRAME_END, 1.0)):
        rise.value = value
        rise.keyframe_insert(data_path="value", frame=frame)


def animate_arthur(
    armature: bpy.types.Object,
    face: bpy.types.Object,
    hair: bpy.types.Object,
) -> None:
    set_base_pose(armature)
    key_character_pose(armature, 1)
    key_character_pose(armature, TRANSFORM_START)
    set_changed_pose(armature)

    hair_bones = [bone for bone in armature.pose.bones if bone.name.startswith("HairJoint-")]
    for index, bone in enumerate(hair_bones):
        bone.rotation_mode = "XYZ"
        # Push the authored VRoid hair chains into a readable supernatural lift.
        # This is deliberately stronger than ordinary secondary motion: the
        # silhouette has to register in a landscape phone preview.
        bone.rotation_euler.x += math.radians(-24.0 - 3.1 * (index % 5))
        bone.rotation_euler.z += math.radians((-1 if index % 2 else 1) * (7.0 + index % 5))
        if bone.parent and not bone.parent.name.startswith("HairJoint-"):
            bone.location.z += 0.060 + 0.008 * (index % 4)
    key_character_pose(armature, TRANSFORM_END)
    for index, bone in enumerate(hair_bones):
        bone.rotation_euler.x += math.radians(-1.2 - 0.35 * (index % 3))
    key_character_pose(armature, FRAME_END)
    add_psychic_hair_rise(hair)

    if face.data.shape_keys:
        angry = face.data.shape_keys.key_blocks.get("target_2")
        if angry:
            angry.value = 0.0
            angry.keyframe_insert(data_path="value", frame=1)
            angry.keyframe_insert(data_path="value", frame=TRANSFORM_START)
            angry.value = 0.46
            angry.keyframe_insert(data_path="value", frame=TRANSFORM_END)
            angry.keyframe_insert(data_path="value", frame=FRAME_END)

    for target in (
        armature,
        face.data.shape_keys if face.data.shape_keys else None,
        hair.data.shape_keys if hair.data.shape_keys else None,
    ):
        animation = target.animation_data if target else None
        if animation and animation.action:
            for curve in animation.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "BEZIER"
                    point.easing = "EASE_IN_OUT"


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area(
    name: str,
    location: tuple[float, float, float],
    energy: float,
    size: float,
    target: Vector,
) -> None:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    light = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(light)
    light.location = location
    look_at(light, target)


def configure_scene() -> bpy.types.Object:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.world.color = (0.006, 0.010, 0.020)
    if scene.world.use_nodes:
        background = scene.world.node_tree.nodes.get("Background")
        background.inputs["Color"].default_value = (0.006, 0.012, 0.025, 1.0)
        background.inputs["Strength"].default_value = 0.22

    camera_data = bpy.data.cameras.new("Arthur_Camera")
    camera = bpy.data.objects.new("Arthur_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    target = Vector((0.0, 0.0, 1.05))
    add_area("Key", (3.2, 4.2, 5.2), 1050.0, 4.0, target)
    add_area("Fill", (-3.0, 2.5, 2.6), 430.0, 3.5, target)
    add_area("Rim", (-2.4, -2.4, 4.8), 850.0, 3.0, target)
    return camera


def render_portrait(
    camera: bpy.types.Object,
    output: Path,
    filename: str,
    frame: int,
    three_quarter: bool = False,
) -> None:
    scene = bpy.context.scene
    scene.frame_set(frame)
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 720
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    changed = frame >= TRANSFORM_END
    target = Vector((0.0, 0.0, 1.60 if changed else 1.46))
    camera.data.lens = 62 if changed else 68
    camera.location = (
        0.28 if three_quarter else 0.07,
        1.75 if changed else 1.48,
        1.55 if changed else 1.48,
    )
    look_at(camera, target)
    scene.render.filepath = str(output / filename)
    bpy.ops.render.render(write_still=True)


def configure_motion_preview(camera: bpy.types.Object) -> None:
    scene = bpy.context.scene
    scene.frame_set(1)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.show_specular_highlight = True
    scene.render.resolution_x = 480
    scene.render.resolution_y = 270
    scene.render.resolution_percentage = 100
    # Begin wide enough to establish the levitating equipment, then push into
    # Arthur's face and lifted hair as the transformation takes over.
    camera.data.lens = 52
    camera.location = (1.72, 4.25, 2.10)
    look_at(camera, Vector((0.0, -0.18, 1.04)))
    for frame in (1, TRANSFORM_START):
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
        camera.data.keyframe_insert(data_path="lens", frame=frame)

    camera.data.lens = 50
    camera.location = (0.45, 2.80, 1.70)
    look_at(camera, Vector((0.0, -0.12, 1.55)))
    camera.keyframe_insert(data_path="location", frame=TRANSFORM_END)
    camera.keyframe_insert(data_path="rotation_euler", frame=TRANSFORM_END)
    camera.data.keyframe_insert(data_path="lens", frame=TRANSFORM_END)

    camera.data.lens = 54
    camera.location = (0.30, 2.50, 1.65)
    look_at(camera, Vector((0.0, -0.06, 1.58)))
    camera.keyframe_insert(data_path="location", frame=FRAME_END)
    camera.keyframe_insert(data_path="rotation_euler", frame=FRAME_END)
    camera.data.keyframe_insert(data_path="lens", frame=FRAME_END)

    for target in (camera, camera.data):
        if target.animation_data and target.animation_data.action:
            for curve in target.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "BEZIER"
                    point.easing = "EASE_IN_OUT"


def main() -> None:
    args = cli()
    model = Path(args.model).resolve()
    output = Path(args.output).resolve()
    blend = Path(args.blend).resolve()
    output.mkdir(parents=True, exist_ok=True)
    blend.parent.mkdir(parents=True, exist_ok=True)
    if not model.is_file():
        raise FileNotFoundError(model)

    clear_scene()
    create_lab()
    create_equipment()
    armature, face, _body, hair = import_arthur(model)
    animate_arthur(armature, face, hair)
    camera = configure_scene()

    render_portrait(camera, output, "arthur_vroid_neutral.png", 1)
    render_portrait(camera, output, "arthur_vroid_changed.png", 100)
    render_portrait(camera, output, "arthur_vroid_three_quarter.png", 100, True)

    configure_motion_preview(camera)
    scene = bpy.context.scene
    scene["arthur_model"] = "HairSample_Male VRoid beta sample"
    scene["arthur_model_license"] = "CC0"
    scene["arthur_model_source"] = "https://github.com/madjin/vrm-samples"
    scene["arthur_animation"] = "150 frames at 15 fps; state change, facial acting, silhouette hair lift, floating equipment, camera push"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))


if __name__ == "__main__":
    main()
