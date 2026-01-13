"""
CLI module - Command line interface for iOS Media Toolkit

Entry point for the `imt` command using Typer.
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from . import __version__
from .classifier import get_favorites
from .config import PipelineConfig, load_config
from .encoder import PipelineResult, run_pipeline
from .profiles import load_profiles_from_yaml
from .runners import RunnerCallbacks, SequentialRunner
from .scanner import AlbumScanner
from .setup_tools import check_tools_status, run_setup
from .verifier import CheckStatus, verify_file
from .workflow import create_archive_workflow

console = Console()
app = typer.Typer(
    name="imt",
    help="iOS Media Toolkit - iPhone media processing with Dolby Vision preservation.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


# Global options callback for version and config
def version_callback(value: bool):
    if value:
        console.print(f"imt version {__version__}")
        raise typer.Exit()


# Type aliases for common options
ConfigOption = Annotated[
    Path | None,
    typer.Option("--config", "-c", help="Path to config file", exists=True, dir_okay=False),
]


def get_config(config_path: Path | None = None, album: str | None = None) -> PipelineConfig:
    """Load configuration with optional album override."""
    return load_config(config_path, album)


@app.callback()
def main(
    version: Annotated[
        bool, typer.Option("--version", "-v", callback=version_callback, is_eager=True, help="Show version")
    ] = False,
):
    """iOS Media Toolkit - iPhone media processing with Dolby Vision preservation."""
    pass


VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".MOV", ".MP4", ".M4V", ".AVI", ".MKV"}
PHOTO_EXTENSIONS = {".heic", ".HEIC", ".jpg", ".JPG", ".jpeg", ".JPEG", ".png", ".PNG", ".dng", ".DNG"}


def format_size_change(compression_ratio: float) -> str:
    """Format compression ratio as human-readable string."""
    pct = abs(compression_ratio * 100)
    if compression_ratio > 0:
        return f"[green]{pct:.0f}% smaller[/green]"
    elif compression_ratio < 0:
        return f"[yellow]{pct:.0f}% larger[/yellow]"
    else:
        return "same size"


def _load_yaml_config(config_path: Path | None = None) -> dict:
    """Load YAML config file."""
    import yaml

    config_file = config_path or Path(__file__).parent.parent.parent / "config" / "global.yaml"
    if config_file.exists():
        with open(config_file) as f:
            return yaml.safe_load(f) or {}
    return {}


@app.command()
def process(
    source: Annotated[Path, typer.Argument(help="Source folder to process", exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output folder for processed files")] = None,
    profile: Annotated[str, typer.Option("--profile", "-p", help="Encoding profile (see list-profiles)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be done without making changes")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="Force reprocessing (overwrite existing)")] = False,
    limit: Annotated[int, typer.Option("--limit", help="Limit number of videos to transcode (0=unlimited)")] = 0,
    min_size: Annotated[
        int, typer.Option("--min-size", help="Min file size in MB to transcode (smaller files are copied)")
    ] = 0,
    config: ConfigOption = None,
):
    """
    Process a folder - transcode videos using an encoding profile.

    Scans for videos, detects favorites from XMP ratings, and transcodes.

    [bold]Examples:[/bold]

        imt process ./iPhone -o ./output -p nvenc_1080p

        imt process /media/album /media/processed --profile nvenc_4k

        imt process ./videos -o ./encoded --dry-run
    """
    # Determine output directory
    if output is None:
        output = source.parent / f"{source.name}_processed"
        console.print(f"[dim]Output not specified, using: {output}[/dim]")

    # Load configuration
    yaml_cfg = _load_yaml_config(config)
    profiles = load_profiles_from_yaml(yaml_cfg)

    # Use default profile from config if not specified
    if profile is None:
        profile = yaml_cfg.get("transcode", {}).get("default_profile", "balanced")

    if profile and profile not in profiles:
        console.print(f"[red]Error:[/red] Unknown profile: {profile}")
        console.print(f"Available: {', '.join(profiles.keys())}")
        console.print("\nRun [cyan]imt list-profiles[/cyan] to see all options")
        raise typer.Exit(1)

    profile_cfg = profiles.get(profile) if profile else None

    if profile_cfg is None:
        console.print("[red]Error:[/red] No profile specified and no default found")
        raise typer.Exit(1)

    # Create workflow
    workflow = create_archive_workflow(
        source=source,
        output=output,
        profile=profile_cfg,
        dry_run=dry_run,
        force=force,
        limit=limit,
        min_size_mb=min_size,
    )

    # Setup callbacks for progress display
    favorites: set[str] = set()

    def on_scan_complete(videos: int, photos: int, mov_count: int):
        console.print(f"\n[bold]Processing:[/bold] {source.name}")
        console.print(f"  Input:    {source}")
        console.print(f"  Output:   {output}")
        console.print(f"  Profile:  {profile} - {profile_cfg.description}")
        console.print(f"  Videos:   {videos} ({mov_count} to transcode)")
        console.print(f"  Photos:   {photos}")
        console.print()

    def on_transcode_start(path: Path, idx: int, total: int):
        pass  # Progress handled by Rich progress bar

    def on_transcode_complete(path: Path, in_size: int, out_size: int, success: bool):
        nonlocal favorites
        if success:
            in_mb = in_size / (1024 * 1024)
            out_mb = out_size / (1024 * 1024)
            ratio = 1.0 - (out_size / in_size) if in_size > 0 else 0
            size_change = format_size_change(ratio)
            fav = " ★" if path.stem in favorites else ""
            console.print(f"  [green]✓[/green] {path.name}{fav} {in_mb:.1f}MB -> {out_mb:.1f}MB ({size_change})")
        else:
            console.print(f"  [red]✗[/red] {path.name}")

    def on_copy_complete(file_type: str, count: int):
        if count > 0:
            console.print(f"  [blue]⤵[/blue] {count} {file_type} copied")

    callbacks = RunnerCallbacks(
        on_scan_complete=on_scan_complete,
        on_transcode_start=on_transcode_start,
        on_transcode_complete=on_transcode_complete,
        on_copy_complete=on_copy_complete,
    )

    # Dry run: just scan and report
    if dry_run:
        from .actions import classify_favorites as classify_action
        from .actions import scan_folder

        scan_result = scan_folder(source)
        classify_result = classify_action(source)
        favorites = classify_result.favorites

        min_size_bytes = min_size * 1024 * 1024
        MOV_EXTENSIONS = {".mov", ".MOV"}

        console.print(f"\n[bold]Dry Run:[/bold] {source.name}")
        console.print(f"  Profile:  {profile} - {profile_cfg.description}")
        console.print()

        to_transcode = 0
        to_copy = 0
        skipped = 0

        for video in scan_result.videos:
            output_file = output / f"{video.stem}.mp4"
            is_mov = video.suffix in MOV_EXTENSIONS

            if output_file.exists() and not force:
                skipped += 1
                console.print(f"  [dim]SKIP (exists):[/dim] {video.name}")
            elif not is_mov:
                to_copy += 1
                size_mb = video.stat().st_size / (1024 * 1024)
                console.print(f"  [dim]COPY (not MOV):[/dim] {video.name} ({size_mb:.1f}MB)")
            elif min_size_bytes > 0 and video.stat().st_size < min_size_bytes:
                to_copy += 1
                size_mb = video.stat().st_size / (1024 * 1024)
                console.print(f"  [dim]COPY (<{min_size}MB):[/dim] {video.name} ({size_mb:.1f}MB)")
            else:
                to_transcode += 1
                fav_marker = " [yellow]★[/yellow]" if video.stem in favorites else ""
                console.print(f"  [cyan]TRANSCODE:[/cyan] {video.name}{fav_marker}")

        if limit > 0 and to_transcode > limit:
            console.print(f"  [dim]Would limit to {limit} of {to_transcode} videos[/dim]")

        console.print(f"\n  Photos: {len(scan_result.photos)}")
        if skipped > 0:
            console.print(f"\n[yellow]Would skip {skipped} files (already exist). Use --force to redo.[/yellow]")
        console.print("\n[dim]Dry run - no files processed. Remove --dry-run to execute.[/dim]")
        return

    # Run the workflow
    runner = SequentialRunner(dry_run=dry_run)

    # Capture favorites for display
    with console.status("Scanning..."):
        from .actions import classify_favorites as classify_action

        classify_result = classify_action(source)
        favorites = classify_result.favorites

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing...", total=None)
        result = runner.run(workflow, callbacks)
        progress.update(task, completed=True)

    # Summary
    console.print()
    total_copied = result.videos_copied + result.photos_copied
    console.print(
        f"[bold]Complete:[/bold] {result.videos_transcoded} transcoded, {total_copied} copied ({result.photos_copied} photos), {result.tasks_failed} failed"
    )
    if result.videos_transcoded > 0 or total_copied > 0:
        console.print(f"[green]Output files in:[/green] {output}")

    if result.errors:
        console.print("\n[yellow]Errors:[/yellow]")
        for err in result.errors:
            console.print(f"  {err}")


@app.command()
def favorites(
    source: Annotated[Path, typer.Argument(help="Folder to scan for favorites", exists=True, file_okay=False)],
    config: ConfigOption = None,
):
    """List favorite files in a folder (based on XMP ratings)."""
    cfg = get_config(config)

    favs = get_favorites(source, cfg.favorites.rating_threshold)

    if not favs:
        console.print(f"No favorites found in {source.name}")
        return

    console.print(f"[bold]Favorites in {source.name}:[/bold] ({len(favs)} files)\n")

    for f in sorted(favs):
        console.print(f"  {f.name}")


@app.command()
def status(
    source: Annotated[Path, typer.Argument(help="Folder to check status", exists=True, file_okay=False)],
):
    """Show folder contents summary."""
    # Scan source
    scanner = AlbumScanner()
    album_data = scanner.scan(source)

    # Create status table
    table = Table(title=f"Status: {source.name}")

    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Path", str(source))
    table.add_row("Total Files", str(len(album_data.files)))
    table.add_row("Photos", str(len(album_data.photos)))
    table.add_row("Videos", str(len(album_data.videos)))

    console.print(table)


@app.command()
def check():
    """Check system dependencies and show their locations."""
    tools = check_tools_status()

    table = Table(title="System Dependencies")
    table.add_column("Tool", style="cyan")
    table.add_column("Status")
    table.add_column("Path", style="dim")

    for tool, path in tools.items():
        if path:
            status_str = "[green]Available[/green]"
            path_str = str(path)
        else:
            status_str = "[red]Missing[/red]"
            path_str = "-"
        table.add_row(tool, status_str, path_str)

    console.print(table)

    missing = [t for t, p in tools.items() if p is None]
    if missing:
        console.print("\n[yellow]Warning:[/yellow] Some dependencies are missing.")
        console.print("Install system tools: sudo apt install ffmpeg libimage-exiftool-perl")
        if "dovi_tool" in missing or "mp4muxer" in missing:
            console.print("Install DV tools: imt setup")


@app.command()
def scan(
    source: Annotated[Path, typer.Argument(help="Folder to scan", exists=True, file_okay=False)],
):
    """List subfolders in a directory with file counts."""
    album_dirs = [d for d in source.iterdir() if d.is_dir() and not d.name.startswith(".")]

    if not album_dirs:
        console.print("No subfolders found")
        return

    table = Table(title=f"Subfolders in {source.name}")
    table.add_column("Folder", style="cyan")
    table.add_column("Files", justify="right")
    table.add_column("Size", justify="right")

    for album_dir in sorted(album_dirs):
        files = list(album_dir.iterdir())
        file_count = len([f for f in files if f.is_file()])
        size = sum(f.stat().st_size for f in files if f.is_file())
        size_str = f"{size / (1024 * 1024):.1f} MB"

        table.add_row(album_dir.name, str(file_count), size_str)

    console.print(table)


@app.command("transcode")
def transcode_cmd(
    video: Annotated[Path, typer.Argument(help="Video file to transcode", exists=True, dir_okay=False)],
    profile: Annotated[str, typer.Option("--profile", "-p", help="Encoding profile to use (see list-profiles)")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output directory")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", "-f", help="Overwrite existing output file")] = False,
    config: ConfigOption = None,
):
    """
    Transcode a single video file using an encoding profile.

    [bold]Examples:[/bold]

        imt transcode video.MOV -p nvenc_4k

        imt transcode video.MOV --profile balanced -o /output/dir

        imt transcode video.MOV -p nvenc_1080p --overwrite
    """
    # Determine output directory
    output_dir = output or video.parent

    # Check if output exists
    output_file = output_dir / f"{video.stem}.mp4"
    if output_file.exists() and not overwrite:
        console.print(f"[yellow]Warning:[/yellow] Output file exists: {output_file}")
        console.print("Use --overwrite to replace, or specify different --output")
        raise typer.Exit(1)

    # Load profile
    yaml_cfg = _load_yaml_config(config)
    profiles = load_profiles_from_yaml(yaml_cfg)

    if profile not in profiles:
        console.print(f"[red]Error:[/red] Unknown profile: {profile}")
        console.print(f"Available: {', '.join(profiles.keys())}")
        raise typer.Exit(1)

    profile_cfg = profiles[profile]

    console.print(f"[bold]Input:[/bold] {video}")
    console.print(f"[bold]Output:[/bold] {output_dir}")
    console.print(f"[bold]Profile:[/bold] {profile} - {profile_cfg.description}")
    console.print()

    # Run transcode
    result = run_pipeline(video, output_dir, profile_cfg)

    if result.success:
        in_mb = result.input_size / (1024 * 1024)
        out_mb = result.output_size / (1024 * 1024)
        ratio = result.compression_ratio
        if ratio > 0:
            change = f"{ratio * 100:.0f}% smaller"
        elif ratio < 0:
            change = f"{abs(ratio) * 100:.0f}% larger"
        else:
            change = "same size"
        console.print(f"[green]Success![/green] {in_mb:.1f}MB -> {out_mb:.1f}MB ({change})")
        console.print(f"Output: {result.output_path}")
    else:
        console.print(f"[red]Failed:[/red] {result.error_message}")
        raise typer.Exit(1)


@app.command()
def verify(
    file: Annotated[Path, typer.Argument(help="Video file to verify", exists=True, dir_okay=False)],
    reference: Annotated[
        Path | None, typer.Option("--reference", "-r", help="Reference file for comparison", exists=True)
    ] = None,
):
    """
    Verify video file for iPhone Dolby Vision compatibility.

    Checks codec tag, Dolby Vision metadata, HDR metadata, and GPS location.

    [bold]Examples:[/bold]

        imt verify output.mp4                       # Basic verification

        imt verify output.mp4 -r original.MOV       # Compare with original
    """
    console.print(f"\n[bold]Verifying:[/bold] {file.name}")
    if reference:
        console.print(f"[bold]Reference:[/bold] {reference.name}")
    console.print()

    # Run verification
    try:
        result = verify_file(file, reference)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    # Create results table
    table = Table(title="Verification Results")
    table.add_column("Check", style="cyan", no_wrap=False)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Details", style="dim", no_wrap=False)

    for chk in result.checks:
        # Determine status symbol and color
        if chk.status == CheckStatus.PASS:
            status_str = "[green]✓ PASS[/green]"
        elif chk.status == CheckStatus.WARN:
            status_str = "[yellow]⚠ WARN[/yellow]"
        else:
            status_str = "[red]✗ FAIL[/red]"

        # Format details
        details = chk.details or ""
        if chk.expected and chk.actual:
            details = f"{details}\nExpected: {chk.expected}\nActual: {chk.actual}"

        # Highlight critical checks
        check_name = chk.name
        if chk.name in ("Codec tag (iPhone compatible)", "DV container boxes (dvcC/dvvC)", "GPS location"):
            if chk.status == CheckStatus.FAIL:
                check_name = f"[bold]{chk.name}[/bold]"

        table.add_row(check_name, status_str, details)

    console.print(table)

    # Overall assessment
    console.print()
    console.print("[bold]Overall Assessment:[/bold]")
    console.print(f"  Critical failures: {result.critical_failures}")
    console.print(f"  Warnings: {result.warnings}")
    console.print()

    if result.is_compatible:
        console.print("[green]✓ File is compatible with iPhone Dolby Vision playback[/green]")

        if result.has_dolby_vision:
            console.print("[green]✓ Should display 'Dolby Vision' badge on iPhone[/green]")
        else:
            # Check if it's HDR
            has_hdr = any(
                chk.name == "Color transfer (HDR)" and chk.status == CheckStatus.PASS for chk in result.checks
            )
            if has_hdr:
                console.print("[yellow]⚠ Will display 'HDR' badge (no Dolby Vision)[/yellow]")
    else:
        console.print("[red]✗ File has critical compatibility issues![/red]")
        console.print("[red]  iPhone may reject or not display properly[/red]")

        # Show critical issues
        critical_issues = [
            chk
            for chk in result.checks
            if chk.status == CheckStatus.FAIL
            and chk.name in ("Codec tag (iPhone compatible)", "DV container boxes (dvcC/dvvC)", "GPS location")
        ]

        if critical_issues:
            console.print("\n[bold]Critical Issues:[/bold]")
            for issue in critical_issues:
                console.print(f"  [red]•[/red] {issue.name}: {issue.details}")

    console.print()


@app.command()
def compare(
    video: Annotated[Path, typer.Argument(help="Video file to compare", exists=True, dir_okay=False)],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output directory")] = None,
    profiles_arg: Annotated[list[str] | None, typer.Option("--profile", "-p", help="Specific profiles to run")] = None,
    config: ConfigOption = None,
):
    """
    Compare encoding profiles on a video file.

    Runs multiple encoding strategies and compares results (size, speed, quality).

    [bold]Examples:[/bold]

        imt compare video.MOV                        # Run all profiles

        imt compare video.MOV -p nvenc_4k -p balanced  # Run specific profiles

        imt compare video.MOV -o /tmp/comparison     # Custom output dir
    """
    import time

    # Load config
    yaml_cfg = _load_yaml_config(config)
    profiles = load_profiles_from_yaml(yaml_cfg)

    if not profiles:
        console.print("[red]Error:[/red] No profiles defined in config")
        raise typer.Exit(1)

    # Determine which profiles to run
    if profiles_arg:
        profile_names = list(profiles_arg)
        # Validate profile names
        for name in profile_names:
            if name not in profiles:
                console.print(f"[red]Error:[/red] Unknown profile: {name}")
                console.print(f"Available: {', '.join(profiles.keys())}")
                raise typer.Exit(1)
    else:
        profile_names = list(profiles.keys())

    # Setup output directory
    output_dir = output or video.parent / "comparison"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get input info
    input_size = video.stat().st_size
    input_size_mb = input_size / (1024 * 1024)

    console.print(f"\n[bold]Comparing Profiles:[/bold] {video.name}")
    console.print(f"[bold]Input Size:[/bold] {input_size_mb:.1f} MB")
    console.print(f"[bold]Output Dir:[/bold] {output_dir}")
    console.print(f"[bold]Profiles:[/bold] {', '.join(profile_names)}")
    console.print()

    # Run each profile
    results: list[PipelineResult] = []

    for name in profile_names:
        profile_cfg = profiles[name]

        console.print(f"[cyan]Running:[/cyan] {name} - {profile_cfg.description}")

        start_time = time.time()
        result = run_pipeline(video, output_dir, profile_cfg)
        elapsed = time.time() - start_time

        if result.success:
            in_mb = result.input_size / (1024 * 1024)
            out_mb = result.output_size / (1024 * 1024)
            size_change = format_size_change(result.compression_ratio)
            speed = result.speed_ratio
            console.print(
                f"  [green]✓[/green] {in_mb:.1f}MB -> {out_mb:.1f}MB ({size_change}) in {elapsed:.1f}s ({speed:.2f}x)"
            )
        else:
            console.print(f"  [red]✗[/red] Failed: {result.error_message}")

        results.append(result)

    # Summary table
    console.print()
    table = Table(title="Profile Comparison Results")
    table.add_column("Profile", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Compression", justify="right")
    table.add_column("Time", justify="right")
    table.add_column("Speed", justify="right")
    table.add_column("Status")

    # Add original as reference
    table.add_row("[dim]Original[/dim]", f"{input_size_mb:.1f} MB", "-", "-", "-", "[dim]-[/dim]")

    for res in results:
        if res.success:
            size_mb = res.output_size / (1024 * 1024)
            ratio = res.compression_ratio
            if ratio > 0:
                compression = f"-{abs(ratio) * 100:.0f}%"
            elif ratio < 0:
                compression = f"+{abs(ratio) * 100:.0f}%"
            else:
                compression = "0%"
            time_str = f"{res.encode_time_seconds:.1f}s"
            speed = f"{res.speed_ratio:.2f}x"
            status_str = "[green]✓[/green]"
        else:
            size_mb = 0
            compression = "-"
            time_str = "-"
            speed = "-"
            status_str = "[red]✗[/red]"

        table.add_row(
            res.pipeline_name, f"{size_mb:.1f} MB" if res.success else "-", compression, time_str, speed, status_str
        )

    console.print(table)

    # Show output files
    console.print("\n[bold]Output Files:[/bold]")
    for res in results:
        if res.success and res.output_path:
            console.print(f"  {res.output_path}")

    console.print()


@app.command()
def setup(
    force: Annotated[bool, typer.Option("--force", "-f", help="Reinstall tools even if present")] = False,
):
    """
    Auto-install external dependencies (dovi_tool, mp4muxer).

    Downloads pre-built binaries when available, compiles from source when needed.
    Tools are installed to ~/.local/share/ios-media-toolkit/bin/

    [bold]Examples:[/bold]

        imt setup                   # Install missing tools

        imt setup --force           # Reinstall all tools
    """
    success = run_setup(force)
    if not success:
        raise typer.Exit(1)


@app.command("list-profiles")
def list_profiles(config: ConfigOption = None):
    """List available encoding profiles."""
    yaml_cfg = _load_yaml_config(config)
    profiles = load_profiles_from_yaml(yaml_cfg)

    if not profiles:
        console.print("[yellow]No profiles defined in config[/yellow]")
        return

    table = Table(title="Available Encoding Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Encoder")
    table.add_column("Resolution")
    table.add_column("Mode")
    table.add_column("Quality")
    table.add_column("DV")
    table.add_column("Description")

    for name, profile in profiles.items():
        enc = profile.encoder.value
        res = profile.resolution
        mode = profile.mode.value

        if profile.mode.value == "crf":
            quality = f"CRF {profile.crf or '?'}"
        else:
            quality = profile.bitrate or "?"

        dv = "[green]✓[/green]" if profile.preserve_dolby_vision else "[dim]-[/dim]"
        desc = profile.description

        table.add_row(name, enc, res, mode, quality, dv, desc)

    console.print(table)


def main_cli():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main_cli()
