# LG MusicFlow (Legacy) for Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/sidprax/ha-lg-musicflow)](https://github.com/sidprax/ha-lg-musicflow/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Validate with hassfest](https://github.com/sidprax/ha-lg-musicflow/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/sidprax/ha-lg-musicflow/actions/workflows/hassfest.yaml)
[![HACS Action](https://github.com/sidprax/ha-lg-musicflow/actions/workflows/hacs.yaml/badge.svg)](https://github.com/sidprax/ha-lg-musicflow/actions/workflows/hacs.yaml)

A custom Home Assistant integration providing native local control and direct audio streaming for legacy **LG Music Flow** soundbars and speakers (including SJ9, SJ8, SJ7, SH7, LAS855M, H7, H5, H4, H3).

Unlike standard DLNA (which often fails with `UPnPError 705: Access denied` on LG speakers) or Google Cast (which is broken on legacy Cast 1.36 firmware with deprecated certificates), this integration speaks the native LG Music Flow protocol over TCP port `9741`.

---

## Features

- 🎵 **Direct Audio Streaming (`play_media`)**: Streams audio URLs, internet radio, and TTS announcements directly to the speaker using LG's native playback protocol.
- 🎛️ **Full Playback Controls**: Play, Pause, Stop, Mute, Volume slider.
- 🔌 **Dynamic Source Selection**: Auto-discovers and exposes all supported physical and wireless inputs (`Wi-Fi`, `Optical / HDMI ARC`, `Bluetooth`, `LG TV`, `HDMI`, `Portable`, etc.) both as media player sources and as a discrete `select` entity on the device page.
- 🎼 **Equalizer & Sound Modes**: Auto-discovers supported sound presets (`Dolby Atmos`, `Bass Blast`, `Cinema`, `Music`, `Adaptive Sound Control`, `Standard`, etc.) exposed as a discrete `select` entity.
- 🔊 **Subwoofer Control**: Real-time subwoofer dB slider (`-15 dB` to `+6 dB` with 1 dB steps).
- 🌙 **Night Mode & Auto Power**: Switch entities for Night Mode (dynamic range compression) and Auto Power (which prevents the soundbar from automatically switching to Optical when a TV is in standby).
- 📡 **SSDP Auto-Discovery**: Automatically detected on your local network.
- 🎶 **Music Assistant Compatible**: Seamlessly compatible with Music Assistant via the Home Assistant Player provider.
- 🛠️ **Guided Wi-Fi Setup Wizard**: Built-in config flow recovery wizard to configure and provision factory-reset speakers back onto your 2.4GHz Wi-Fi network.
- 💻 **Standalone Setup Script**: Includes a standalone tool (`tools/setup_soundbar_wifi.js`) that allows configuring a reset speaker from any computer without an app.

---

## Supported Devices

Any LG speaker or soundbar using the LG Music Flow / Smart Audio platform, including:
- **Soundbars**: SJ9 (Dolby Atmos), SJ8, SJ7, SH7, LAS855M, LAS750M, LAS950M
- **Wireless Speakers**: Music Flow H7 (NP8740), H5 (NP8540), H4 (NP8350), H3 (NP8340)
- **Bridges**: MR140

---

## Installation

### Method 1: HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in Home Assistant.
2. In Home Assistant, open **HACS > Integrations**.
3. Click the three dots in the top right corner and select **Custom repositories**.
4. Add `https://github.com/sidprax/ha-lg-musicflow` with Category **Integration**.
5. Click **Download**, then restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release from the [Releases](https://github.com/sidprax/ha-lg-musicflow/releases) page.
2. Copy the `custom_components/lg_musicflow` folder into your Home Assistant `<config>/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, go to **Settings > Devices & Services > Add Integration**.
2. Search for **LG MusicFlow (Legacy)** (or click **Configure** if automatically discovered via SSDP).
3. Enter your speaker's IP address (port `9741`).

### Speaker Reset & Wi-Fi Provisioning

If your speaker was factory reset or lost its Wi-Fi connection, select **Speaker not found / Reset & Wi-Fi Setup Wizard** during setup:
- **Option 1 (Ethernet - Recommended)**: Plug the speaker into your router/switch with an Ethernet cable temporarily. Home Assistant will push your 2.4GHz Wi-Fi credentials directly, after which you can unplug the cable.
- **Option 2 (Wi-Fi Hotspot via PC)**: Put the speaker into setup mode (press & hold the Wi-Fi/Add button for 5–10s until the LED flashes). Connect your computer to `MusicFlow_Setup_xxxx` and run:
  ```bash
  node tools/setup_soundbar_wifi.js
  ```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
