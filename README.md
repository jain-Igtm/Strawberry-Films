# Strawberry Films

Programmatic 3D animated stories, rendered without hand animation.

## First production: *Arthur: Lab Break* — VRoid anime 3D

The repository builds a ten-second, 150-frame transformation gate in which
Arthur's posture and expression change, independently rigged hair sections rise,
and laboratory equipment leaves the floor around him. The guard fight is the
next sequence built on this character and rig.

Arthur uses VRoid Studio's CC0 `HairSample_Male` base: an authored masculine
anime face, textured eyes, layered rigged hair, hoodie costume, 91-bone
humanoid/secondary rig, and 40 facial shape keys. Strawberry Films adds the
acting, hair lift, laboratory, floating props, cameras, and automated render
pipeline. Nothing requires hand animation.

### Render from GitHub

1. Open **Actions**.
2. Select **Render Arthur VRoid Anime Gate**.
3. Choose **Run workflow**.
4. When the workflow finishes, download the `arthur-vroid-anime-gate` artifact.

The artifact contains:

- `arthur-vroid-transformation-proof.mp4`
- `arthur-vroid-lab.blend`
- three high-resolution anime checkpoint PNGs

### Render locally

```bash
curl --fail --location \
  --output /tmp/Arthur_HairSample_Male.vrm \
  https://raw.githubusercontent.com/madjin/vrm-samples/master/vroid/beta/HairSample_Male.vrm
cp /tmp/Arthur_HairSample_Male.vrm /tmp/Arthur_HairSample_Male.glb
mkdir -p build/review build/motion
blender --background --python scripts/arthur_vroid_short.py -- \
  --model /tmp/Arthur_HairSample_Male.glb \
  --output "$PWD/build/review" \
  --blend "$PWD/build/arthur-vroid-lab.blend"
blender --background build/arthur-vroid-lab.blend \
  -o "$PWD/build/motion/frame_####" -F PNG -s 1 -e 150 -a
ffmpeg -framerate 15 -pattern_type glob -i 'build/motion/frame_*.png' \
  -c:v libx264 -crf 18 -pix_fmt yuv420p \
  build/arthur-vroid-transformation-proof.mp4
```

See [the production sheet](production/arthur-lab-short.md) for the current story and shot timing.
