"""Configuration for the Coloring Pixels bot."""
import os
from pathlib import Path

# Game paths
GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Coloring Pixels")
EXE_PATH = GAME_DIR / "ColoringPixels.exe"
MONO_DLL = GAME_DIR / "MonoBleedingEdge" / "EmbedRuntime" / "mono-2.0-bdwgc.dll"
ASSEMBLY_CSHARP_PATH = GAME_DIR / "ColoringPixels_Data" / "Managed" / "Assembly-CSharp.dll"

# Process settings
PROCESS_NAME = "ColoringPixels"
WINDOW_TITLE = "ColoringPixels"

# Display settings
WINDOW_WIDTH = 1680
WINDOW_HEIGHT = 1050

# UI y-coordinate cutoff for palette (from ClickTest yCuttoff ~140 * canvas scale)
PALETTE_Y_CUTOFF = 155

# Memory settings
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400

# Mono class names
NAMESPACE = ""
CLASS_CROSS_LEVEL_STORAGE_HOLDER = "CrossLevelStorageHolder"
CLASS_CROSS_LEVEL_STORAGE = "CrossLevelStorage"
CLASS_CLICK_TEST = "ClickTest"
CLASS_CAMERA = "UnityEngine.Camera"
CLASS_TRANSFORM = "UnityEngine.Transform"
CLASS_GRID_LAYOUT = "UnityEngine.GridLayout"
CLASS_VECTOR3 = "UnityEngine.Vector3"
CLASS_VECTOR3INT = "UnityEngine.Vector3Int"

# Known field names
FIELD_INST = "_inst"  # CrossLevelStorageHolder static
FIELD_MAIN_GRID = "mainGridValues"
FIELD_SAVED_GRID = "savedGridValues"
FIELD_X_MAX = "xMax"
FIELD_Y_MAX = "yMax"
FIELD_COLOURS = "colours"
FIELD_COLOUR_COUNTS = "colourCounts"
FIELD_SELECTED_COLOUR_ID = "selectedColourID"
FIELD_TRANSFORM = "transform"
FIELD_CAM = "cam"
FIELD_POSITION = "position"
FIELD_ORTHOGRAPHIC_SIZE = "orthographicSize"
FIELD_ASPECT = "aspect"
FIELD_CELL_SIZE = "m_CellSize"
FIELD_GAME_OVER = "gameOver"
FIELD_BOOK_INDEX = "bookIndex"
FIELD_LEVEL_INDEX = "levelIndex"

# Input settings
COLOR_CYCLE_KEY_PREV = "q"
COLOR_CYCLE_KEY_NEXT = "e"
PAN_KEYS = {
    "left": "left",
    "right": "right",
    "up": "up",
    "down": "down",
}

# Bot settings
DEBUG = True
CLICK_DELAY = 0.005
BATCH_SIZE = 100

# Logging
LOG_DIR = Path(__file__).parent / "logs"
