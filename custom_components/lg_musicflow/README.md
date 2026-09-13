# LG MusicFlow (Legacy) for Home Assistant

Custom component for Home Assistant providing native local control and direct audio streaming for legacy LG Music Flow soundbars and speakers (including SJ9, SJ8, SJ7, SH7, LAS855M, H7, H5, H4, H3).

Unlike standard DLNA (which often fails with `UPnPError 705: Access denied` on LG soundbars) or Google Cast (which is broken on legacy Cast 1.36 firmware with deprecated SHA-1 certificates), this integration speaks the native LG Music Flow JSON protocol over TCP port `9741`.

## Features

- **Audio Streaming (`play_media`)**: Streams audio URLs, radio stations, and TTS announcements directly to the speaker using LG's native `LOCAL_PLAY_URL` protocol.
- **Full Media Player Controls**: Play, Pause, Stop, Mute, Volume slider.
- **Dynamic Source Selection**: Auto-discovers and populates supported inputs for your model (Wi-Fi, Optical, HDMI, ARC, Bluetooth, Portable).
- **Dynamic Sound Modes / EQ**: Auto-discovers supported sound presets (Dolby Atmos, Bass Blast, Cinema, ASC, Standard, etc.).
- **Subwoofer Control**: Exposes Subwoofer Level (`-15 dB` to `+6 dB`) as a Number slider entity.
- **Night Mode & Auto Power**: Switch entities to toggle Night Mode and Auto Power (which prevents unwanted switching to Optical when TV is in standby).
- **SSDP Auto-Discovery**: Automatically detected by Home Assistant on your local network.
- **Music Assistant Compatible**: Works out-of-the-box with Music Assistant's Home Assistant Player provider.

### Initial Wi-Fi Setup (Provisioning)
If your speaker was factory reset or isn't on your Wi-Fi network yet:
1. Turn on the speaker and press the **Wi-Fi Setup / Add** button. The speaker creates a temporary Wi-Fi hotspot (e.g. `MusicFlow_Setup_xxxx`), or plug it into an Ethernet cable connected to your router.
2. If connecting via the speaker's hotspot, its IP address is `192.168.5.100`.
3. In Home Assistant, go to **Add Integration > LG MusicFlow (Legacy) > Set up a new/reset speaker on Wi-Fi**.
4. Enter your 2.4GHz Wi-Fi SSID and password, and optionally a speaker name. The speaker will connect to your Wi-Fi and be discovered automatically!

You can also run the included standalone setup script from your computer without Home Assistant:
```bash
node setup_soundbar_wifi.js --host 192.168.5.100 --ssid "YourSSID" --password "YourPassword" --name "Living Room SJ9"
```

## Installation

### Manual
1. Copy the `custom_components/lg_musicflow` directory to your Home Assistant `<config>/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings > Devices & Services > Add Integration** and search for **LG MusicFlow (Legacy)** (or click Configure if discovered via SSDP).
