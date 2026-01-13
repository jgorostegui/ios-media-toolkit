# Dolby Vision Tools Installation Guide

This guide explains how to install the tools required for Dolby Vision preservation during video transcoding.

## Required Tools

| Tool | Purpose | Source |
|------|---------|--------|
| **dovi_tool** | Extract/inject Dolby Vision RPU metadata | [quietvoid/dovi_tool](https://github.com/quietvoid/dovi_tool) |
| **mp4muxer** | Mux HEVC with proper DV container boxes | [Dolby dlb_mp4base](https://github.com/DolbyLaboratories/dlb_mp4base) |

## dovi_tool Installation

### Option 1: Download Pre-built Binary (Recommended)

```bash
# Download latest release (check GitHub for current version)
wget https://github.com/quietvoid/dovi_tool/releases/download/2.3.1/dovi_tool-2.3.1-x86_64-unknown-linux-musl.tar.gz

# Extract
tar -xzf dovi_tool-2.3.1-x86_64-unknown-linux-musl.tar.gz

# Make executable and move to desired location
chmod +x dovi_tool
sudo mv dovi_tool /usr/local/bin/
# Or keep in a custom location and configure in global.yaml

# Verify installation
dovi_tool --version
```

### Option 2: Build from Source

Requires Rust toolchain.

```bash
# Install Rust if not already installed
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Clone and build
git clone https://github.com/quietvoid/dovi_tool.git
cd dovi_tool
cargo build --release

# Binary will be at: target/release/dovi_tool
sudo cp target/release/dovi_tool /usr/local/bin/
```

## mp4muxer Installation (Dolby dlb_mp4base)

mp4muxer must be compiled from source.

### Prerequisites

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install build-essential cmake git

# Fedora/RHEL
sudo dnf install gcc gcc-c++ make cmake git
```

### Build from Source

```bash
# Clone the repository
git clone https://github.com/DolbyLaboratories/dlb_mp4base.git
cd dlb_mp4base

# Build using make
cd make/mp4muxer/linux_amd64
make

# Binary will be at: mp4muxer_release
# Copy to desired location
sudo cp mp4muxer_release /usr/local/bin/mp4muxer
# Or keep in place and configure path in global.yaml
```

### Verify Build

```bash
./mp4muxer_release --help
```

## Configuration

After installation, update `config/global.yaml` with the tool paths:

```yaml
tools:
  # Leave empty to use system PATH, or specify full path
  dovi_tool: "/usr/local/bin/dovi_tool"
  mp4muxer: "/usr/local/bin/mp4muxer"
```

## Dolby Vision Transcoding Workflow

The complete workflow for re-encoding while preserving Dolby Vision:

```bash
# 1. Extract HEVC bitstream from source
ffmpeg -i source.MOV -c:v copy -bsf:v hevc_mp4toannexb -f hevc temp.hevc

# 2. Extract Dolby Vision RPU metadata
dovi_tool extract-rpu temp.hevc -o RPU.bin

# 3. Re-encode video (adjust CRF for quality: 18-22 recommended)
ffmpeg -i source.MOV \
  -c:v libx265 -preset veryslow -crf 20 \
  -x265-params "hdr10=1:repeat-headers=1:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc" \
  -pix_fmt yuv420p10le -an \
  -f hevc reencoded.hevc

# 4. Inject RPU back into re-encoded file
dovi_tool inject-rpu -i reencoded.hevc -r RPU.bin -o final_DV.hevc

# 5. Mux with mp4muxer (creates proper dvcC/dvvC boxes)
mp4muxer -i final_DV.hevc -o video_DV.mp4 \
  --dv-profile 8 \
  --dv-bl-compatible-id 1 \
  --hvc1flag 0 \
  --mpeg4-comp-brand mp42,iso6,isom,msdh,dby1 \
  --overwrite

# 6. Add audio and metadata
ffmpeg -i video_DV.mp4 -i source.MOV \
  -map 0:v:0 -map 1:a:0 \
  -c copy -strict unofficial \
  -tag:v hvc1 \
  -map_metadata 1 \
  -movflags +faststart \
  output.mp4
```

## Critical Parameters

### mp4muxer Flags

| Flag | Value | Purpose |
|------|-------|---------|
| `--dv-profile` | 8 | iPhone Dolby Vision profile |
| `--dv-bl-compatible-id` | 1 | Base layer compatibility (HDR10) |
| `--hvc1flag` | 0 | **CRITICAL**: Creates hvc1 codec tag for iPhone |
| `--mpeg4-comp-brand` | mp42,iso6,isom,msdh,dby1 | MP4 brand compatibility |

### ffmpeg Final Mux

| Flag | Value | Purpose |
|------|-------|---------|
| `-tag:v` | hvc1 | **CRITICAL**: Ensures hvc1 tag preserved |
| `-strict` | unofficial | Allows DV stream copying |
| `-map_metadata` | 1 | Preserve GPS, dates, device info |

## Verification

After transcoding, verify the output:

```bash
# Check codec tag (must be hvc1 or dvh1, NOT hev1)
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_tag_string \
  -of default=noprint_wrappers=1 output.mp4

# Check Dolby Vision profile
ffprobe -v error -show_entries stream_side_data=dv_profile \
  -of default=noprint_wrappers=1 output.mp4

# Check for dvcC/dvvC container boxes
ffprobe -v trace output.mp4 2>&1 | grep -E "dvvC|dvcC"
```

Or use the integrated CLI command:

```bash
imt verify output.mp4 -r source.MOV
```

## Troubleshooting

### File not showing on iPhone

**Cause**: Wrong codec tag (hev1 instead of hvc1)

**Fix**: Use `--hvc1flag 0` with mp4muxer and `-tag:v hvc1` with ffmpeg

### "HDR" badge instead of "Dolby Vision"

**Cause**: Missing dvcC/dvvC container boxes

**Fix**: Ensure mp4muxer is used for muxing, not just ffmpeg

### GPS location lost

**Cause**: Metadata not properly copied

**Fix**: Use `-map_metadata 1` and verify with `imt verify`

## Quality Guidelines

| Use Case | CRF | Expected Size | Quality |
|----------|-----|---------------|---------|
| Archival | 18 | ~50% of original | Near-lossless |
| High quality | 20 | ~35% of original | Excellent |
| Balanced | 22 | ~25% of original | Very good |
| Space-saving | 25 | ~10% of original | Good |

For 4K iPhone videos (typically 70-80 Mbps source):
- CRF 20 → ~25 Mbps → ~35% of original size
- CRF 25 → ~7 Mbps → ~10% of original size
