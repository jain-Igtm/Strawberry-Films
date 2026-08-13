#!/usr/bin/env python3
"""Build the real anime-body quality gate for Arthur.

This intentionally renders stills only.  The animation pipeline stays off until the
continuous anime mesh, face, hair and costume have passed visual inspection.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector


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
    # MB-Lab's template orientation is confirmed by rendering both Y directions once.
    render_view(camera, output, "front_y_negative_body", center, height, -1.0, False)
    render_view(camera, output, "front_y_positive_body", center, height, 1.0, False)
    render_view(camera, output, "front_y_negative_face", center, height, -1.0, True)
    render_view(camera, output, "front_y_positive_face", center, height, 1.0, True)

    bpy.context.scene["arthur_quality_gate"] = "continuous MB-Lab anime male base"
    bpy.context.scene["source_project"] = "https://github.com/animate1978/MB-Lab"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))


if __name__ == "__main__":
    main()
