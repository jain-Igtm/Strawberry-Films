# Strawberry Films

Programmatic 3D animated stories, rendered without hand animation.

## First production: *Arthur: Lab Break* — anime 3D

The repository currently builds the first finished movement gate for the short: a
7.33-second, 110-frame anime transformation in which Arthur's posture changes,
individual hair locks rise, and laboratory equipment lifts around him. The guard
fight is the next sequence built on this accepted character and rig.

The continuous anime body and 71-bone deformation rig come from MB-Lab's anime
base. Strawberry Films adds Arthur's cel shader, textured anime eyes, fitted
costume, independently animated hair, laboratory, acting poses, props, camera,
and automated render pipeline. Nothing requires hand animation.

### Render from GitHub

1. Open **Actions**.
2. Select **Render Arthur Anime Quality Gate**.
3. Choose **Run workflow**.
4. When the workflow finishes, download the `arthur-anime-body-gate` artifact.

The artifact contains:

- `arthur-anime-transformation-proof.mp4`
- `arthur-anime-gate.blend`
- three high-resolution anime checkpoint PNGs

### Render locally

```bash
git clone --depth 1 --branch 1_8_1 https://github.com/animate1978/MB-Lab.git /tmp/MB-Lab
mkdir -p build/review build/motion
blender --background --python scripts/arthur_anime_gate.py -- \
  --mblab /tmp/MB-Lab \
  --output "$PWD/build/review" \
  --blend "$PWD/build/arthur-anime-gate.blend"
blender --background build/arthur-anime-gate.blend \
  -o "$PWD/build/motion/frame_####" -F PNG -s 1 -e 110 -a
ffmpeg -framerate 15 -pattern_type glob -i 'build/motion/frame_*.png' \
  -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
  -c:v libx264 -crf 18 -pix_fmt yuv420p \
  build/arthur-anime-transformation-proof.mp4
```

See [the production sheet](production/arthur-lab-short.md) for the current story and shot timing.
