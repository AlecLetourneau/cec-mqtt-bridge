cec-mqtt-bridge
===============
My take on michaelarnauts' cec-mqtt-bridge.

Adds:
* active source tracking
* publishes to mqtt topic based on result of the OSD Name cec command
* publishes the logical and physical addresses.

Removes the IR component

I'm currently using this container on a Raspberry Pi 3B+ connected to a receiver to monitor and control a Tv, Receiver, PS4, Nintendo Switch, and Chromecast. 
HomeAssistant is used to synchronize the Tv and Receiver's power status with the active source.


A HDMI-CEC to MQTT bridge written in Python 3 for connecting your AV-devices to your Home Automation system. You can control and monitor power status, volume, and the active source.

# Features
* CEC
  * Power control
  * Volume control
  * Active Source tracking
  * Relay CEC messages from HDMI to broker (RX)
  * Relay CEC messages from broker to HDMI (TX)

# Dependencies

## MQTT
* MQTT broker (like [Mosquitto](https://mosquitto.org/))

## HDMI-CEC 
* libcec4 with python bindings (https://github.com/Pulse-Eight/libcec)
  * You can compile the bindings yourself, or use precompiled packages from my [libcec directory](libcec/).
* HDMI-CEC interface device (like a [Pulse-Eight](https://www.pulse-eight.com/) device, or a Raspberry Pi)


# MQTT Topics

The bridge subscribes to the following topics:

| topic                   | body                                    | remark                                           |
|:------------------------|-----------------------------------------|--------------------------------------------------|
| `prefix`/cec/`id`/cmd   | `on` / `off`                            | Turn on/off device with id `id`.                 |
| `prefix`/cec/cmd        | `mute` / `unmute` / `voldown` / `volup` | Sends the specified command to the audio system. |
| `prefix`/cec/volume/set | `integer (0-100)`                       | Sets the volume level of the audio system to a specific level. |
| `prefix`/cec/tx         | `commands`                              | Send the specified `commands` to the CEC bus. You can specify multiple commands by separating them with a space. Example: `cec/tx 15:44:41,15:45`. |
| `prefix`/ir/`remote`/tx | `key`                                   | Send the specified `key` of `remote` to the IR transmitter. |

The bridge publishes to the following topics:

| topic                   | body                                    | remark                                           |
|:------------------------|-----------------------------------------|--------------------------------------------------|
| `prefix`/bridge/status  | `online` / `offline`                    | Report availability status of the bridge.        |
| `prefix`/cec/`id`       | `on` / `off`                            | Report power status of device with id `id`.      |
| `prefix`/cec/volume     | `integer (0-100)`                       | Report volume level of the audio system.         |
| `prefix`/cec/mute       | `on` / `off`                            | Report mute status of the audio system.          |
| `prefix`/cec/rx         | `command`                               | Notify that `command` was received.              |
`id` is the address (0-15) of the device on the CEC-bus.

# Examples
* `mosquitto_pub -t media/cec/volup -m ''`
* `mosquitto_pub -t media/cec/tx -m '15:44:42,15:45'`

# Interesting links
* https://github.com/nvella/mqtt-cec
* http://www.cec-o-matic.com/
* http://wiki.kwikwai.com/index.php?title=The_HDMI-CEC_bus
