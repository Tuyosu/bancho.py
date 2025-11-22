"""
Configuration for map-specific and mapper-specific PP nerfs.
"""

# Patterns to detect in map titles/artists (case-insensitive)
# Maps matching these patterns will receive MAPSET_NERF_MULTIPLIER
NERFED_TITLE_PATTERNS = [
    "speed-up",
    "speed up",
    "sped up",
    "speed-up map",
    "speed up map pack",
    "sped up pack",
]

# Specific beatmap set IDs to nerf (if you want to manually add specific sets)
NERFED_MAPSET_IDS = {
    # Add specific set IDs here if needed
    # Example: 123456, 789012
}

# Mapper-specific nerfs (mapper name -> multiplier)
# Example: "MapperName": 0.90 means 10% nerf for all maps by that mapper
MAPPER_NERFS = {
    # 15% nerf for these mappers
    "None1637": 0.85,
    "[-Omni-]": 0.85,
    "juliet": 0.85,
    "xAsuna": 0.85,
    "quantumvortex": 0.85,
    "Toffery2002": 0.85,
    "helloisuck": 0.85,
    "hool": 0.85,
}

# Default nerf multiplier for speed-up maps (15% nerf)
MAPSET_NERF_MULTIPLIER = 0.85  # 15% nerf


def should_nerf_map(title: str, artist: str, creator: str, set_id: int) -> float:
    """
    Check if a map should be nerfed and return the nerf multiplier.
    
    Returns:
        float: Multiplier to apply (1.0 = no nerf, 0.85 = 15% nerf)
    """
    title_lower = title.lower()
    artist_lower = artist.lower()
    
    # Check for title pattern matches
    for pattern in NERFED_TITLE_PATTERNS:
        if pattern in title_lower or pattern in artist_lower:
            return MAPSET_NERF_MULTIPLIER
    
    # Check for specific set ID
    if set_id in NERFED_MAPSET_IDS:
        return MAPSET_NERF_MULTIPLIER
    
    # Check for mapper-specific nerf
    if creator in MAPPER_NERFS:
        return MAPPER_NERFS[creator]
    
    # No nerf
    return 1.0
