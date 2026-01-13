"""
Setup tools module - Auto-install external dependencies (dovi_tool, mp4muxer).

Handles downloading pre-built binaries and compiling from source when needed.
"""

import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

# Standard user bin directory following XDG spec
USER_BIN_DIR = Path.home() / ".local" / "share" / "ios-media-toolkit" / "bin"

# Tool versions
DOVI_TOOL_VERSION = "2.3.1"
DOVI_TOOL_RELEASES = {
    "x86_64": f"https://github.com/quietvoid/dovi_tool/releases/download/{DOVI_TOOL_VERSION}/dovi_tool-{DOVI_TOOL_VERSION}-x86_64-unknown-linux-musl.tar.gz",
    "aarch64": f"https://github.com/quietvoid/dovi_tool/releases/download/{DOVI_TOOL_VERSION}/dovi_tool-{DOVI_TOOL_VERSION}-aarch64-unknown-linux-musl.tar.gz",
}


def get_arch() -> str:
    """Get normalized architecture string."""
    arch = platform.machine().lower()
    if arch in ("x86_64", "amd64"):
        return "x86_64"
    elif arch in ("aarch64", "arm64"):
        return "aarch64"
    return arch


def check_build_deps() -> tuple[bool, list[str]]:
    """
    Check if build dependencies are available.

    Returns:
        Tuple of (all_present, missing_tools)
    """
    required = ["git", "make", "cmake", "g++"]
    missing = [tool for tool in required if not shutil.which(tool)]
    return len(missing) == 0, missing


def get_tool_path(tool_name: str) -> Path | None:
    """
    Find a tool in standard locations.

    Search order:
    1. User local bin (~/.local/share/ios-media-toolkit/bin)
    2. System PATH
    """
    # Check user local bin first
    user_path = USER_BIN_DIR / tool_name
    if user_path.exists():
        return user_path

    # Check system PATH
    sys_path = shutil.which(tool_name)
    if sys_path:
        return Path(sys_path)

    return None


def install_dovi_tool(force: bool = False) -> bool:
    """
    Download and install dovi_tool binary.

    Args:
        force: Reinstall even if already present

    Returns:
        True if successful
    """
    target = USER_BIN_DIR / "dovi_tool"

    if target.exists() and not force:
        console.print(f"[dim]dovi_tool already installed at {target}[/dim]")
        return True

    arch = get_arch()
    if arch not in DOVI_TOOL_RELEASES:
        console.print(f"[red]Error:[/red] Unsupported architecture for auto-download: {arch}")
        console.print("Please install dovi_tool manually from https://github.com/quietvoid/dovi_tool/releases")
        return False

    url = DOVI_TOOL_RELEASES[arch]

    try:
        USER_BIN_DIR.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tar_path = tmp_path / "dovi.tar.gz"

            console.print(f"[dim]Downloading from {url}[/dim]")
            urllib.request.urlretrieve(url, tar_path)

            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(path=tmp_path)

            # Find the binary (might be in subdirectory)
            extracted = list(tmp_path.glob("**/dovi_tool"))
            if not extracted:
                console.print("[red]Error:[/red] dovi_tool binary not found in archive")
                return False

            shutil.move(str(extracted[0]), str(target))
            target.chmod(target.stat().st_mode | stat.S_IEXEC)

        console.print(f"[green]✓[/green] dovi_tool installed to {target}")
        return True

    except Exception as e:
        console.print(f"[red]Error downloading dovi_tool:[/red] {e}")
        return False


def compile_mp4muxer(force: bool = False) -> bool:
    """
    Clone and compile mp4muxer from source.

    Args:
        force: Recompile even if already present

    Returns:
        True if successful
    """
    target = USER_BIN_DIR / "mp4muxer"

    if target.exists() and not force:
        console.print(f"[dim]mp4muxer already installed at {target}[/dim]")
        return True

    # Check build dependencies
    deps_ok, missing = check_build_deps()
    if not deps_ok:
        console.print(f"[red]Error:[/red] Missing build tools: {', '.join(missing)}")
        if platform.system() == "Linux":
            console.print("[dim]Install with: sudo apt-get install build-essential cmake git[/dim]")
        return False

    try:
        USER_BIN_DIR.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)

            # Clone repo
            console.print("[dim]Cloning dlb_mp4base repository...[/dim]")
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "https://github.com/DolbyLaboratories/dlb_mp4base.git"],
                cwd=cwd,
                capture_output=True,
                timeout=120,
            )
            if result.returncode != 0:
                console.print(f"[red]Error cloning repository:[/red] {result.stderr.decode()}")
                return False

            # Determine build directory based on architecture
            arch = get_arch()
            if arch == "aarch64":
                build_subdir = "linux_arm64"
            else:
                build_subdir = "linux_amd64"

            build_dir = cwd / "dlb_mp4base" / "make" / "mp4muxer" / build_subdir

            if not build_dir.exists():
                console.print(f"[red]Error:[/red] Build directory not found: {build_dir}")
                console.print("[dim]Your architecture may not be supported[/dim]")
                return False

            # Build
            console.print("[dim]Compiling mp4muxer...[/dim]")
            result = subprocess.run(
                ["make"],
                cwd=build_dir,
                capture_output=True,
                timeout=300,
            )
            if result.returncode != 0:
                console.print(f"[red]Compilation failed:[/red] {result.stderr.decode()}")
                return False

            # Find and install binary
            binary = build_dir / "mp4muxer_release"
            if not binary.exists():
                console.print("[red]Error:[/red] Compiled binary not found")
                return False

            shutil.move(str(binary), str(target))
            target.chmod(target.stat().st_mode | stat.S_IEXEC)

        console.print(f"[green]✓[/green] mp4muxer installed to {target}")
        return True

    except subprocess.TimeoutExpired:
        console.print("[red]Error:[/red] Build timed out")
        return False
    except Exception as e:
        console.print(f"[red]Error compiling mp4muxer:[/red] {e}")
        return False


def run_setup(force: bool = False) -> bool:
    """
    Run full setup: install dovi_tool and compile mp4muxer.

    Args:
        force: Reinstall tools even if present

    Returns:
        True if all tools installed successfully
    """
    console.print("\n[bold]iOS Media Toolkit - Setup External Tools[/bold]\n")
    console.print(f"Install directory: {USER_BIN_DIR}\n")

    success = True

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Install dovi_tool
        task1 = progress.add_task("Installing dovi_tool...", total=None)
        if install_dovi_tool(force):
            progress.update(task1, description="[green]✓ dovi_tool installed[/green]")
        else:
            progress.update(task1, description="[red]✗ dovi_tool failed[/red]")
            success = False

        # Compile mp4muxer
        task2 = progress.add_task("Compiling mp4muxer...", total=None)
        if compile_mp4muxer(force):
            progress.update(task2, description="[green]✓ mp4muxer compiled[/green]")
        else:
            progress.update(task2, description="[red]✗ mp4muxer failed[/red]")
            success = False

    console.print()

    if success:
        console.print("[green]Setup complete![/green]")
        console.print(f"\nTools installed to: [cyan]{USER_BIN_DIR}[/cyan]")
        console.print("\nYou can now use Dolby Vision preservation features.")
    else:
        console.print("[yellow]Some tools failed to install.[/yellow]")
        console.print("You may need to install them manually.")

    return success


def check_tools_status() -> dict[str, Path | None]:
    """
    Check status of all external tools.

    Returns:
        Dict mapping tool name to path (None if not found)
    """
    tools = {
        "ffmpeg": get_tool_path("ffmpeg"),
        "ffprobe": get_tool_path("ffprobe"),
        "exiftool": get_tool_path("exiftool"),
        "dovi_tool": get_tool_path("dovi_tool"),
        "mp4muxer": get_tool_path("mp4muxer"),
    }
    return tools
