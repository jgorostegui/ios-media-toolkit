"""
Encoding profiles - Configuration for video encoding strategies.

Terminology:
- Profile: Settings for how to encode (encoder, bitrate, quality)
- Workflow: Sequence of tasks to execute
- Runner: Engine that executes workflows

A profile defines HOW to encode, not WHAT to do.
"""

from .encoder import EncoderProfile, load_encoder_profile, resolve_tool_path

# Re-export EncoderProfile as EncodingProfile for API compatibility
EncodingProfile = EncoderProfile


def load_profile(name: str, config_dict: dict, tools_config: dict) -> EncodingProfile:
    """
    Load an encoding profile from config dictionary.

    Args:
        name: Profile name
        config_dict: Profile configuration from YAML
        tools_config: Tools configuration for path resolution

    Returns:
        EncodingProfile instance
    """
    return load_encoder_profile(name, config_dict, tools_config)


def load_profiles_from_yaml(yaml_cfg: dict) -> dict[str, EncodingProfile]:
    """
    Load all profiles from YAML configuration.

    Args:
        yaml_cfg: Full YAML configuration dictionary

    Returns:
        Dictionary of profile name to EncodingProfile
    """
    # Support: video.profiles (new), profiles (legacy), pipelines (legacy)
    video_cfg = yaml_cfg.get("video", {})
    profiles_config = video_cfg.get("profiles") or yaml_cfg.get("profiles") or yaml_cfg.get("pipelines", {})
    tools_config = yaml_cfg.get("tools", {})

    profiles = {}
    for name, config_dict in profiles_config.items():
        profiles[name] = load_profile(name, config_dict, tools_config)

    return profiles


__all__ = [
    "EncodingProfile",
    "load_profile",
    "load_profiles_from_yaml",
    "resolve_tool_path",
]
