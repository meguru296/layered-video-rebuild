#!/usr/bin/env python3
"""Read-only structural audit; does not decode video or certify visual quality."""
import argparse
import hashlib
import json
import math
import re
import struct
import sys
from pathlib import Path, PureWindowsPath


def integer(x):
    return type(x) is int


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def audit(data, root, *, allow_partial=False, require_native=False, verify_hashes=False):
    root = Path(root).resolve()
    errors, warnings = [], []
    counts = {"assets": 0, "native_frames": 0, "tracks": 0, "png_headers": 0, "hashes": 0}
    path_cache, hash_cache = {}, {}

    def error(code, location, detail):
        errors.append({"code": code, "location": location, "detail": detail})

    def warning(code, detail):
        warnings.append({"code": code, "detail": detail})

    def finish():
        return {"ok": not errors, "scope": "Declared structure only; no video decode, audio alignment or artistic/content verification.",
                "checked": counts, "errors": errors, "warnings": warnings}

    if not isinstance(data, dict):
        error("SCHEMA", "manifest", "Expected an object.")
        return finish()
    if not root.is_dir():
        error("ROOT_MISSING", "root", "Project root must be an existing directory.")
        return finish()
    if not integer(data.get("schema_version")) or data["schema_version"] != 1:
        error("SCHEMA_VERSION", "schema_version", "Expected integer 1.")
    t = data.get("timeline")
    if not isinstance(t, dict):
        error("TIMELINE", "timeline", "Required object is missing.")
        return finish()
    n = t.get("frame_count")
    if not integer(n) or n < 1:
        error("FRAME_COUNT", "timeline.frame_count", "Expected a positive integer.")
        return finish()
    for key in ("fps_num", "fps_den"):
        if not integer(t.get(key)) or t[key] < 1:
            error("FPS", "timeline." + key, "Expected a positive integer.")
    dimensions = None
    if "width" in t or "height" in t:
        if all(integer(t.get(k)) and t[k] > 0 for k in ("width", "height")):
            dimensions = (t["width"], t["height"])
        else:
            error("DIMENSIONS", "timeline", "Width and height must both be positive integers.")

    def array(obj, key, location):
        x = obj.get(key, [])
        if not isinstance(x, list):
            error("ARRAY", location, "Expected a list.")
            return []
        return x

    def interval(x, location):
        if not (isinstance(x, (list, tuple)) and len(x) == 2 and all(integer(v) for v in x)
                and 0 <= x[0] < x[1] <= n):
            error("INTERVAL", location, "Expected zero-based [start, end), inside the timeline, with start < end.")
            return None
        return tuple(x)

    def media(record, location, png=False):
        rel = record.get("path")
        if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or PureWindowsPath(rel).is_absolute() or PureWindowsPath(rel).drive:
            error("MEDIA_PATH", location, "Expected a portable relative path inside the project root.")
            return None
        try:
            p = (root / rel).resolve()
            p.relative_to(root)
        except (ValueError, OSError, RuntimeError):
            error("MEDIA_ESCAPE", location, "Resolved path escapes the project or cannot be resolved.")
            return None
        if p not in path_cache:
            path_cache[p] = p.is_file()
        if not path_cache[p]:
            error("MEDIA_MISSING", location, rel)
            return None
        expected_hash = record.get("sha256")
        if expected_hash is not None:
            if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
                error("HASH_FORMAT", location, "sha256 must contain exactly 64 hexadecimal digits.")
            elif verify_hashes:
                try:
                    if p not in hash_cache:
                        h = hashlib.sha256()
                        with p.open("rb") as f:
                            for block in iter(lambda: f.read(1024 * 1024), b""):
                                h.update(block)
                        hash_cache[p] = h.hexdigest()
                        counts["hashes"] += 1
                    if hash_cache[p] != expected_hash.lower():
                        error("HASH_MISMATCH", location, rel)
                except OSError as exc:
                    error("MEDIA_READ", location, str(exc))
        if png and p.suffix.lower() == ".png":
            try:
                with p.open("rb") as f:
                    header = f.read(24)
                if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
                    error("PNG_HEADER", location, "Invalid PNG signature or IHDR.")
                else:
                    counts["png_headers"] += 1
                    wh = struct.unpack(">II", header[16:24])
                    if min(wh) < 1 or (dimensions is not None and wh != dimensions):
                        error("PNG_DIMENSIONS", location, f"Actual {wh}; expected {dimensions}.")
            except OSError as exc:
                error("MEDIA_READ", location, str(exc))
        return p

    shots = array(data, "shots", "shots")
    valid_shots = []
    for j, shot in enumerate(shots):
        if not isinstance(shot, dict):
            error("SHOT", f"shots[{j}]", "Expected an object.")
            continue
        v = interval([shot.get("start"), shot.get("end")], f"shots[{j}]")
        if v:
            valid_shots.append(v)
    if shots:
        end = 0
        for a, b in sorted(valid_shots):
            if a < end:
                error("SHOT_OVERLAP", "shots", f"Overlap at frame {a}.")
            if a > end and not allow_partial:
                error("SHOT_GAP", "shots", f"Uncovered [{end}, {a}).")
            end = max(end, b)
        if end < n and not allow_partial:
            error("SHOT_GAP", "shots", f"Uncovered [{end}, {n}).")
    else:
        warning("SHOTS_NOT_CHECKED", "No shot coverage table supplied.")

    assets = {}
    for j, asset in enumerate(array(data, "assets", "assets")):
        loc = f"assets[{j}]"
        if not isinstance(asset, dict):
            error("ASSET", loc, "Expected an object.")
            continue
        counts["assets"] += 1
        ident = asset.get("id")
        if not isinstance(ident, str) or not ident:
            error("ASSET_ID", loc, "Expected a nonempty string ID.")
        elif ident in assets:
            error("ASSET_DUPLICATE", loc, ident)
        else:
            assets[ident] = asset
        if asset.get("status") not in ("approved", "reference", "candidate", "rejected"):
            error("ASSET_STATUS", loc, "Expected approved/reference/candidate/rejected.")
        media(asset, loc)

    for j, layer in enumerate(array(data, "layers", "layers")):
        loc = f"layers[{j}]"
        if not isinstance(layer, dict):
            error("LAYER", loc, "Expected an object.")
            continue
        if layer.get("enabled", True) is False:
            continue
        for ref in array(layer, "asset_ids", loc + ".asset_ids"):
            if not isinstance(ref, str) or ref not in assets:
                error("LAYER_UNKNOWN_ASSET", loc, repr(ref))
            elif assets[ref].get("status") != "approved":
                error("LAYER_UNAPPROVED_ASSET", loc, ref)
        actual = []
        for k, span in enumerate(array(layer, "intervals", loc + ".intervals")):
            v = interval(span, loc + f".intervals[{k}]")
            if v:
                actual.append(v)
        if "expected_intervals" in layer:
            expected = []
            for k, span in enumerate(array(layer, "expected_intervals", loc + ".expected_intervals")):
                v = interval(span, loc + f".expected_intervals[{k}]")
                if v:
                    expected.append(v)
            if sorted(actual) != sorted(expected):
                error("LAYER_INTERVAL_MISMATCH", loc, "Actual strip intervals differ from the intended intervals.")

    frames = array(data, "native_frames", "native_frames")
    if require_native and not frames:
        error("NATIVE_REQUIRED", "native_frames", "A nonempty native-frame list is required.")
    seen = set()
    for j, record in enumerate(frames):
        loc = f"native_frames[{j}]"
        if not isinstance(record, dict):
            error("NATIVE_FRAME", loc, "Expected an object.")
            continue
        f = record.get("frame")
        if not integer(f) or not 0 <= f < n:
            error("NATIVE_RANGE", loc, "Frame index must be inside [0, frame_count).")
        elif f in seen:
            error("NATIVE_DUPLICATE", loc, f"Frame {f} appears more than once.")
        else:
            seen.add(f)
        media(record, loc, png=True)
        counts["native_frames"] += 1
    if frames and len(seen) != n and not allow_partial:
        error("NATIVE_GAP", "native_frames", f"Found {len(seen)} unique in-range frames; expected {n}.")
    if not frames:
        warning("NATIVE_NOT_CHECKED", "No native frames supplied; encoding and visual content are not checked.")

    for j, track in enumerate(array(data, "tracks", "tracks")):
        loc = f"tracks[{j}]"
        if not isinstance(track, dict):
            error("TRACK", loc, "Expected an object.")
            continue
        counts["tracks"] += 1
        kind = track.get("kind")
        if kind not in ("affine", "progress"):
            error("TRACK_KIND", loc, "Expected affine or progress.")
            continue
        samples = array(track, "samples", loc + ".samples")
        if not samples:
            error("TRACK_EMPTY", loc, "Track samples are required.")
        last_frame, values = -1, []
        sign = track.get("expected_sign", 1 if track.get("role") == "stabilization_correction" else None)
        if sign is not None and (not integer(sign) or sign not in (-1, 1)):
            error("TRACK_SIGN", loc, "expected_sign must be integer -1 or 1.")
        if track.get("role") == "stabilization_correction" and sign != 1:
            error("CORRECTION_SIGN", loc, "A same-handedness stabilization correction must be proper, with expected_sign 1.")
        for k, sample in enumerate(samples):
            sloc = loc + f".samples[{k}]"
            if not isinstance(sample, dict):
                error("SAMPLE", sloc, "Expected an object.")
                continue
            f = sample.get("frame")
            if not integer(f) or not 0 <= f <= n or f <= last_frame:
                error("SAMPLE_ORDER", sloc, "Control frames must increase strictly, in [0, frame_count].")
            else:
                last_frame = f
            if kind == "affine":
                m = sample.get("matrix")
                if not (isinstance(m, list) and len(m) == 2 and all(isinstance(r, list) and len(r) == 3 and all(finite(v) for v in r) for r in m)):
                    error("MATRIX", sloc, "Expected a finite 2x3 affine matrix.")
                    continue
                det = m[0][0] * m[1][1] - m[0][1] * m[1][0]
                if not math.isfinite(det) or abs(det) < 1e-10:
                    error("MATRIX_SINGULAR", sloc, "Affine transform is singular or non-finite.")
                elif sign in (-1, 1) and det * sign <= 0:
                    error("MATRIX_HANDEDNESS", sloc, f"Determinant {det} contradicts expected sign {sign}.")
                if track.get("representation") == "similarity":
                    u = (m[0][0], m[1][0])
                    v = (m[0][1], m[1][1])
                    uu, vv = sum(x*x for x in u), sum(x*x for x in v)
                    uv = sum(a*b for a, b in zip(u, v))
                    tolerance = 1e-6 * max(uu, vv, 1e-12)
                    if not all(math.isfinite(x) for x in (uu, vv, uv)) or abs(uu-vv) > tolerance or abs(uv) > tolerance:
                        error("MATRIX_REPRESENTATION", sloc, "Transform cannot be expressed as uniform scale plus rotation/reflection.")
            else:
                value = sample.get("value")
                if not finite(value):
                    error("PROGRESS_VALUE", sloc, "Expected a finite scalar.")
                else:
                    values.append(value)
        if kind == "progress":
            direction = track.get("monotonic")
            if direction not in (None, "increasing", "decreasing"):
                error("MONOTONIC_MODE", loc, "Expected increasing or decreasing, or omit this constraint.")
            if direction in ("increasing", "decreasing"):
                s = 1 if direction == "increasing" else -1
                if any((b - a) * s < -1e-7 for a, b in zip(values, values[1:])):
                    error("PROGRESS_REVERSAL", loc, "Declared monotonic control values reverse direction.")
            bounds = track.get("bounds")
            if bounds is not None:
                if not (isinstance(bounds, list) and len(bounds) == 2 and all(finite(v) for v in bounds) and bounds[0] <= bounds[1]):
                    error("PROGRESS_BOUNDS", loc, "Expected [minimum, maximum].")
                elif any(v < bounds[0] - 1e-7 or v > bounds[1] + 1e-7 for v in values):
                    error("PROGRESS_OUTSIDE_BOUNDS", loc, "A declared control value is outside its bounds.")
            if "required_value" in track:
                v = track["required_value"]
                if not finite(v) or not any(abs(x - v) <= 1e-7 for x in values):
                    error("PROGRESS_REQUIRED_VALUE", loc, "Required control value was never reached.")

    reuse = data.get("source_reuse")
    if reuse is None:
        warning("REUSE_NOT_CHECKED", "No source-reuse declaration supplied; no originality/content claim is made.")
    elif not isinstance(reuse, dict):
        error("REUSE", "source_reuse", "Expected an object.")
    else:
        approved, used = [], []
        for key, target in (("approved_intervals", approved), ("used_intervals", used)):
            for j, x in enumerate(array(reuse, key, "source_reuse." + key)):
                v = interval(x, f"source_reuse.{key}[{j}]")
                if v:
                    target.append(v)
        merged = []
        for a, b in sorted(approved):
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
            else:
                merged.append((a, b))
        for a, b in used:
            if not any(x <= a and b <= y for x, y in merged):
                error("REUSE_OUTSIDE_APPROVAL", "source_reuse", f"Used [{a}, {b}) is not fully approved.")
    return finish()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--require-native", action="store_true")
    parser.add_argument("--verify-hashes", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        result = audit(data, args.root or args.manifest.resolve().parent,
                       allow_partial=args.allow_partial, require_native=args.require_native,
                       verify_hashes=args.verify_hashes)
    except (OSError, ValueError) as exc:
        result = {"ok": False, "errors": [{"code": "MANIFEST_READ", "detail": str(exc)}], "warnings": []}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
