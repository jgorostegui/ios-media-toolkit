"""
Archive workflow factory - Creates the media archival workflow.

This is the main workflow for processing iPhone media:
1. Scan source folder for media files
2. Classify favorites from XMP ratings
3. Copy photos
4. Copy non-MOV videos (already compressed)
5. Transcode MOV files
"""

from dataclasses import dataclass, field
from pathlib import Path

from ..profiles import EncodingProfile
from .tasks import Task, TaskType, Workflow


@dataclass
class ArchiveWorkflowConfig:
    """Configuration for the archive workflow."""

    source: Path
    output: Path
    profile: EncodingProfile
    dry_run: bool = False
    force: bool = False
    limit: int = 0  # 0 = unlimited
    min_size_mb: int = 0  # Minimum size to transcode
    rating_threshold: int = 5


@dataclass
class ArchiveWorkflow(Workflow):
    """
    The archive workflow with specific configuration.

    Extends base Workflow with archive-specific data.
    """

    config: ArchiveWorkflowConfig | None = None
    # Populated after scan
    videos_to_transcode: list[Path] = field(default_factory=list)
    videos_to_copy: list[Path] = field(default_factory=list)
    photos_to_copy: list[Path] = field(default_factory=list)
    favorites: set[str] = field(default_factory=set)


def create_archive_workflow(
    source: Path,
    output: Path,
    profile: EncodingProfile,
    dry_run: bool = False,
    force: bool = False,
    limit: int = 0,
    min_size_mb: int = 0,
    rating_threshold: int = 5,
) -> ArchiveWorkflow:
    """
    Create an archive workflow for processing media.

    This is a FACTORY function that creates the workflow data structure.
    The workflow defines WHAT to do, not HOW to do it.

    Args:
        source: Source folder containing media
        output: Output folder for processed files
        profile: Encoding profile to use for transcoding
        dry_run: If True, workflow will only report what would be done
        force: If True, overwrite existing files
        limit: Maximum videos to transcode (0 = unlimited)
        min_size_mb: Minimum file size in MB to transcode
        rating_threshold: XMP rating threshold for favorites

    Returns:
        ArchiveWorkflow ready for execution by a runner
    """
    config = ArchiveWorkflowConfig(
        source=source,
        output=output,
        profile=profile,
        dry_run=dry_run,
        force=force,
        limit=limit,
        min_size_mb=min_size_mb,
        rating_threshold=rating_threshold,
    )

    workflow = ArchiveWorkflow(
        name="archive",
        description=f"Archive media from {source.name} to {output.name}",
        config=config,
    )

    # Task 1: Scan source folder
    workflow.add_task(
        Task(
            id="scan",
            task_type=TaskType.SCAN,
            description="Scan source folder for media files",
            params={"source": source},
        )
    )

    # Task 2: Classify favorites
    workflow.add_task(
        Task(
            id="classify",
            task_type=TaskType.CLASSIFY,
            description="Detect favorites from XMP ratings",
            params={"source": source, "rating_threshold": rating_threshold},
            depends_on=["scan"],
        )
    )

    # Task 3: Copy photos
    workflow.add_task(
        Task(
            id="copy_photos",
            task_type=TaskType.COPY,
            description="Copy photos to output",
            params={"output_dir": output, "force": force},
            depends_on=["scan"],
        )
    )

    # Task 4: Copy non-MOV videos
    workflow.add_task(
        Task(
            id="copy_videos",
            task_type=TaskType.COPY,
            description="Copy non-MOV videos to output",
            params={"output_dir": output, "force": force},
            depends_on=["scan"],
        )
    )

    # Task 5: Transcode MOV videos
    workflow.add_task(
        Task(
            id="transcode",
            task_type=TaskType.TRANSCODE,
            description="Transcode MOV videos",
            params={
                "output_dir": output,
                "profile": profile,
                "force": force,
                "limit": limit,
                "min_size_mb": min_size_mb,
            },
            depends_on=["scan", "classify"],
        )
    )

    return workflow
