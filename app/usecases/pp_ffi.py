"""
Python bindings for the osu-pp-ffi library.

This module provides a Python interface to the Rust-based PP calculation library
with all custom logic from bancho-new (multipliers, nerfs, buffs, caps).

Example usage:
    from pp_ffi import PPCalculator
    
    calc = PPCalculator()
    
    with open('beatmap.osu', 'rb') as f:
        beatmap_data = f.read()
    
    result = calc.calculate(
        beatmap_data=beatmap_data,
        mods=64,  # DT
        accuracy=98.5,
        combo=1000,
        n_misses=2,
        map_title="Some Map",
        map_artist="Artist",
        map_creator="Mapper",
        player_id=4,
        apply_pp_cap=True
    )
    
    print(f"PP: {result.pp:.2f}")
    print(f"Stars: {result.stars:.2f}")
"""

import ctypes
import os
import platform
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class PPResult:
    """Result of PP calculation"""
    pp: float
    pp_aim: float
    pp_speed: float
    pp_acc: float
    pp_flashlight: float
    stars: float
    effective_miss_count: float


class CScoreParams(ctypes.Structure):
    """C-compatible score parameters structure"""
    _fields_ = [
        ("mode", ctypes.c_int),
        ("mods", ctypes.c_uint),
        ("combo", ctypes.c_int),
        ("accuracy", ctypes.c_double),
        ("n300", ctypes.c_int),
        ("n100", ctypes.c_int),
        ("n50", ctypes.c_int),
        ("n_geki", ctypes.c_int),
        ("n_katu", ctypes.c_int),
        ("n_misses", ctypes.c_int),
    ]


class CPPResult(ctypes.Structure):
    """C-compatible PP result structure"""
    _fields_ = [
        ("pp", ctypes.c_double),
        ("pp_aim", ctypes.c_double),
        ("pp_speed", ctypes.c_double),
        ("pp_acc", ctypes.c_double),
        ("pp_flashlight", ctypes.c_double),
        ("stars", ctypes.c_double),
        ("effective_miss_count", ctypes.c_double),
        ("error_message", ctypes.c_char_p),
    ]


class CMapMetadata(ctypes.Structure):
    """C-compatible map metadata structure"""
    _fields_ = [
        ("title", ctypes.c_char_p),
        ("artist", ctypes.c_char_p),
        ("creator", ctypes.c_char_p),
    ]


def _get_library_path() -> Path:
    """Get the path to the compiled FFI library"""
    # Determine library extension based on platform
    if platform.system() == "Windows":
        lib_name = "osu_pp_ffi.dll"
    elif platform.system() == "Darwin":
        lib_name = "libosu_pp_ffi.dylib"
    else:
        lib_name = "libosu_pp_ffi.so"
    
    # Look for the library in the target/release directory
    lib_path = Path(__file__).parent.parent.parent / "pp-ffi" / "target" / "release" / lib_name
    
    if not lib_path.exists():
        raise FileNotFoundError(
            f"FFI library not found at {lib_path}. "
            f"Please build it first with: cd pp-ffi && cargo build --release"
        )
    
    return lib_path


class PPCalculator:
    """
    Python wrapper for the osu-pp-ffi library.
    
    This calculator implements all custom PP logic from bancho-new:
    - Custom multipliers for aim/speed/accuracy/flashlight
    - Miss penalty adjustments
    - Global 1.25x multiplier
    - Map-specific nerfs (speed-up maps, specific mappers)
    - Player-specific buffs
    - PP caps
    """
    
    def __init__(self, config_json: Optional[str] = None):
        """
        Initialize the PP calculator.
        
        Args:
            config_json: Optional JSON string with custom configuration.
                        If None, uses default configuration.
        """
        # Load the FFI library
        lib_path = _get_library_path()
        self._lib = ctypes.CDLL(str(lib_path))
        
        # Define function signatures
        self._lib.osu_pp_calculator_new.restype = ctypes.c_void_p
        self._lib.osu_pp_calculator_new.argtypes = []
        
        self._lib.osu_pp_calculator_new_with_config.restype = ctypes.c_void_p
        self._lib.osu_pp_calculator_new_with_config.argtypes = [ctypes.c_char_p]
        
        self._lib.osu_pp_calculator_free.restype = None
        self._lib.osu_pp_calculator_free.argtypes = [ctypes.c_void_p]
        
        self._lib.osu_pp_calculate.restype = CPPResult
        self._lib.osu_pp_calculate.argtypes = [
            ctypes.c_void_p,  # calculator
            ctypes.POINTER(ctypes.c_ubyte),  # beatmap_data
            ctypes.c_size_t,  # beatmap_len
            CScoreParams,  # score
            ctypes.POINTER(CMapMetadata),  # metadata
            ctypes.c_int,  # player_id
            ctypes.c_int,  # apply_pp_cap
        ]
        
        self._lib.osu_pp_free_error.restype = None
        self._lib.osu_pp_free_error.argtypes = [ctypes.c_char_p]
        
        self._lib.osu_pp_version.restype = ctypes.c_char_p
        self._lib.osu_pp_version.argtypes = []
        
        # Create calculator instance
        if config_json:
            self._calculator = self._lib.osu_pp_calculator_new_with_config(
                config_json.encode('utf-8')
            )
            if not self._calculator:
                raise ValueError("Failed to create calculator with provided config")
        else:
            self._calculator = self._lib.osu_pp_calculator_new()
    
    def __del__(self):
        """Free the calculator when the object is destroyed"""
        if hasattr(self, '_calculator') and self._calculator:
            self._lib.osu_pp_calculator_free(self._calculator)
    
    def calculate(
        self,
        beatmap_data: bytes,
        mode: int = 0,
        mods: int = 0,
        combo: Optional[int] = None,
        accuracy: Optional[float] = None,
        n300: Optional[int] = None,
        n100: Optional[int] = None,
        n50: Optional[int] = None,
        n_geki: Optional[int] = None,
        n_katu: Optional[int] = None,
        n_misses: Optional[int] = None,
        map_title: Optional[str] = None,
        map_artist: Optional[str] = None,
        map_creator: Optional[str] = None,
        player_id: Optional[int] = None,
        apply_pp_cap: bool = True,
    ) -> PPResult:
        """
        Calculate PP for a score.
        
        Args:
            beatmap_data: Raw .osu file contents as bytes
            mode: Game mode (0=std, 1=taiko, 2=catch, 3=mania, 4=relax, 8=autopilot)
            mods: Mods as integer (e.g., 64 for DT, 128 for Relax)
            combo: Max combo achieved
            accuracy: Accuracy percentage (0-100)
            n300: Number of 300s
            n100: Number of 100s
            n50: Number of 50s
            n_geki: Number of gekis
            n_katu: Number of katus
            n_misses: Number of misses
            map_title: Map title for nerf detection
            map_artist: Map artist for nerf detection
            map_creator: Mapper name for nerf detection
            player_id: Player ID for player-specific buffs
            apply_pp_cap: Whether to apply PP caps
        
        Returns:
            PPResult with calculated PP values
        
        Raises:
            RuntimeError: If calculation fails
        """
        # Prepare score parameters
        score = CScoreParams(
            mode=mode,
            mods=mods,
            combo=combo if combo is not None else -1,
            accuracy=accuracy if accuracy is not None else -1.0,
            n300=n300 if n300 is not None else -1,
            n100=n100 if n100 is not None else -1,
            n50=n50 if n50 is not None else -1,
            n_geki=n_geki if n_geki is not None else -1,
            n_katu=n_katu if n_katu is not None else -1,
            n_misses=n_misses if n_misses is not None else -1,
        )
        
        # Prepare metadata if provided
        metadata = None
        if map_title or map_artist or map_creator:
            metadata = CMapMetadata(
                title=map_title.encode('utf-8') if map_title else None,
                artist=map_artist.encode('utf-8') if map_artist else None,
                creator=map_creator.encode('utf-8') if map_creator else None,
            )
        
        # Convert beatmap data to C array
        beatmap_array = (ctypes.c_ubyte * len(beatmap_data)).from_buffer_copy(beatmap_data)
        
        # Call FFI function
        result = self._lib.osu_pp_calculate(
            self._calculator,
            beatmap_array,
            len(beatmap_data),
            score,
            ctypes.byref(metadata) if metadata else None,
            player_id if player_id is not None else -1,
            1 if apply_pp_cap else 0,
        )
        
        # Check for errors
        if result.error_message:
            error_msg = result.error_message.decode('utf-8')
            self._lib.osu_pp_free_error(result.error_message)
            raise RuntimeError(f"PP calculation failed: {error_msg}")
        
        return PPResult(
            pp=result.pp,
            pp_aim=result.pp_aim,
            pp_speed=result.pp_speed,
            pp_acc=result.pp_acc,
            pp_flashlight=result.pp_flashlight,
            stars=result.stars,
            effective_miss_count=result.effective_miss_count,
        )
    
    def get_version(self) -> str:
        """Get the library version"""
        return self._lib.osu_pp_version().decode('utf-8')
