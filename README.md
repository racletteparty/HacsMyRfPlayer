# MyRfPlayer HomeAssistant Integration

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![Community Forum][forum-shield]][forum]

_Integration to integrate with [GCE RfPlayer][myrfplayer]._

**This integration will set up the following platforms.**

Platforms:

- `binary_sensor`
- `sensor`
- `light`
- `climate`

Services:

- `send command`
- `simulate event`

## Installation

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
1. If you do not have a `custom_components` directory (folder) there, you need to create it.
1. In the `custom_components` directory (folder) create a new folder called `myrfplayer`.
1. Download _all_ the files from the `custom_components/myrfplayer/` directory (folder) in this repository.
1. Place the files you downloaded in the new directory (folder) you created.
1. Restart Home Assistant
1. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "MyRfPlayer"

## Configuration

Configuration is done in the UI.

It is possible to emulate a RfPlayer to try the integration without real hardware. You can use the simulate event service to try out different JSON events as if they were received on the USB serial line. Read the RfPlayer API documentation for details about the JSON payload format.

Some RF devices like Oregon sensors will renew their addresses after changing the battery. Using the redirect device option, it is possible to redirect events from the new address to device and entities created with the initial address.

RF devices can be declared manually from the integration configuration form.

When automatic device creation is enabled, the RF device will be created with the first matching RF device profiles. However, some generic RF devices can match several profiles (e.g. Blyss devices). If you want to assign a more specific profile, you need to disable automatic device creation, delete the device that was automatically created and re-create it manually with the selected profile.

## Device profiles

| Profile                                     | Event verified | Command verified | Comment |
| ------------------------------------------- | -------------- | ---------------- | ------- |
| X10 DOMIA Switch                            | ❌             | ❌               |
| Jamming Detector                            | ❌             | ❌               |
| X10 CHACON KD101 BLYSS FS20 Switch          | ❌             | ❌               |
| X10 CHACON KD101 BLYSS FS20 Lighting        | ❌             | ❌               |
| X10 CHACON KD101 BLYSS FS20 On/Off          | ❌             | ❌               |
| X10 CHACON KD101 BLYSS FS20 Motion detector | ❌             | ❌               |
| X10 CHACON KD101 BLYSS FS20 Smoke detector  | ❌             | ❌               |
| Visionic Sensor/Detector                    | ❌             | ❌               |
| Visionic Remote                             | ❌             | ❌               |
| RTS Shutter                                 | ❌             | ❌               |
| RTS Portal                                  | ❌             | ❌               |
| Oregon Temperature Sensor                   | ❌             | ❌               |
| Oregon Temperature/Humidity Sensor          | ❌             | ❌               |
| Oregon Pressure Sensor                      | ❌             | ❌               |
| Oregon Wind Sensor                          | ❌             | ❌               |
| Oregon UV Sensor                            | ❌             | ❌               |
| OWL Power Meter                             | ❌             | ❌               |
| Oregon Rain Sensor                          | ❌             | ❌               |
| X2D Thermostat Elec                         | ❌             | ❌               |
| X2D Thermostat Gas                          | ❌             | ❌               |
| X2D Detector/Sensor                         | ❌             | ❌               |
| X2D Shutter                                 | ❌             | ❌               |

## Future improvements

- Add user-defined device profiles
- Add actions to RF devices like association
- Move device configuration (area,...) to new device instead of redirecting events
- Add more platforms siren, events...

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

---

[myrfplayer]: https://github.com/racletteparty/HacsMyRfPlayer
[commits-shield]: https://img.shields.io/github/commit-activity/y/racletteparty/HacsMyRfPlayer
[commits]: https://github.com/racletteparty/HacsMyRfPlayer/commits/main
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg
[forum]: https://forum.hacf.fr/
[license-shield]: https://img.shields.io/github/license/racletteparty/HacsMyRfPlayer
[releases-shield]: https://img.shields.io/github/release/racletteparty/HacsMyRfPlayer
[releases]: https://github.com/racletteparty/HacsMyRfPlayer/releases
