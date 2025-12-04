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
    "over Speed-up pack"
    "over speed-up pack"
]

# Specific beatmap set IDs to nerf (if you want to manually add specific sets)
NERFED_MAPSET_IDS = {
    # Add specific set IDs here if needed
    # Example: 123456, 789012
}

# Mapper-specific nerfs (mapper name -> multiplier)
# Example: "MapperName": 0.90 means 10% nerf for all maps by that mapper
MAPPER_NERFS = {
    # 5% nerf for these mappers (reduced from 15%)
    "None1637": 0.70,
    "[-Omni-]": 0.95,
    "juliet": 0.95,
    "xAsuna": 0.95,
    "quantumvortex": 0.95,
    "Toffery2002": 0.65,
    "helloisuck": 0.95,
    "hool": 0.75,
    "Learner_": 0.40,  # 60% nerf
    "tazuwik": 0.75,  # 25% nerf (reduced from 35%)
    "kselon": 0.75,  # 25% nerf (reduced from 35%)
    "DTtheCarry": 0.65,  # 35% nerf
}

# Default nerf multiplier for speed-up maps (15% nerf)
MAPSET_NERF_MULTIPLIER = 0.85  # 15% nerf


def should_nerf_map(title: str, artist: str, creator: str, set_id: int, mods: int = 0) -> float:
    """
    Check if a map should be nerfed and return the nerf multiplier.
    
    Args:
        title: Map title
        artist: Map artist
        creator: Mapper name
        set_id: Beatmap set ID
        mods: Mods used (for detecting Relax mod)
    
    Returns:
        float: Multiplier to apply (1.0 = no nerf, 0.85 = 15% nerf)
    """
    # Check if Relax mod is active (Relax = 128)
    is_relax = bool(mods & 128)
    
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
        base_nerf = MAPPER_NERFS[creator]
        
        # Apply additional nerf for Relax mod (reduce by another 15%)
        if is_relax:
            # If base nerf is 0.65 (35% nerf), relax makes it 0.5525 (44.75% total nerf)
            # Formula: base_nerf * 0.85 (additional 15% reduction)
            return base_nerf * 0.85
        
        return base_nerf
    
    # No nerf
    return 1.0
