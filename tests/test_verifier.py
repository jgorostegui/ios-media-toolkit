"""Tests for verifier module dataclasses."""

from pathlib import Path

from ios_media_toolkit.verifier import CheckResult, CheckStatus, VerificationResult


class TestCheckStatus:
    """Tests for CheckStatus enum."""

    def test_values(self):
        """Test enum values."""
        assert CheckStatus.PASS.value == "pass"
        assert CheckStatus.WARN.value == "warn"
        assert CheckStatus.FAIL.value == "fail"


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_basic_check(self):
        """Test basic check result."""
        result = CheckResult(
            name="Test check",
            status=CheckStatus.PASS,
            details="All good",
        )
        assert result.name == "Test check"
        assert result.status == CheckStatus.PASS
        assert result.details == "All good"
        assert result.expected is None
        assert result.actual is None

    def test_check_with_comparison(self):
        """Test check result with expected/actual."""
        result = CheckResult(
            name="Codec tag",
            status=CheckStatus.FAIL,
            details="Wrong codec",
            expected="hvc1",
            actual="hev1",
        )
        assert result.expected == "hvc1"
        assert result.actual == "hev1"


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_compatible_file(self):
        """Test compatible file with no failures."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Codec", status=CheckStatus.PASS),
                CheckResult(name="DV", status=CheckStatus.PASS),
            ],
            critical_failures=0,
            warnings=0,
        )
        assert result.is_compatible
        assert result.file_path == Path("test.mp4")

    def test_incompatible_file(self):
        """Test incompatible file with critical failure."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Codec tag", status=CheckStatus.FAIL),
            ],
            critical_failures=1,
            warnings=0,
        )
        assert not result.is_compatible

    def test_has_dolby_vision_true(self):
        """Test has_dolby_vision when DV present."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Dolby Vision side data", status=CheckStatus.PASS),
            ],
        )
        assert result.has_dolby_vision

    def test_has_dolby_vision_false(self):
        """Test has_dolby_vision when DV not present."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Dolby Vision side data", status=CheckStatus.FAIL),
            ],
        )
        assert not result.has_dolby_vision

    def test_has_dolby_vision_no_check(self):
        """Test has_dolby_vision when no DV check present."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Other check", status=CheckStatus.PASS),
            ],
        )
        assert not result.has_dolby_vision

    def test_warnings_count(self):
        """Test warnings tracking."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Check 1", status=CheckStatus.WARN),
                CheckResult(name="Check 2", status=CheckStatus.WARN),
            ],
            warnings=2,
        )
        assert result.warnings == 2
        assert result.is_compatible  # Warnings don't make file incompatible
