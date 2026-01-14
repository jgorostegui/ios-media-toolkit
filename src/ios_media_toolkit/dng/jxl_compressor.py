"""
JXL DNG compression.

Recompresses JXL-compressed DNG tiles with lossy JXL encoding.
This preserves RAW editing capability while reducing file size.

Only works for iPhone 17+ JXL DNGs. LJPEG DNGs cannot be reliably
recompressed because dcraw applies color processing during decode.
"""

import os
import struct
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .detector import DngCompression, detect_dng

# TIFF field types → size (bytes)
TIFF_TYPE_SIZE = {
    1: 1,  # BYTE
    2: 1,  # ASCII
    3: 2,  # SHORT
    4: 4,  # LONG
    5: 8,  # RATIONAL
    6: 1,  # SBYTE
    7: 1,  # UNDEFINED
    8: 2,  # SSHORT
    9: 4,  # SLONG
    10: 8,  # SRATIONAL
    11: 4,  # FLOAT
    12: 8,  # DOUBLE
}

TAG_IMAGE_WIDTH = 256
TAG_IMAGE_LENGTH = 257
TAG_COMPRESSION = 259
TAG_TILE_WIDTH = 322
TAG_TILE_LENGTH = 323
TAG_TILE_OFFSETS = 324
TAG_TILE_BYTECOUNTS = 325
TAG_SUBIFDS = 330
TAG_BITS_PER_SAMPLE = 258
TAG_WHITELEVEL = 50717
TAG_BLACKLEVEL = 50714

COMPRESSION_JXL = 52546


@dataclass
class JxlProfile:
    """JXL compression settings."""

    distance: float = 1.0  # 0=lossless, 1.0=visually lossless, 2.0+=lossy
    effort: int = 7  # 1-9, higher=slower+smaller
    modular: bool = True  # Better for linear/HDR data


@dataclass
class CompressionResult:
    """Result of JXL compression."""

    success: bool
    input_path: Path
    output_path: Path | None
    input_size: int
    output_size: int
    tiles_processed: int
    profile: JxlProfile
    error_message: str | None = None
    tile_stats: list[tuple[int, int]] = field(default_factory=list)  # (old_size, new_size)

    @property
    def size_reduction(self) -> float:
        """Calculate size reduction as a ratio (0.0 to 1.0)."""
        if self.input_size > 0 and self.output_size > 0:
            return 1.0 - (self.output_size / self.input_size)
        return 0.0


@dataclass
class _IfdEntry:
    tag: int
    typ: int
    count: int
    value_u32: int
    entry_pos: int
    value_pos: int


@dataclass
class _Ifd:
    offset: int
    entries: dict[int, _IfdEntry]
    next_ifd: int


def _read_u16(endian: str, data: bytes, off: int) -> int:
    return struct.unpack_from(endian + "H", data, off)[0]


def _read_u32(endian: str, data: bytes, off: int) -> int:
    return struct.unpack_from(endian + "I", data, off)[0]


def _parse_ifd(endian: str, data: bytes, off: int) -> _Ifd:
    n = _read_u16(endian, data, off)
    pos = off + 2
    entries: dict[int, _IfdEntry] = {}
    for _ in range(n):
        tag = _read_u16(endian, data, pos)
        typ = _read_u16(endian, data, pos + 2)
        count = _read_u32(endian, data, pos + 4)
        value_u32 = _read_u32(endian, data, pos + 8)
        unit = TIFF_TYPE_SIZE.get(typ, 1)
        total = unit * count
        value_pos = (pos + 8) if total <= 4 else value_u32
        entries[tag] = _IfdEntry(tag, typ, count, value_u32, pos, value_pos)
        pos += 12
    next_ifd = _read_u32(endian, data, pos)
    return _Ifd(off, entries, next_ifd)


def _read_values(endian: str, data: bytes, e: _IfdEntry) -> list[int]:
    if e.typ == 3:  # SHORT
        raw = data[e.value_pos : e.value_pos + max(4, e.count * 2)]
        raw = raw[: e.count * 2]
        return list(struct.unpack(endian + f"{e.count}H", raw))
    if e.typ == 4:  # LONG
        raw = data[e.value_pos : e.value_pos + max(4, e.count * 4)]
        raw = raw[: e.count * 4]
        return list(struct.unpack(endian + f"{e.count}I", raw))
    if e.typ == 9:  # SLONG
        raw = data[e.value_pos : e.value_pos + max(4, e.count * 4)]
        raw = raw[: e.count * 4]
        return list(struct.unpack(endian + f"{e.count}i", raw))
    raise ValueError(f"Unsupported TIFF type {e.typ} for tag {e.tag}")


def _write_values(endian: str, buf: bytearray, e: _IfdEntry, vals: list[int]) -> None:
    if len(vals) != e.count:
        raise ValueError(f"Count mismatch for tag {e.tag}: expected {e.count}, got {len(vals)}")
    if e.typ == 3:  # SHORT
        packed = struct.pack(endian + f"{e.count}H", *vals)
        buf[e.value_pos : e.value_pos + len(packed)] = packed
    elif e.typ == 4:  # LONG
        packed = struct.pack(endian + f"{e.count}I", *vals)
        buf[e.value_pos : e.value_pos + len(packed)] = packed
    elif e.typ == 9:  # SLONG
        packed = struct.pack(endian + f"{e.count}i", *vals)
        buf[e.value_pos : e.value_pos + len(packed)] = packed
    else:
        raise ValueError(f"Unsupported TIFF type {e.typ} for tag {e.tag}")


def _gather_ifds(endian: str, data: bytes, ifd0_off: int) -> list[_Ifd]:
    seen = set()
    q = [ifd0_off]
    out: list[_Ifd] = []
    while q:
        off = q.pop()
        if off == 0 or off in seen:
            continue
        seen.add(off)
        if off >= len(data):
            continue
        ifd = _parse_ifd(endian, data, off)
        out.append(ifd)
        if ifd.next_ifd:
            q.append(ifd.next_ifd)
        sub = ifd.entries.get(TAG_SUBIFDS)
        if sub:
            try:
                suboffs = _read_values(endian, data, sub)
                for so in suboffs:
                    q.append(so)
            except Exception:
                pass
    return out


def _choose_main_tiled_ifd(endian: str, data: bytes, ifds: list[_Ifd]) -> _Ifd:
    candidates = []
    for ifd in ifds:
        if TAG_TILE_OFFSETS in ifd.entries and TAG_TILE_BYTECOUNTS in ifd.entries:
            w = _read_values(endian, data, ifd.entries[TAG_IMAGE_WIDTH])[0] if TAG_IMAGE_WIDTH in ifd.entries else 0
            h = _read_values(endian, data, ifd.entries[TAG_IMAGE_LENGTH])[0] if TAG_IMAGE_LENGTH in ifd.entries else 0
            cnt = ifd.entries[TAG_TILE_OFFSETS].count
            candidates.append((w * h, cnt, ifd))
    if not candidates:
        raise RuntimeError("No tiled IFD found.")
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def _ppm_read_u16_rgb(path: str) -> np.ndarray:
    with open(path, "rb") as f:
        magic = f.readline().strip()
        if magic != b"P6":
            raise ValueError(f"Unexpected PPM magic: {magic}")
        line = f.readline()
        while line.startswith(b"#"):
            line = f.readline()
        w, h = map(int, line.split())
        _ = int(f.readline().strip())  # maxval
        raw = f.read()
    return np.frombuffer(raw, dtype=">u2").reshape(h, w, 3).astype(np.uint16)


def _ppm_write_u16_rgb(path: str, arr: np.ndarray) -> None:
    h, w, c = arr.shape
    assert c == 3
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n65535\n".encode("ascii"))
        f.write(arr.astype(">u2").tobytes())


def _encode_tile_jxl(in_ppm: str, out_jxl: str, profile: JxlProfile) -> None:
    cmd = ["cjxl", in_ppm, out_jxl, "-d", str(profile.distance), "-e", str(profile.effort)]
    if profile.modular:
        cmd.extend(["-m", "1"])
    subprocess.run(cmd, capture_output=True, check=True)


def compress_jxl_dng(
    input_path: Path,
    output_path: Path | None = None,
    profile: JxlProfile | None = None,
    verbose: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> CompressionResult:
    """
    Recompress JXL DNG with lossy JXL tiles.

    Only works for iPhone 17+ JXL-compressed DNGs.

    Args:
        input_path: Path to input DNG file
        output_path: Path for output DNG (default: input_recomp.DNG)
        profile: JXL compression profile (default: distance=1.0, effort=7, modular=True)
        verbose: Print progress information
        progress_callback: Optional callback(tile_idx, total_tiles) for progress

    Returns:
        CompressionResult with compression details

    Raises:
        FileNotFoundError: If input file doesn't exist
        ValueError: If DNG is not JXL-compressed
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    # Use default profile if not specified
    if profile is None:
        profile = JxlProfile()

    # Default output path
    if output_path is None:
        output_path = input_path.with_stem(f"{input_path.stem}_recomp")
    else:
        output_path = Path(output_path)

    # Detect DNG type
    info = detect_dng(input_path)

    if info.compression != DngCompression.JXL:
        raise ValueError(f"DNG is not JXL-compressed (found: {info.compression.value}). " "JXL recompression only works for iPhone 17+ JXL DNGs.")

    # Read input DNG
    with open(input_path, "rb") as f:
        orig = f.read()

    # Detect endianness
    if orig[:2] == b"II":
        endian = "<"
    elif orig[:2] == b"MM":
        endian = ">"
    else:
        return CompressionResult(
            success=False,
            input_path=input_path,
            output_path=None,
            input_size=len(orig),
            output_size=0,
            tiles_processed=0,
            profile=profile,
            error_message="Not a valid TIFF/DNG file",
        )

    # Parse IFD structure
    ifd0_off = _read_u32(endian, orig, 4)
    ifds = _gather_ifds(endian, orig, ifd0_off)
    main_ifd = _choose_main_tiled_ifd(endian, orig, ifds)

    # Get tile info
    tile_offsets_e = main_ifd.entries[TAG_TILE_OFFSETS]
    tile_counts_e = main_ifd.entries[TAG_TILE_BYTECOUNTS]
    tile_offsets = _read_values(endian, orig, tile_offsets_e)
    tile_counts = _read_values(endian, orig, tile_counts_e)
    ntiles = len(tile_offsets)

    first_tile = min(tile_offsets)

    # Process tiles
    new_tiles: list[bytes] = []
    tile_stats: list[tuple[int, int]] = []

    with tempfile.TemporaryDirectory() as td:
        for i in range(ntiles):
            off = tile_offsets[i]
            ln = tile_counts[i]
            tile_bytes = orig[off : off + ln]

            in_jxl = os.path.join(td, f"in_{i:03d}.jxl")
            dec_ppm = os.path.join(td, f"dec_{i:03d}.ppm")
            out_jxl = os.path.join(td, f"out_{i:03d}.jxl")

            # Write tile data
            with open(in_jxl, "wb") as f:
                f.write(tile_bytes)

            # Decode with djxl
            cmd = ["djxl", in_jxl, dec_ppm, "--bits_per_sample", "16"]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                return CompressionResult(
                    success=False,
                    input_path=input_path,
                    output_path=None,
                    input_size=len(orig),
                    output_size=0,
                    tiles_processed=i,
                    profile=profile,
                    error_message=f"Failed to decode tile {i}: {result.stderr.decode()}",
                )

            # Read and re-encode
            img = _ppm_read_u16_rgb(dec_ppm)
            _ppm_write_u16_rgb(dec_ppm, img)  # Write back (no modifications)
            _encode_tile_jxl(dec_ppm, out_jxl, profile)

            with open(out_jxl, "rb") as f:
                new_tile = f.read()
                new_tiles.append(new_tile)
                tile_stats.append((ln, len(new_tile)))

            if verbose:
                print(f"  Tile {i}: {ln / 1024:.1f}KB → {len(new_tile) / 1024:.1f}KB")

            if progress_callback:
                progress_callback(i + 1, ntiles)

    # Build output DNG
    out = bytearray(orig[:first_tile])

    new_offsets = []
    new_counts = []
    for t in new_tiles:
        new_offsets.append(len(out))
        new_counts.append(len(t))
        out.extend(t)

    # Patch tile arrays
    _write_values(endian, out, tile_offsets_e, new_offsets)
    _write_values(endian, out, tile_counts_e, new_counts)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    with open(output_path, "wb") as f:
        f.write(out)

    return CompressionResult(
        success=True,
        input_path=input_path,
        output_path=output_path,
        input_size=len(orig),
        output_size=len(out),
        tiles_processed=ntiles,
        profile=profile,
        tile_stats=tile_stats,
    )
