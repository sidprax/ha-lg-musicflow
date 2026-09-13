"""Constants for the LG MusicFlow (Legacy) integration."""

DOMAIN = "lg_musicflow"
DEFAULT_PORT = 9741

# Functions (Sources)
FUNCTION_MAP = {
    0: "Wi-Fi",
    1: "Bluetooth",
    2: "Portable",
    3: "Aux",
    4: "Optical",
    5: "CP",
    6: "HDMI",
    7: "ARC",
    8: "Spotify",
    9: "Optical 2",
    10: "HDMI 2",
    11: "HDMI 3",
    12: "LG TV",
    14: "Google Cast",
    15: "Optical / HDMI ARC",
}

FUNCTION_REVERSE_MAP = {v: k for k, v in FUNCTION_MAP.items()}

# Equalizers (Sound Modes)
EQUALIZER_MAP = {
    0: "Standard",
    1: "Bass",
    2: "Flat",
    3: "Boost",
    4: "Treble & Bass",
    5: "User",
    6: "Music",
    7: "Cinema",
    8: "Night",
    9: "News",
    10: "Voice",
    11: "iSound",
    12: "Adaptive Sound Control (ASC)",
    13: "Movie",
    14: "Bass Blast",
    15: "Dolby Atmos",
    16: "DTS Virtual:X",
    17: "Bass Boost+",
}

EQUALIZER_REVERSE_MAP = {v: k for k, v in EQUALIZER_MAP.items()}

# Play Control Commands
PLAY_CTRL_PLAY = 0
PLAY_CTRL_PAUSE = 1
PLAY_CTRL_STOP = 2
PLAY_CTRL_PREV = 3
PLAY_CTRL_NEXT = 5

# Playback State codes
STATE_PLAYING = 0
STATE_PAUSED = 1
STATE_STOPPED = 2
STATE_IDLE = 3
STATE_BUFFERING = 4
