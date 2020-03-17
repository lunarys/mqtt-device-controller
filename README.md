# MQTT device controller

## What does this do?
This python script executed in a docker container manages the start and shutdown of devices I do not always need.

The current state of the controlled device is tracked via MQTT and MQTT topics are subscribed for messages from other devices and users. The controller acts differently based on different conditions:
- **The device is already running:** Add the device or user to the active instances and wait until they are done.
- **The device is disabled:** Do not start the device and notify the user about this.
- **The device is not running:** 
   - **Start of the device is desired:** Start the device and tell the user to wait for a notification when the device is online.
   - **Only use the device if online:** Notify the user that the device is not running.
- **All devices are done:** Wait for a configured time in case the device is required again, then shut it down.

Everything can be configured via the docker-compose `.env` file, which is provided as a template.

## Using this controller
The easiest way of interacting with the controller is by using the existing clients:
- The [vbackup](https://github.com/lunarys/vbackup) backup can interact with this controller.
- There also is a [standalone client](https://github.com/lunarys/mqtt-device-controller-client) to interact with the controller from the command line.
