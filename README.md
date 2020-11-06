# MQTT device controller

## What does this do?
This python script executed in a docker container manages the start and shutdown of devices I do not always need. 
The controller is built to work autonomously.

The current state of the controlled device is tracked via MQTT and MQTT topics are subscribed for messages from other devices and users. The controller acts differently based on different conditions:
- **The device is already running:** Add the device or user to the active instances and wait until they are done.
- **The device is disabled:** Do not start the device and notify the user about this.
- **The device is not running:** 
   - **Start of the device is desired:** Start the device and tell the user to wait for a notification when the device is online.
   - **Only use the device if online:** Notify the user that the device is not running.
- **All devices are done:** Wait for a configured time in case the device is required again, then shut it down.

The current state of active devices and users is also observed in order to handle a shutdown or crash of those accordingly.

## Related projects
- [MQTT device status](https://github.com/lunarys/mqtt-device-status): Send the online state of devices via MQTT.
- [MQTT wake-on-lan](https://github.com/lunarys/mqtt-wake-on-lan): Start remote devices using wake-on-lan.
- [MQTT shutdown trigger](https://github.com/lunarys/mqtt-shutdown-trigger): Shut down devices remotely.
- The [vbackup](https://github.com/lunarys/vbackup) backup can interact with this controller.
- A [standalone client](https://github.com/lunarys/mqtt-device-controller-client) can be used to interact with the controller from the command line.

## Configuration
Everything can be configured via the docker-compose `.env` file, which is provided as a template.

| Option   | Default     | Description     |
|---------|-------------|-----------------|
| DEVICE_NAME | | The name of the controlled device. Determines the MQTT topic as described below. |
| MQTT_BROKER | localhost | The hostname of the MQTT broker. |
| MQTT_USER | | The username for the MQTT broker. |
| MQTT_PASSWORD | | The password for the MQTT broker. |
| MQTT_PORT | 1883 | The port for the MQTT broker. |
| MQTT_QOS | 1 | The quality of service for the MQTT broker. |
| WAIT_AFTER_START | 600 | The amount of seconds to wait for users after the device started. |
| WAIT_BEFORE_STOP | 300 | The amount of seconds to wait before shutting down the controlled device after all users are done. |
| MINIMUM_RUN_TIME | 600 | Keep the device running for at least this amount of seconds. Enables shorter times for WAIT_BEFORE_STOP. |

More options are theoretically supported to change subscription and publishing topics, but not listed here.

Default topics:

| Topic | Description |
|-------|-------------|
| `device/$DEVICE_NAME/status` | The status topic for the controlled device. |
| `device/$DEVICE_NAME/status/retained` | The topic for receiving the state of the remote device retained. `ONLINE`, `OFFLINE` or `CRASHED`. |
| `device/$DEVICE_NAME/status/desired` | The topic for interacting with the remote device. Send `ON` or `OFF`. |
| `device/$DEVICE_NAME/controller/status` | The status of the controller. `ENABLED` or `DISABLED`. |
| `device/$DEVICE_NAME/controller/status/desired` | Set the status of the controller. `ENABLE` or `DISABLE`. |
| `device/$DEVICE_NAME/controller/status/active` | A list of users using the device currently. |
| `device/$DEVICE_NAME/contoller/status/waiting` | A list of users waiting for the start of the controlled device. |
| `device/$DEVICE_NAME/controller/to/$USER` | Outgoing messages to $USER |
| `device/$DEVICE_NAME/controller/from/$USER` | Incoming messages from $USER |
| `device/$USER/status` | The observed topic for $USER. Listens for `OFFLINE` or `CRASHED` |
