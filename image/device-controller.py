import os
import paho.mqtt.client as mqtt
import sys
import time
import signal
from threading import Timer


# TODO: There might be an issue if a user starts the device and the device never comes online.
#       If the next time the device is started manually, the controller will think it was his work,
#       stopping the device as no users are registered.
#    Possible solution: Timeout for start

def topic_from(*args):
    is_first = True
    result = ""
    for arg in args:
        if arg is not None and arg != "":
            if is_first:
                result += arg
                is_first = False
            else:
                result += "/" + arg
    return result


def topic_device_user(constants, device, user):
    return topic_from(constants[0], device, constants[1], constants[2], user, constants[3])


def topic_device_user_len(constants):
    count = 2
    for arg in constants:
        if arg is not None and arg != "":
            count += 1
    return count


def topic_device_user_match(constants, device, topic):
    topic_split = topic.split("/")
    if len(topic_split) != topic_device_user_len(constants):
        return False
    else:
        constant_count = 0
        topic_count = 0
        for arg in constants:
            if arg is not None and arg != "":
                if arg != topic_split[topic_count]:
                    return False
                topic_count += 1
            if constant_count == 0 or constant_count == 2:
                topic_count += 1  # This would be the device name
            constant_count += 1
        result = device_from(constants, topic) == device
        return result


def device_from(constants, topic):
    topic_split = topic.split("/")
    if len(topic_split) != topic_device_user_len(constants):
        return None
    if constants[0] is not None and constants[0] != "":
        return topic_split[1]
    else:
        return topic_split[0]


def user_from(constants, topic):
    topic_split = topic.split("/")
    if len(topic_split) != topic_device_user_len(constants):
        return None
    constant_count = 0
    for i in range(0, 3):
        if constants[i] is not None and constants[i] != "":
            constant_count += 1
    return topic_split[1 + constant_count]


def topic_status(constants, device):
    return topic_from(constants[0], device, constants[1], constants[2])


def topic_status_len(constants):
    count = 1
    for arg in constants:
        if arg is not None and arg != "":
            count += 1
    return count


def topic_status_match(constants, topic):
    topic_split = topic.split("/")
    if len(topic_split) != topic_status_len(constants):
        return False
    else:
        constant_count = 0
        topic_count = 0
        for arg in constants:
            if arg is not None and arg != "":
                if arg != topic_split[topic_count]:
                    return False
                topic_count += 1
            if constant_count == 0:
                topic_count += 1
            constant_count += 1
    return True


def from_status_topic(constants, topic):
    topic_split = topic.split("/")
    if len(topic_split) != topic_status_len(constants):
        return None
    else:
        if constants[0] is not None and constants[0] != "":
            return topic_split[1]
        else:
            return topic_split[0]


#####################################################
def stop_device():
    global i_started
    global timer
    global state
    print("[T] Timeout is over, there were no new users, shutting down.")
    i_started = False
    client.publish(topic_status(topic_device_status_pub_constants, device), "OFF", qos, False)

    # In case device does not shut down immediately
    timer = None


#####################################################
def send_device_list():
    topic_status_check = topic_status(topic_status_pub_constants, device)
    print("    Sending list of currently active devices:", devices)
    print("    Sending list of currently waiting devices:", devices_waiting)
    if len(devices) == 0:
        send_string = "[]"
    else:
        send_string = "[" + ",".join(devices) + "]"
    if len(devices_waiting) == 0:
        send_string_waiting = "[]"
    else:
        send_string_waiting = "[" + ",".join(devices_waiting) + "]"
    time.sleep(1)
    client.publish(topic_status_check + "/active", send_string, qos, False)
    client.publish(topic_status_check + "/waiting", send_string_waiting, qos, False)
    client.publish(topic_status_check + "/active/count", str(len(devices)), qos, False)
    client.publish(topic_status_check + "/waiting/count", str(len(devices_waiting)), qos, False)


#####################################################
def on_message(client, usr, msg):
    global state
    global device
    global devices
    global devices_waiting
    global i_started
    global wait_after_start
    global wait_before_stop
    global timer
    global disabled

    message = msg.payload.decode("utf-8").upper()
    topic = msg.topic
    print("[R] Received", message, "on", topic)

    topic_split = topic.split("/")

    device_status_sub = topic_status(topic_device_status_sub_constants, device)
    controller_status_sub = topic_status(topic_status_sub_constants, device)
    controller_status_pub = topic_status(topic_status_pub_constants, device)

    just_started = False

    #################################################
    # Handle device state topic separately
    #################################################
    if topic == device_status_sub:
        if message == "ONLINE":
            if state == "ON":
                print("    Device was already online, doing nothing...")
                return 0
            state = "ON"
            print("    Device is now online, notifying waiting devices...")
            send_msg = "CHECK"
            just_started = True
        elif message == "OFFLINE" or message == "CRASHED":
            if state == "OFF":
                print("    Device was already offline, doing nothing...")
                return 0
            state = "OFF"
            print("    Device not online anymore, notifying active devices...")
            send_msg = "ABORT"

            # In this case also send to active (not waiting) devices
            print("    Notifying:", devices)
            for user in devices:
                client.publish(topic_device_user(topic_pub_constants, device, user), send_msg, qos, False)
        else:
            print("    Received unknown device state:", message)
            return 1

        print("    Notifying:", devices_waiting)
        for user in devices_waiting:
            client.publish(topic_device_user(topic_pub_constants, device, user), send_msg, qos, False)

        if message == "OFFLINE" or message == "CRASHED":
            print("    Clearing waiting devices list")
            devices = []
            devices_waiting = []
            send_device_list()
            if timer is not None:
                print("    Stopping active timer")
                timer.cancel()
                timer = None

        # Disable return here so that time will be started if device comes online but users already left
        # return 0
    ################################################
    # Handle device state check (for active devices)
    ################################################
    elif topic_status_match(topic_user_constants, topic):
        curr_user = from_status_topic(topic_user_constants, topic)
        if message == "OFFLINE" or message == "CRASHED":
            if curr_user in devices:
                devices.remove(curr_user)
                print("    Device", curr_user,
                      "went offline/crashed while being active, removing from active devices...")
                send_device_list()
            elif curr_user in devices_waiting:
                devices_waiting.remove(curr_user)
                print("    Device", curr_user, "went offline/crashed while waiting for the start...")
                send_device_list()
            else:
                print("    Device", curr_user, "was not saving or waiting.")
                return 0
        else:
            return 0
    ################################################
    # Handle active devices check
    ################################################
    elif topic == controller_status_sub:
        # Update controller state
        if message == "DISABLE" or message == "DISABLED":
            print("    Setting controller state to disabled")
            disabled = True
        elif message == "ENABLE" or message == "ENABLED":
            print("    Setting controller state to enabled")
            disabled = False

        # Send controller state
        time.sleep(1)
        if disabled:
            print("    Sending current controller state: DISABLED")
            client.publish(controller_status_pub, "DISABLED", qos, True)
        else:
            print("    Sending current controller state: ENABLED")
            client.publish(controller_status_pub, "ENABLED", qos, True)

        # Send active / waiting devices
        if message == "CHECK":
            send_device_list()

        return 0
    ################################################
    # Handle saving devices topics
    ################################################
    elif topic_device_user_match(topic_sub_constants, device, topic):
        curr_user = user_from(topic_sub_constants, topic)
        reply_on = topic_device_user(topic_pub_constants, device, curr_user)

        ################################################
        # Is device disabled?
        ################################################
        if disabled:
            if message == "CHECK" or message == "START_BOOT" or message == "START_RUN":
                print("    Device is disabled, sending this as reply.")
                time.sleep(1)
                client.publish(reply_on, "DISABLED", qos, False)
                return 0

        ################################################
        # Just checking device state?
        ################################################
        if message == "CHECK":
            print("    Publishing current device state for", curr_user, ":", state)
            time.sleep(1)
            client.publish(reply_on, state, qos, False)
            return 0

        ################################################
        # Register users that are running a backup
        ################################################
        if state == "ON" and (message == "START_RUN" or message == "START_BOOT"):
            if curr_user not in devices:
                devices.append(curr_user)
                if curr_user in devices_waiting:
                    devices_waiting.remove(curr_user)
                if timer is not None:
                    print("    User connected, stopping active timer to stop device.")
                    timer.cancel()
                    timer = None
                send_device_list()

        ################################################
        # Run backup without starting?
        ################################################
        if message == "START_RUN":
            if state == "ON":
                print("    Notifying", curr_user, "that device is running...")
                time.sleep(1)
                client.publish(reply_on, "READY", qos, False)
            else:
                print("    Notifying", curr_user, "that device is offline...")
                time.sleep(1)
                client.publish(reply_on, "OFF", qos, False)

        ################################################
        # Backup starting?
        ################################################
        if message == "START_BOOT":
            if state == "ON":
                # Device is ready
                print("    Notifying", curr_user, "that device is already running...")
                time.sleep(1)
                client.publish(reply_on, "READY", qos, False)
            else:
                ################################################
                # Register users that are waiting for the device
                ################################################
                if curr_user not in devices_waiting:
                    devices_waiting.append(curr_user)
                    time.sleep(1)
                    client.publish(reply_on, "WAIT", qos, False)
                    send_device_list()

                # Start device
                print("    Starting device for", curr_user, "...")
                time.sleep(1)
                client.publish(topic_status(topic_device_status_pub_constants, device), "ON", qos, False)
                i_started = True
            return 0

        ################################################
        # Confirmation or query from user 
        ################################################
        if message == "STILL_WAITING":
            if curr_user in devices_waiting:
                if state == "ON":
                    # Device is now ready for the user
                    devices.append(curr_user)
                    devices_waiting.remove(curr_user)
                    if timer is not None:
                        print("    User connected, stopping active timer to stop device")
                        timer.cancel()
                        timer = None
                    print("    Notifying", curr_user, "that device is now ready for use...")
                    time.sleep(1)
                    client.publish(reply_on, "READY", qos, False)
                    send_device_list()
                else:
                    # Device is still not ready
                    print("    Notifying", curr_user, "that device is still not ready...")
                    time.sleep(1)
                    client.publish(reply_on, "WAIT", qos, False)
            else:
                print("    ", curr_user, "is not registered as waiting, doing nothing")

        ################################################
        # Backup stopping?
        ################################################
        if message == "DONE" or message == "ABORT":
            if devices.count(curr_user) > 0 or devices_waiting.count(curr_user) > 0:
                verb = ""
                if message == "DONE":
                    verb = "finished"
                else:
                    verb = "aborted"
                if state == "OFF" and i_started:
                    # Still the timer should handle this just fine...
                    print("   ", curr_user, verb, "before device was even started...")
                else:
                    print("   ", curr_user, verb + "...")

                if curr_user in devices:
                    devices.remove(curr_user)
                if curr_user in devices_waiting:
                    devices_waiting.remove(curr_user)
                send_device_list()
    ###############################################
    # Catch all
    ###############################################
    else:
        print("    Received on unknown topic, ignoring...")
        return 1

    ################################################
    # All backups done and device was started by this controller?
    ################################################
    if state == "ON" and len(devices) == 0 and i_started and timer is None:
        # Shut down device
        if just_started:
            print("    Device started, setting timeout of", wait_after_start, "seconds for users to connect...")
            timer = Timer(wait_after_start, stop_device)
        else:
            print("    All users are done, awaiting timeout of", wait_before_stop, "seconds before shutdown...")
            timer = Timer(wait_before_stop, stop_device)
        timer.start()


#####################################################
def on_subscribe(client, userdata, mid, granted_qos):
    print("Subscription")


#####################################################
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.connected_flag = True
        print("[C] Connected OK")

        device_status_topic = topic_status(topic_device_status_sub_constants, device)
        user_status_topic = topic_status(topic_user_constants, "+")
        all_device_save_topics = topic_device_user(topic_sub_constants, device, "+")
        topic_status_check = topic_status(topic_status_sub_constants, device)

        # Subscribe to all saver topics and to device status topic
        print("    Subscribing to topic", device_status_topic)
        client.subscribe(device_status_topic, qos)
        print("    Subscribed!")
        print("    Subscribing to topic", topic_status_check)
        client.subscribe(topic_status_check, qos)
        print("    Subscribed!")
        print("    Subscribing to topic", all_device_save_topics)
        client.subscribe(all_device_save_topics, qos)
        print("    Subscribed!")
        print("    Subscribing to topic", user_status_topic)
        client.subscribe(user_status_topic, qos)
        print("    Subscribed!")

        # Publish initial state
        topic_status_check_pub = topic_status(topic_status_pub_constants, device)
        if disabled:
            print("    Publishing initial state: DISABLED")
            client.publish(topic_status_check_pub, "DISABLED", qos, True)
        else:
            print("    Publishing initial state: ENABLED")
            client.publish(topic_status_check_pub, "ENABLED", qos, True)

        print("    Done!")
    else:
        print("[C] Bad connection: Returned code=", rc)


#####################################################
def on_disconnect(client, userdata, rc):
    print("[C] Disconnected: ", rc)
    client.connected_flag = False


#####################################################
def interrupt_handler(sig, frame):
    print("Received interrupt, terminating...")

    # Set state via retained message
    topic = topic_status(topic_status_pub_constants, device)
    client.publish(topic, "DISABLED", qos, True)

    client.loop_stop()
    client.disconnect()

    if timer is not None:
        timer.cancel()

    print("Done")
    exit()


#####################################################

# Store active devices
devices = []
devices_waiting = []
# Store manages devices name
device = os.environ.get('BACKUP_DEVICE')
wait_after_start = int(os.getenv('WAIT_AFTER_START', "600"))
wait_before_stop = int(os.getenv('WAIT_BEFORE_STOP', "300"))
# Store backup device state
state = "OFF"
i_started = False
timer = None
disabled_str = os.environ.get('DEVICE_DISABLED')
if disabled_str is None:
    disabled = False
else:
    disabled = disabled_str.lower() == "true"

# Topic template
topic_device_pre = os.getenv('MQTT_TOPIC_DEVICE_PRE', "device")
topic_device_post = os.getenv('MQTT_TOPIC_DEVICE_POST', "controller")
topic_user_pre = os.getenv('MQTT_TOPIC_USER_PRE')
topic_user_post = os.getenv('MQTT_TOPIC_USER_POST')

topic_device_pre_pub = os.getenv('MQTT_TOPIC_DEVICE_PRE_PUB', topic_device_pre)
topic_device_post_pub = os.getenv('MQTT_TOPIC_DEVICE_POST_PUB', topic_device_post)
topic_user_pre_pub = os.getenv('MQTT_TOPIC_USER_PRE_PUB', "to")
topic_user_post_pub = os.getenv('MQTT_TOPIC_USER_POST_PUB', topic_user_post)

topic_device_pre_sub = os.getenv('MQTT_TOPIC_DEVICE_PRE_SUB', topic_device_pre)
topic_device_post_sub = os.getenv('MQTT_TOPIC_DEVICE_POST_SUB', topic_device_post)
topic_user_pre_sub = os.getenv('MQTT_TOPIC_USER_PRE_SUB', "from")
topic_user_post_sub = os.getenv('MQTT_TOPIC_USER_POST_SUB', topic_user_post)

topic_pub_constants = [topic_device_pre_pub, topic_device_post_pub, topic_user_pre_pub, topic_user_post_pub]
topic_sub_constants = [topic_device_pre_sub, topic_device_post_sub, topic_user_pre_sub, topic_user_post_sub]

topic_device_status_pre = os.getenv('MQTT_TOPIC_DEVICE_STATUS_PRE', "device")
topic_device_status_post = os.getenv('MQTT_TOPIC_STATUS_POST', "status")

topic_device_status_pre_pub = os.getenv('MQTT_TOPIC_DEVICE_STATUS_PRE_PUB', topic_device_status_pre)
topic_device_status_post_pub = os.getenv('MQTT_TOPIC_DEVICE_STATUS_POST_PUB', topic_device_status_post)
topic_device_status_ext_pub = os.getenv('MQTT_TOPIC_DEVICE_STATUS_EXT_PUB', "desired")

topic_device_status_pre_sub = os.getenv('MQTT_TOPIC_DEVICE_STATUS_PRE_SUB', topic_device_status_pre)
topic_device_status_post_sub = os.getenv('MQTT_TOPIC_DEVICE_STATUS_POST_SUB', topic_device_status_post)
topic_device_status_ext_sub = os.getenv('MQTT_TOPIC_DEVICE_STATUS_EXT_SUB', "retained")

topic_device_status_pub_constants = [topic_device_status_pre_pub, topic_device_status_post_pub,
                                     topic_device_status_ext_pub]
topic_device_status_sub_constants = [topic_device_status_pre_sub, topic_device_status_post_sub,
                                     topic_device_status_ext_sub]

topic_status_pre = os.getenv('MQTT_TOPIC_STATUS_PRE', "device")
topic_status_post = os.getenv('MQTT_TOPIC_STATUS_POST', "controller/status")

topic_status_post_pub = os.getenv('MQTT_TOPIC_STATUS_POST_PUB', topic_status_post)
topic_status_post_sub = os.getenv('MQTT_TOPIC_STATUS_POST_SUB', topic_status_post + "/desired")

topic_status_pub_constants = [topic_status_pre, topic_status_post_pub, None]
topic_status_sub_constants = [topic_status_pre, topic_status_post_sub, None]

topic_user_pre = os.getenv('MQTT_TOPIC_USER_PRE', "device")
topic_user_post = os.getenv('MQTT_TOPIC_USER_POST', "status")
topic_user_ext = os.getenv('MQTT_TOPIC_USER_EXT')

topic_user_constants = [topic_user_pre, topic_user_post, topic_user_ext]

# Listen to interrupt and termination
signal.signal(signal.SIGINT, interrupt_handler)
signal.signal(signal.SIGTERM, interrupt_handler)

# Set default values
broker_address = "localhost"
port = 1883
qos = 1

# Get iterator for command line arguments and skip first item (script call)
arg_it = iter(sys.argv)
next(arg_it)

user_set = False
password_set = False

# Parse environment variables
broker_address = os.getenv('MQTT_BROKER', broker_address)
port = int(os.getenv('MQTT_PORT', port))
qos = int(os.getenv('MQTT_QOS', qos))
user = os.environ.get('MQTT_USER')
password = os.environ.get('MQTT_PASSWORD')

if user is not None:
    user_set = True

if password is not None:
    password_set = True

# Parse command line arguments
for arg in arg_it:
    if arg == '-a':
        broker_address = next(arg_it)

    elif arg == '-q':
        qos = next(arg_it)

    elif arg == '-p':
        port = next(arg_it)

    elif arg == '-u':
        user = next(arg_it)
        user_set = True

    elif arg == '-pw' or arg == '-P':
        password = next(arg_it)
        password_set = True

    elif arg == '-d':
        device = next(arg_it)

    elif arg == '-f':
        import configparser

        configParser = configparser.RawConfigParser()
        configParser.read(next(arg_it))

        if configParser.has_option('settings', 'address'):
            broker_address = configParser.get('settings', 'address')

        if configParser.has_option('settings', 'qos'):
            qos = configParser.getint('settings', 'qos')

        if configParser.has_option('settings', 'port'):
            port = configParser.getint('settings', 'port')

        if configParser.has_option('settings', 'user'):
            user = configParser.get('settings', 'user')
            user_set = True

        if configParser.has_option('settings', 'password'):
            password = configParser.get('settings', 'password')
            password_set = True

        if configParser.has_option('settings', 'device'):
            device = configParser.get('settings', 'device')

    elif arg == '-h':
        print("Usage:", sys.argv[0],
              "[-f <broker-config-file>] "
              "[-a <ip>] "
              "[-p <port>] "
              "[-q <qos>] "
              "[-u <username>] "
              "[-pw <password>] "
              "[-c <listener-config-file>]")
        exit()

    else:
        print("Use \'", sys.argv[0], " -h\' to print available arguments.")
        exit()

if device is None:
    print("Name of controlled device needs to be specified")
    exit()

# User and password need to be set both or none
if user_set != password_set:
    print("Please set either both username and password or none of those")
    exit()

# Set up MQTT client
client = mqtt.Client()
# Set callback functions
client.on_message = on_message
# client.on_subscribe = on_subscribe
client.on_connect = on_connect
client.on_disconnect = on_disconnect
# Set last will
client.will_set(topic_status(topic_status_pub_constants, device), "DISABLED", qos, True)

# Set username and password
if user_set and password_set:
    client.username_pw_set(user, password)

# Connect to broker
client.connect(broker_address, port)
# Start client loop (automatically reconnects after connection loss)
client.loop_forever()
