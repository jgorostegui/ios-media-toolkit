"""Sequential runner - Executes workflows tasks one at a time."""

import shutil
from pathlib import Path

from ..actions import classify_favorites, scan_folder
from ..actions.scan import is_mov_file
from ..constants import DNG_EXTENSIONS, FAV_SUFFIX
from ..dng import DngMethod, compress_jxl_dng, extract_preview
from ..encoder import run_pipeline
from ..manifest import Manifest
from ..workflow import ArchiveWorkflow, TaskStatus, TaskType
from .base import RunnerCallbacks, RunnerResult


def get_output_filename(source_path: Path, is_favorite: bool, extension: str | None = None) -> str:
    """
    Generate output filename, adding __FAV suffix for favorites.

    Args:
        source_path: Source file path
        is_favorite: Whether the file is a favorite
        extension: Optional extension override (e.g., ".mp4" for transcoded videos)

    Returns:
        Output filename with __FAV suffix if favorite

    Examples:
        photo.HEIC + favorite=True  -> photo__FAV.HEIC
        video.MOV  + favorite=True  -> video__FAV.mp4 (with extension=".mp4")
        photo.JPG  + favorite=False -> photo.JPG
    """
    stem = source_path.stem
    ext = extension if extension else source_path.suffix

    if is_favorite:
        return f"{stem}{FAV_SUFFIX}{ext}"
    return f"{stem}{ext}"


class SequentialRunner:
    """
    Sequential workflow runner.

    Executes tasks one at a time in dependency order.
    Uses callbacks for progress reporting without coupling to UI.
    Tracks state via Manifest for idempotent processing.
    """

    def __init__(self, dry_run: bool = False):
        """
        Initialize the runner.

        Args:
            dry_run: If True, don't actually execute operations
        """
        self.dry_run = dry_run
        self.manifest: Manifest | None = None

    def run(self, workflow: ArchiveWorkflow, callbacks: RunnerCallbacks | None = None) -> RunnerResult:
        """
        Execute an archive workflow.

        Args:
            workflow: The ArchiveWorkflow to execute
            callbacks: Optional callbacks for progress reporting

        Returns:
            RunnerResult with execution summary
        """
        cb = callbacks or RunnerCallbacks()
        config = workflow.config

        if config is None:
            return RunnerResult(
                success=False,
                workflow_name=workflow.name,
                errors=["Workflow config is None"],
            )

        # Initialize manifest (stored in output directory)
        if not self.dry_run:
            self.manifest = Manifest(config.output, source_name=config.source.name)
            self.manifest.load()

        # Notify workflow start
        if cb.on_workflow_start:
            cb.on_workflow_start(workflow.name, len(workflow.tasks))

        result = RunnerResult(
            success=True,
            workflow_name=workflow.name,
        )

        # Execute tasks in order
        for task in workflow.tasks:
            # Check dependencies
            deps_met = all(
                workflow.get_task(dep_id).status == TaskStatus.COMPLETED
                for dep_id in task.depends_on
                if workflow.get_task(dep_id) is not None
            )

            if not deps_met:
                task.status = TaskStatus.SKIPPED
                result.tasks_skipped += 1
                continue

            # Notify task start
            if cb.on_task_start:
                cb.on_task_start(task.id, task.description)

            task.status = TaskStatus.RUNNING

            try:
                success = self._execute_task(task, workflow, cb, result)
                if success:
                    task.status = TaskStatus.COMPLETED
                    result.tasks_completed += 1
                else:
                    task.status = TaskStatus.FAILED
                    result.tasks_failed += 1
                    result.success = False

                # Notify task complete
                if cb.on_task_complete:
                    cb.on_task_complete(task.id, success)

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                result.tasks_failed += 1
                result.errors.append(f"Task {task.id}: {e}")
                result.success = False

                if cb.on_task_complete:
                    cb.on_task_complete(task.id, False)

        # Save manifest
        if self.manifest and not self.dry_run:
            # Store favorites in manifest
            if workflow.favorites:
                self.manifest.set_favorites(list(workflow.favorites))
                self.manifest.export_favorites_list()
            self.manifest.save()

        # Notify workflow complete
        if cb.on_workflow_complete:
            cb.on_workflow_complete(result)

        return result

    def _execute_task(
        self,
        task,
        workflow: ArchiveWorkflow,
        cb: RunnerCallbacks,
        result: RunnerResult,
    ) -> bool:
        """Execute a single task based on its type."""
        if task.task_type == TaskType.SCAN:
            return self._run_scan(workflow, cb)

        elif task.task_type == TaskType.CLASSIFY:
            return self._run_classify(workflow, cb)

        elif task.task_type == TaskType.COPY:
            return self._run_copy(task.id, workflow, cb, result)

        elif task.task_type == TaskType.TRANSCODE:
            return self._run_transcode(workflow, cb, result)

        elif task.task_type == TaskType.DNG_PROCESS:
            return self._run_dng_process(workflow, cb, result)

        elif task.task_type == TaskType.VERIFY:
            # Not implemented in this workflow
            return True

        return False

    def _run_scan(self, workflow: ArchiveWorkflow, cb: RunnerCallbacks) -> bool:
        """Execute scan task."""
        config = workflow.config
        scan_result = scan_folder(config.source)

        if not scan_result.success:
            return False

        # Get already processed files from manifest
        processed_stems = self.manifest.get_processed_stems() if self.manifest else set()

        # Categorize videos
        min_size_bytes = config.min_size_mb * 1024 * 1024

        for video in scan_result.videos:
            is_mov = is_mov_file(video)
            output_file = config.output / f"{video.stem}.mp4"
            output_file_fav = config.output / f"{video.stem}{FAV_SUFFIX}.mp4"

            # Skip if output exists and not force
            if not config.force and (output_file.exists() or output_file_fav.exists()):
                continue

            # Non-MOV files: copy (already compressed)
            if not is_mov or (min_size_bytes > 0 and video.stat().st_size < min_size_bytes):
                workflow.videos_to_copy.append(video)
            # MOV files: transcode
            else:
                workflow.videos_to_transcode.append(video)

        # Apply limit
        if config.limit > 0 and len(workflow.videos_to_transcode) > config.limit:
            workflow.videos_to_transcode = workflow.videos_to_transcode[: config.limit]

        # Filter photos by processed status AND output file existence
        # Separate DNGs from regular photos
        for photo in scan_result.photos:
            # Skip if in manifest (unless force)
            if photo.stem in processed_stems and not config.force:
                # But check if output actually exists - if not, process anyway
                # For DNGs, output will be .jpg; for others, same extension
                if photo.suffix in DNG_EXTENSIONS:
                    output_file = config.output / f"{photo.stem}.jpg"
                    output_file_fav = config.output / f"{photo.stem}{FAV_SUFFIX}.jpg"
                else:
                    output_file = config.output / f"{photo.stem}{photo.suffix}"
                    output_file_fav = config.output / f"{photo.stem}{FAV_SUFFIX}{photo.suffix}"
                if output_file.exists() or output_file_fav.exists():
                    continue

            # Separate DNGs from regular photos
            if photo.suffix in DNG_EXTENSIONS:
                workflow.dngs_to_process.append(photo)
            else:
                workflow.photos_to_copy.append(photo)

        # Notify scan complete
        if cb.on_scan_complete:
            cb.on_scan_complete(
                len(scan_result.videos),
                len(scan_result.photos),
                len(workflow.videos_to_transcode),
            )

        return True

    def _run_classify(self, workflow: ArchiveWorkflow, _cb: RunnerCallbacks) -> bool:
        """Execute classify task."""
        config = workflow.config
        classify_result = classify_favorites(config.source, config.rating_threshold)

        if classify_result.success:
            workflow.favorites = classify_result.favorites

        return classify_result.success

    def _run_copy(
        self,
        task_id: str,
        workflow: ArchiveWorkflow,
        cb: RunnerCallbacks,
        result: RunnerResult,
    ) -> bool:
        """Execute copy task."""
        config = workflow.config

        if self.dry_run:
            return True

        # Create output directory
        config.output.mkdir(parents=True, exist_ok=True)

        if task_id == "copy_photos":
            files = workflow.photos_to_copy
            file_type = "photos"
        else:  # copy_videos
            files = workflow.videos_to_copy
            file_type = "videos"

        total = len(files)
        if cb.on_copy_start:
            cb.on_copy_start(file_type, total)

        copied = 0
        progress_interval = max(1, total // 20)  # Report every 5%
        for _idx, file_path in enumerate(files):
            is_favorite = file_path.stem in workflow.favorites
            output_filename = get_output_filename(file_path, is_favorite)
            output_file = config.output / output_filename

            if output_file.exists() and not config.force:
                continue

            shutil.copy2(file_path, output_file)
            copied += 1

            # Report progress periodically
            if cb.on_copy_progress and (copied % progress_interval == 0 or copied == total):
                cb.on_copy_progress(file_type, copied, total)

            # Track in manifest
            if self.manifest:
                self.manifest.mark_completed(
                    stem=file_path.stem,
                    source_path=file_path,
                    output_path=output_file,
                    input_size=file_path.stat().st_size,
                    output_size=output_file.stat().st_size,
                    is_favorite=is_favorite,
                )

        if task_id == "copy_photos":
            result.photos_copied = copied
        else:
            result.videos_copied = copied

        if cb.on_copy_complete:
            cb.on_copy_complete(file_type, copied)

        return True

    def _run_transcode(
        self,
        workflow: ArchiveWorkflow,
        cb: RunnerCallbacks,
        result: RunnerResult,
    ) -> bool:
        """Execute transcode task."""
        config = workflow.config

        if self.dry_run:
            return True

        # Create output directory
        config.output.mkdir(parents=True, exist_ok=True)

        total = len(workflow.videos_to_transcode)
        success_count = 0

        for idx, video in enumerate(workflow.videos_to_transcode):
            if cb.on_transcode_start:
                cb.on_transcode_start(video, idx + 1, total)

            transcode_result = run_pipeline(video, config.output, config.profile)
            is_favorite = video.stem in workflow.favorites

            if transcode_result.success:
                success_count += 1
                result.total_input_bytes += transcode_result.input_size
                result.total_output_bytes += transcode_result.output_size

                # Rename to add __FAV suffix if favorite
                final_output_path = transcode_result.output_path
                if is_favorite and transcode_result.output_path:
                    fav_filename = get_output_filename(video, is_favorite=True, extension=".mp4")
                    fav_output_path = config.output / fav_filename
                    transcode_result.output_path.rename(fav_output_path)
                    final_output_path = fav_output_path

                # Track in manifest
                if self.manifest:
                    self.manifest.mark_completed(
                        stem=video.stem,
                        source_path=video,
                        output_path=final_output_path,
                        input_size=transcode_result.input_size,
                        output_size=transcode_result.output_size,
                        is_favorite=is_favorite,
                    )

                if cb.on_transcode_complete:
                    cb.on_transcode_complete(
                        video,
                        transcode_result.input_size,
                        transcode_result.output_size,
                        True,
                    )
            else:
                error_msg = transcode_result.error_message or "Unknown error"
                result.errors.append(f"Transcode failed: {video.name} - {error_msg}")

                # Track error in manifest
                if self.manifest:
                    self.manifest.mark_error(video.stem, video, error_msg)

                if cb.on_transcode_complete:
                    cb.on_transcode_complete(video, 0, 0, False)

        result.videos_transcoded = success_count
        return success_count > 0 or total == 0

    def _run_dng_process(
        self,
        workflow: ArchiveWorkflow,
        cb: RunnerCallbacks,
        result: RunnerResult,
    ) -> bool:
        """Execute DNG processing task."""
        config = workflow.config

        if self.dry_run:
            return True

        # Create output directory
        config.output.mkdir(parents=True, exist_ok=True)

        dng_profile = config.dng_profile
        if dng_profile is None:
            return True  # No DNG processing configured

        total = len(workflow.dngs_to_process)
        if total == 0:
            return True

        success_count = 0

        for idx, dng_path in enumerate(workflow.dngs_to_process):
            is_favorite = dng_path.stem in workflow.favorites

            # Determine output path based on method
            if dng_profile.method == DngMethod.APPLE_PREVIEW:
                ext = ".jpg"
            else:
                ext = ".DNG"

            output_filename = get_output_filename(dng_path, is_favorite, extension=ext)
            output_file = config.output / output_filename

            if output_file.exists() and not config.force:
                continue

            # Notify start
            if cb.on_dng_start:
                cb.on_dng_start(dng_path, idx + 1, total)

            try:
                if dng_profile.method == DngMethod.APPLE_PREVIEW:
                    dng_result = extract_preview(dng_path, output_file)
                else:
                    dng_result = compress_jxl_dng(
                        dng_path,
                        output_file,
                        profile=dng_profile.to_jxl_profile(),
                    )

                if dng_result.success:
                    success_count += 1
                    result.total_input_bytes += dng_result.input_size
                    result.total_output_bytes += dng_result.output_size

                    # Track in manifest
                    if self.manifest:
                        self.manifest.mark_completed(
                            stem=dng_path.stem,
                            source_path=dng_path,
                            output_path=output_file,
                            input_size=dng_result.input_size,
                            output_size=dng_result.output_size,
                            is_favorite=is_favorite,
                        )

                    if cb.on_dng_complete:
                        cb.on_dng_complete(dng_path, dng_result.input_size, dng_result.output_size, True)
                else:
                    error_msg = dng_result.error_message or "Unknown error"
                    result.errors.append(f"DNG failed: {dng_path.name} - {error_msg}")
                    if self.manifest:
                        self.manifest.mark_error(dng_path.stem, dng_path, error_msg)
                    if cb.on_dng_complete:
                        cb.on_dng_complete(dng_path, 0, 0, False)

            except Exception as e:
                result.errors.append(f"DNG failed: {dng_path.name} - {e}")
                if self.manifest:
                    self.manifest.mark_error(dng_path.stem, dng_path, str(e))
                if cb.on_dng_complete:
                    cb.on_dng_complete(dng_path, 0, 0, False)

        result.dngs_processed = success_count
        return success_count > 0 or total == 0
