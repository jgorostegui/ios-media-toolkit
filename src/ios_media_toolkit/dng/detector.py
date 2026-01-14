"""
DNG type detection.

Detects compression type (JXL, LJPEG, uncompressed) and extracts metadata
from ProRAW DNG files.
"""

import struct
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DngCompression(Enum):
    """DNG compression types."""

    JXL = "jxl"  # JPEG XL (iPhone 17+)
    LJPEG = "ljpeg"  # Lossless JPEG (iPhone 12-16 "Most Compatible")
    UNCOMPRESSED = "uncompressed"
    UNKNOWN = "unknown"


# TIFF compression tag values
COMPRESSION_NONE = 1
COMPRESSION_LJPEG = 7  # Lossless JPEG
COMPRESSION_JXL = 52546  # JPEG XL


@dataclass
class DngInfo:
    """Information about a DNG file."""

    path: Path
    compression: DngCompression
    compression_value: int  # Raw TIFF compression tag value
    dimensions: tuple[int, int]  # (width, height)
    bits_per_sample: int
    has_preview: bool
    preview_dimensions: tuple[int, int] | None
    preview_size: int  # Size of embedded preview in bytes
    file_size: int

    @property
    def is_jxl(self) -> bool:
        """Check if this is a JXL-compressed DNG."""
        return self.compression == DngCompression.JXL

    @property
    def is_ljpeg(self) -> bool:
        """Check if this is an LJPEG-compressed DNG."""
        return self.compression == DngCompression.LJPEG

    @property
    def can_recompress_jxl(self) -> bool:
        """Check if this DNG can be recompressed with JXL tiles."""
        # Only JXL DNGs can be reliably recompressed
        # LJPEG requires dcraw which applies color processing
        return self.compression == DngCompression.JXL


def _read_compression_from_tiff(path: Path) -> int:
    """Read compression tag from TIFF/DNG, checking SubIFDs for main image."""
    with open(path, "rb") as f:
        data = f.read()

    # Check endianness
    if data[:2] == b"II":
        endian = "<"
    elif data[:2] == b"MM":
        endian = ">"
    else:
        return 0

    # Check TIFF magic
    if struct.unpack(endian + "H", data[2:4])[0] != 42:
        return 0

    def read_ifd(off: int) -> tuple[dict, int]:
        """Read IFD entries and return (entries dict, next_ifd offset)."""
        if off >= len(data) - 2:
            return {}, 0
        n = struct.unpack_from(endian + "H", data, off)[0]
        pos = off + 2
        entries = {}
        for _ in range(n):
            if pos + 12 > len(data):
                break
            tag = struct.unpack_from(endian + "H", data, pos)[0]
            typ = struct.unpack_from(endian + "H", data, pos + 2)[0]
            cnt = struct.unpack_from(endian + "I", data, pos + 4)[0]
            val = struct.unpack_from(endian + "I", data, pos + 8)[0]
            entries[tag] = (typ, cnt, val, pos + 8)
            pos += 12
        next_ifd = struct.unpack_from(endian + "I", data, pos)[0] if pos + 4 <= len(data) else 0
        return entries, next_ifd

    def get_compression(entries: dict) -> int:
        """Get compression value from IFD entries."""
        if 259 not in entries:
            return 0
        typ, cnt, val, vpos = entries[259]
        if typ == 3:  # SHORT
            return struct.unpack_from(endian + "H", data, vpos)[0]
        return val

    # Read IFD0
    ifd0_off = struct.unpack(endian + "I", data[4:8])[0]
    entries, _ = read_ifd(ifd0_off)

    # Check SubIFDs (tag 330) - main RAW image is typically here
    if 330 in entries:
        typ, cnt, val, vpos = entries[330]
        if typ == 4:  # LONG array
            if cnt == 1:
                suboffs = [val]
            else:
                suboffs = list(struct.unpack_from(endian + f"{cnt}I", data, val))

            for suboff in suboffs:
                sub_entries, _ = read_ifd(suboff)
                comp = get_compression(sub_entries)
                if comp == COMPRESSION_JXL:
                    return comp  # Found JXL in SubIFD

    # Fallback to IFD0 compression
    return get_compression(entries)


def detect_dng(path: Path) -> DngInfo:
    """
    Detect DNG type and extract metadata.

    Uses exiftool for reliable metadata extraction.

    Args:
        path: Path to DNG file

    Returns:
        DngInfo with file details

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is not a valid DNG
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Read compression directly from TIFF header (more reliable than exiftool for this)
    compression_value = _read_compression_from_tiff(path)

    # Map compression value to enum
    if compression_value == COMPRESSION_JXL:
        compression = DngCompression.JXL
    elif compression_value == COMPRESSION_LJPEG:
        compression = DngCompression.LJPEG
    elif compression_value == COMPRESSION_NONE:
        compression = DngCompression.UNCOMPRESSED
    else:
        compression = DngCompression.UNKNOWN

    # Use exiftool for other metadata
    cmd = [
        "exiftool",
        "-s",
        "-s",
        "-s",
        "-ImageWidth",
        "-ImageHeight",
        "-BitsPerSample",
        "-PreviewImageLength",
        "-PreviewImageWidth",
        "-PreviewImageHeight",
        str(path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Parse output (one value per line)
    lines = result.stdout.strip().split("\n")
    values = [line.strip() if line.strip() else "0" for line in lines]

    # Pad with defaults if exiftool didn't return all fields
    while len(values) < 6:
        values.append("0")

    try:
        width = int(values[0]) if values[0] else 0
        height = int(values[1]) if values[1] else 0
        # BitsPerSample may be "10 10 10" for 3 channels
        bps_str = values[2].split()[0] if values[2] else "0"
        bits_per_sample = int(bps_str) if bps_str else 0
        preview_length = int(values[3]) if values[3] else 0
        preview_width = int(values[4]) if values[4] else 0
        preview_height = int(values[5]) if values[5] else 0
    except (ValueError, IndexError):
        width = height = bits_per_sample = 0
        preview_length = preview_width = preview_height = 0

    has_preview = preview_length > 0
    preview_dims = (preview_width, preview_height) if has_preview else None

    return DngInfo(
        path=path,
        compression=compression,
        compression_value=compression_value,
        dimensions=(width, height),
        bits_per_sample=bits_per_sample,
        has_preview=has_preview,
        preview_dimensions=preview_dims,
        preview_size=preview_length,
        file_size=path.stat().st_size,
    )
