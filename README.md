# LG MusicFlow (Legacy) for Home Assistant

[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/sidprax/ha-lg-musicflow)](https://github.com/sidprax/ha-lg-musicflow/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Validate with hassfest](https://github.com/sidprax/ha-lg-musicflow/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/sidprax/ha-lg-musicflow/actions/workflows/hassfest.yaml)
[![HACS Action](https://github.com/sidprax/ha-lg-musicflow/actions/workflows/hacs.yaml/badge.svg)](https://github.com/sidprax/ha-lg-musicflow/actions/workflows/hacs.yaml)

A custom Home Assistant integration providing native local control and direct audio streaming for legacy **LG Music Flow** soundbars and speakers (including SJ9, SJ8, SJ7, SH7, LAS855M, H7, H5, H4, H3).

Unlike standard DLNA (which often fails with `UPnPError 705: Access denied` on LG speakers) or Google Cast (which is broken on legacy Cast 1.36 firmware with deprecated certificates), this integration speaks the native LG Music Flow protocol over TCP port `9741`.

---

## Features

- **Direct Audio Streaming (`play_media`)**: Streams audio URLs, internet radio, and TTS announcements directly to the speaker using LG's native playback protocol.
- **Full Playback Controls**: Play, Pause, Stop, Mute, Volume slider.
- **Dynamic Source Selection**: Auto-discovers and exposes all supported physical and wireless inputs (`Wi-Fi`, `Optical / HDMI ARC`, `Bluetooth`, `LG TV`, `HDMI`, `Portable`, etc.) both as media player sources and as a discrete `select` entity on the device page.
- **Equalizer & Sound Modes**: Auto-discovers supported sound presets (`Dolby Atmos`, `Bass Blast`, `Cinema`, `Music`, `Adaptive Sound Control`, `Standard`, etc.) exposed as a discrete `select` entity.
- **Subwoofer Control**: Real-time subwoofer dB slider (`-15 dB` to `+6 dB` with 1 dB steps).
- **Night Mode & Auto Power**: Switch entities for Night Mode (dynamic range compression) and Auto Power (which prevents the soundbar from automatically switching to Optical when a TV is in standby).
- **SSDP Auto-Discovery**: Automatically detected on your local network.
- **Music Assistant Compatible**: Seamlessly compatible with Music Assistant via the Home Assistant Player provider.
- **Guided Wi-Fi Setup Wizard**: Built-in config flow recovery wizard to configure and provision factory-reset speakers back onto your 2.4GHz Wi-Fi network.
- **Standalone Setup Script**: Includes a standalone tool (`tools/setup_soundbar_wifi.js`) that allows configuring a reset speaker from any computer without an app.
- **Configurable Polling & Standby Handling**: Native standby detection with automatic polling pause, allowing soundbars to sleep undisturbed with your TV or remote without being held awake by network traffic.

---

## Supported Devices

Any LG speaker or soundbar using the LG Music Flow / Smart Audio platform, including:
- **Soundbars**: SJ9 (Dolby Atmos), SJ8, SJ7, SH7, LAS855M, LAS750M, LAS950M
- **Wireless Speakers**: Music Flow H7 (NP8740), H5 (NP8540), H4 (NP8350), H3 (NP8340)
- **Bridges**: MR140

---

## Installation

### Method 1: HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sidprax&repository=ha-lg-musicflow&category=integration)

1. Click the button above to open the repository in HACS, or in Home Assistant go to **HACS > Integrations**.
2. Search for **LG MusicFlow (Legacy)**.
3. Click **Download**, then restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release from the [Releases](https://github.com/sidprax/ha-lg-musicflow/releases) page.
2. Copy the `custom_components/lg_musicflow` folder into your Home Assistant `<config>/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=lg_musicflow)

1. Click the button above, or go to **Settings > Devices & Services > Add Integration**.
2. Search for **LG MusicFlow (Legacy)** (or click **Configure** if automatically discovered via SSDP).
3. Enter your speaker's IP address (port `9741`).

### Integration Options

Click **Configure** on the integration card under **Settings > Devices & Services > LG MusicFlow** to adjust options:
- **Active status polling interval**: Seconds between polls while actively playing or in use (3–60s, default: `6`). During active media streaming, a fast 3-second interval is automatically used for smooth position and volume tracking.
- **Pause polling during standby**: Enabled by default (`true`). Pauses network polling and closes the TCP socket when the speaker is idle or in standby. **Required for LG soundbars to enter and stay in sleep mode.**

### Speaker Reset & Wi-Fi Provisioning

If your speaker was factory reset or lost its Wi-Fi connection, select **Speaker not found / Reset & Wi-Fi Setup Wizard** during setup:
- **Option 1 (Ethernet - Recommended)**: Plug the speaker into your router/switch with an Ethernet cable temporarily. Home Assistant will push your 2.4GHz Wi-Fi credentials directly, after which you can unplug the cable.
- **Option 2 (Wi-Fi Hotspot via PC)**: Put the speaker into setup mode (press & hold the Wi-Fi/Add button for 5–10s until the LED flashes). Connect your computer to `MusicFlow_Setup_xxxx` and run:
  ```bash
  node tools/setup_soundbar_wifi.js
  ```

---

## Power, Standby & Polling Behavior

### Hardware Reality
LG soundbar hardware treats any incoming TCP connection on port `9741` as an active controller session. If Home Assistant polls the soundbar while it is in standby, the incoming connection immediately wakes up the display and hardware (for example, showing `OPTICAL` or `ARC` right after turning off).

**Any active polling will prevent the soundbar from staying in standby.**

### Standby & Polling Pause
To ensure soundbars can turn off and stay asleep, the integration automatically pauses background polling and closes the TCP connection when idle:
1. **Physical TV Inputs (ARC, Optical, HDMI)**: When active on physical inputs, the soundbar remains `on` with full volume and sound mode controls available in Home Assistant. Turning off the TV allows the soundbar to enter low-power sleep via HDMI-CEC or auto-power without background network traffic waking it.
2. **Wi-Fi Streaming**: When active playback finishes or `turn_off` is called, polling pauses so the soundbar's hardware auto-power timer can expire undisturbed.
3. **Turn Off in HA**: Calling `turn_off` stops playback, sends the native standby command, and puts the entity into standby without hijacking or muting your physical TV input.

### Seamless Waking
Any action triggered from Home Assistant instantly reconnects, wakes the soundbar, and resumes active polling:
- Playing music, radio, or TTS announcements (`play_media`)
- Adjusting volume or mute
- Selecting an input source or sound mode
- Calling `turn_on`

### Always-On Speakers (H3, H4, H5, H7)
Standalone Music Flow wireless speakers do not have an AC standby mode and are always-on network devices. If you prefer continuous polling at all times on these models, you can uncheck **Pause polling during standby** in the integration options.

### Syncing with TV Power (Optional Automation)
When you turn on your TV, HDMI CEC automatically powers on the soundbar and routes TV audio locally. If you want Home Assistant to instantly reflect the TV-on state without waiting for a command in HA, you can add this optional automation:

```yaml
alias: Sync LG Soundbar on TV Power
description: "Refresh soundbar state when the TV is powered on"
trigger:
  - platform: state
    entity_id: media_player.your_tv
    to: "on"
action:
  - action: homeassistant.update_entity
    target:
      entity_id: media_player.lg_soundbar
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
