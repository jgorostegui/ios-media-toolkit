"""Verify actions - DV compatibility verification."""

from dataclasses import dataclass
from pathlib import Path

from ..verifier import verify_file


@dataclass
class VerifyResult:
    """Result of verification action."""

    success: bool
    is_compatible: bool = False
    has_dolby_vision: bool = False
    critical_failures: int = 0
    warnings: int = 0
    error: str | None = None


def verify_dv_compatibility(file_path: Path, reference: Path | None = None) -> VerifyResult:
    """
    Verify video file for iPhone Dolby Vision compatibility.

    Args:
        file_path: Path to video file to verify
        reference: Optional reference file for comparison

    Returns:
        VerifyResult with compatibility info
    """
    try:
        result = verify_file(file_path, reference)
        return VerifyResult(
            success=True,
            is_compatible=result.is_compatible,
            has_dolby_vision=result.has_dolby_vision,
            critical_failures=result.critical_failures,
            warnings=result.warnings,
        )
    except Exception as e:
        return VerifyResult(success=False, error=str(e))
