#!/usr/bin/env python3
"""Build the real anime-body quality gate for Arthur.

This intentionally renders stills only.  The animation pipeline stays off until the
continuous anime mesh, face, hair and costume have passed visual inspection.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector


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


def textured_eye_material(source: bpy.types.Material | None) -> bpy.types.Material:
    material = bpy.data.materials.new("Arthur_AnimeEyes")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (0.82, 0.93, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 0.38

    image = bpy.data.images.get("Anime_mblab_eys_albedo")
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


def replace_legacy_materials(body: bpy.types.Object) -> None:
    skin = cel_material(
        "Arthur_CelSkin",
        SKIN_SHADOW,
        SKIN_BASE,
        SKIN_LIGHT,
        bpy.data.images.get("Anime_mblab_skn_albedo"),
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
    eyes = textured_eye_material(eye_source)

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


def append_anime_body(mblab_root: Path) -> bpy.types.Object:
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
    body.name = "Arthur_AnimeBody"
    body.hide_render = False
    body.hide_viewport = False
    body.select_set(True)
    bpy.context.view_layer.objects.active = body

    for polygon in body.data.polygons:
        polygon.use_smooth = True
    print("ANIME_IMAGES", ", ".join(image.name for image in bpy.data.images))
    replace_legacy_materials(body)
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
    distance = height * (0.78 if portrait else 1.32)
    target_z = center.z + (height * (0.32 if portrait else 0.02))
    camera.location = Vector((height * 0.11, side_sign * distance, target_z + height * 0.01))
    look_at(camera, Vector((0.0, 0.0, target_z)))
    camera.data.lens = 72 if portrait else 58
    scene.render.resolution_x = 720 if portrait else 640
    scene.render.resolution_y = 900
    scene.render.filepath = str(output / f"{label}.png")
    bpy.ops.render.render(write_still=True)


def main() -> None:
    args = cli()
    mblab = Path(args.mblab).resolve()
    output = Path(args.output).resolve()
    blend = Path(args.blend).resolve()
    output.mkdir(parents=True, exist_ok=True)
    blend.parent.mkdir(parents=True, exist_ok=True)

    clear_scene()
    body = append_anime_body(mblab)
    low, high = bounds(body)
    center = (low + high) * 0.5
    height = high.z - low.z
    print("ANIME_BOUNDS", f"low={tuple(low)}", f"high={tuple(high)}", f"height={height:.4f}")

    camera = configure_render()
    # The first gate confirmed the detailed face is on the negative-Y side.
    render_view(camera, output, "front_y_negative_body", center, height, -1.0, False)
    render_view(camera, output, "front_y_negative_face", center, height, -1.0, True)

    bpy.context.scene["arthur_quality_gate"] = "continuous MB-Lab anime male base"
    bpy.context.scene["source_project"] = "https://github.com/animate1978/MB-Lab"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))


if __name__ == "__main__":
    main()
