"""
Apple Preview extraction from DNG files.

Extracts the embedded JPEG preview that Apple renders at capture time.
This preview has the exact HDR/tone mapping and colors as viewing the
original DNG on iPhone.

This is the recommended approach for LJPEG DNGs (iPhone 12-16) where
JXL recompression doesn't work correctly.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .detector import detect_dng


@dataclass
class ExtractionResult:
    """Result of preview extraction."""

    success: bool
    input_path: Path
    output_path: Path | None
    input_size: int
    output_size: int
    preview_dimensions: tuple[int, int] | None
    error_message: str | None = None

    @property
    def size_reduction(self) -> float:
        """Calculate size reduction as a ratio (0.0 to 1.0)."""
        if self.input_size > 0 and self.output_size > 0:
            return 1.0 - (self.output_size / self.input_size)
        return 0.0


def extract_preview(
    input_path: Path,
    output_path: Path | None = None,
    copy_metadata: bool = True,
    fix_orientation: bool = True,
) -> ExtractionResult:
    """
    Extract embedded Apple preview from DNG.

    The preview is a full-resolution JPEG rendered by Apple with correct
    HDR tone mapping and color science.

    Args:
        input_path: Path to input DNG file
        output_path: Path for output JPEG (default: input_name.jpg in same dir)
        copy_metadata: Copy EXIF metadata from DNG to output
        fix_orientation: Apply orientation tag to pixel data

    Returns:
        ExtractionResult with extraction details

    Raises:
        FileNotFoundError: If input file doesn't exist
        ValueError: If DNG has no embedded preview
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    # Detect DNG info
    info = detect_dng(input_path)

    if not info.has_preview:
        raise ValueError(f"DNG has no embedded preview: {input_path}")

    # Default output path
    if output_path is None:
        output_path = input_path.with_suffix(".jpg")
    else:
        output_path = Path(output_path)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract preview using exiftool
    cmd = ["exiftool", "-b", "-PreviewImage", str(input_path)]
    result = subprocess.run(cmd, capture_output=True)

    if result.returncode != 0 or not result.stdout:
        return ExtractionResult(
            success=False,
            input_path=input_path,
            output_path=None,
            input_size=info.file_size,
            output_size=0,
            preview_dimensions=info.preview_dimensions,
            error_message=f"Failed to extract preview: {result.stderr.decode()}",
        )

    # Write preview to file
    with open(output_path, "wb") as f:
        f.write(result.stdout)

    # Fix orientation - just update the tag, modern viewers handle it correctly
    # (Pixel rotation would require JPEG re-encoding which degrades quality)
    if fix_orientation:
        cmd = [
            "exiftool",
            "-overwrite_original",
            "-Orientation=1",
            "-n",  # Use numeric value
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True)

    # Copy metadata from original DNG
    if copy_metadata:
        cmd = [
            "exiftool",
            "-overwrite_original",
            "-TagsFromFile",
            str(input_path),
            "-all:all",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True)

    output_size = output_path.stat().st_size if output_path.exists() else 0

    return ExtractionResult(
        success=True,
        input_path=input_path,
        output_path=output_path,
        input_size=info.file_size,
        output_size=output_size,
        preview_dimensions=info.preview_dimensions,
    )


def batch_extract_previews(
    input_paths: list[Path],
    output_dir: Path | None = None,
    copy_metadata: bool = True,
    fix_orientation: bool = True,
) -> list[ExtractionResult]:
    """
    Extract previews from multiple DNG files.

    Args:
        input_paths: List of input DNG paths
        output_dir: Output directory (default: same as each input)
        copy_metadata: Copy EXIF metadata from DNG to output
        fix_orientation: Apply orientation tag to pixel data

    Returns:
        List of ExtractionResult for each input
    """
    results = []

    for input_path in input_paths:
        try:
            if output_dir:
                output_path = output_dir / f"{input_path.stem}.jpg"
            else:
                output_path = None

            result = extract_preview(
                input_path,
                output_path=output_path,
                copy_metadata=copy_metadata,
                fix_orientation=fix_orientation,
            )
            results.append(result)
        except Exception as e:
            results.append(
                ExtractionResult(
                    success=False,
                    input_path=input_path,
                    output_path=None,
                    input_size=input_path.stat().st_size if input_path.exists() else 0,
                    output_size=0,
                    preview_dimensions=None,
                    error_message=str(e),
                )
            )

    return results
