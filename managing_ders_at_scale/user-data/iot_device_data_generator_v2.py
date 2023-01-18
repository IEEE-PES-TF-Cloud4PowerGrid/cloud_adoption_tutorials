from awscrt import mqtt
import sys
import threading
import time
from uuid import uuid4
import json
import random
from datetime import datetime
import der_class

random.seed(datetime.now())
sampling_interval = 60

# generate a random battery capacity between min and max value. Unit: kWh
def get_random_number_between(lower_value, upper_value):
    value = 0.0
    assert(upper_value > lower_value > 0)
    value = random.random() * (upper_value - lower_value) + lower_value
    return value

# generate a random discharge power to deplete the battery in 3 to 5 hours. Unit: kW
def get_random_discharge_power(battery_cap):
    assert(battery_cap > 0)
    battery_discharge_power = battery_cap / (random.random() * 2 + 3)
    return battery_discharge_power

# generate random data for devices (for testing only)
def get_device_rt_data(metrics):
    rt_data = {}
    for metric in metrics:
        rt_data[metric] = get_random_number_between(10, 100)
    return rt_data

def get_wind_speed(curr_hour):
    wind_speed = 0
    if curr_hour in [0, 1, 2, 22, 23]:
        wind_speed = int(get_random_number_between(10, 25))
    else:
        wind_speed = int(get_random_number_between(5, 10))
    return wind_speed

# This sample uses the Message Broker for AWS IoT to send and receive messages
# through an MQTT connection. On startup, the device connects to the server,
# subscribes to a topic, and begins publishing messages to that topic.
# The device should receive those same messages back from the message broker,
# since it is subscribed to that same topic.

# Parse arguments
import command_line_utils;
cmdUtils = command_line_utils.CommandLineUtils("PubSub - Send and recieve messages through an MQTT connection.")
cmdUtils.add_common_mqtt_commands()
cmdUtils.add_common_topic_message_commands()
cmdUtils.add_common_proxy_commands()
cmdUtils.add_common_logging_commands()
cmdUtils.register_command("key", "<path>", "Path to your key in PEM format.", True, str)
cmdUtils.register_command("cert", "<path>", "Path to your client certificate in PEM format.", True, str)
cmdUtils.register_command("port", "<int>", "Connection port. AWS IoT supports 443 and 8883 (optional, default=auto).", type=int)
cmdUtils.register_command("client_id", "<str>", "Client ID to use for MQTT connection (optional, default='test-*').", default="test-" + str(uuid4()))
cmdUtils.register_command("count", "<int>", "The number of messages to send (optional, default='10').", default=10, type=int)
cmdUtils.register_command("device_type", "<str>", "DER device type", default="battery", type=str)
# Needs to be called so the command utils parse the commands
cmdUtils.get_args()

received_count = 0
received_all_event = threading.Event()

# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        print("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)


def on_resubscribe_complete(resubscribe_future):
        resubscribe_results = resubscribe_future.result()
        print("Resubscribe results: {}".format(resubscribe_results))

        for topic, qos in resubscribe_results['topics']:
            if qos is None:
                sys.exit("Server rejected resubscribe to topic: {}".format(topic))


# Callback when the subscribed topic receives a message
def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    print("Received message from topic '{}': {}".format(topic, payload))
    global received_count
    received_count += 1
    if received_count == cmdUtils.get_command("count"):
        received_all_event.set()

if __name__ == '__main__':
    mqtt_connection = cmdUtils.build_mqtt_connection(on_connection_interrupted, on_connection_resumed)

    print("Connecting to {} with client ID '{}'...".format(
        cmdUtils.get_command(cmdUtils.m_cmd_endpoint), cmdUtils.get_command("client_id")))
    connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    print("Connected!")

    message_count = cmdUtils.get_command("count")
    message_topic = cmdUtils.get_command(cmdUtils.m_cmd_topic)
    message_string = cmdUtils.get_command(cmdUtils.m_cmd_message)

    # Subscribe
    print("Subscribing to topic '{}'...".format(message_topic))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=message_topic,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message_received)

    subscribe_result = subscribe_future.result()
    print("Subscribed with {}".format(str(subscribe_result['qos'])))

    # Publish message to server desired number of times.
    # This step is skipped if message is blank.
    # This step loops forever if count was set to 0.
    if message_string:
        if message_count == 0:
            print ("Sending messages until program killed")
        else:
            print ("Sending {} message(s)".format(message_count))

        publish_count = 1
        device_id = cmdUtils.get_command("client_id")
        device_type = cmdUtils.get_command("device_type")
        message = {}
        metrics = {}
        resource = None
        with open('metrics_def.json') as metrics_file:
            metrics = json.load(metrics_file)
        if device_type == "battery":
            resource = der_class.Battery(device_id, round(get_random_number_between(80, 100), 1))
        elif device_type == "PV":
            resource = der_class.PV(device_id, round(get_random_number_between(20, 30), 1))
        elif device_type == "wind":
            resource = der_class.WindMachine(device_id, 50)
        while (publish_count <= message_count) or (message_count == 0):
            # message = "{} [{}]".format(message_string, publish_count)
            # capacity = round(get_random_number_between(8, 15), 2)    #keep only 2 digits
            # discharge_power = round(get_random_discharge_power(capacity), 2)
            # rt_data = get_device_rt_data(metrics[device_type])
            message["device_id"] = device_id
            message["device_type"] = device_type
            message["ts"] = datetime.now().replace(microsecond=0, second=0).isoformat()
            for metric in metrics[device_type]:
                if device_type == "battery":
                    message[metric] = resource.get_metric_value(metric, sampling_interval = sampling_interval)
                elif device_type == "wind":
                    wind_speed = get_wind_speed(curr_hour=datetime.now().hour)
                    message[metric] = resource.get_metric_value(metric, wind_speed=wind_speed)
                else:
                    message[metric] = resource.get_metric_value(metric)
                # message[metric] = rt_data[metric]
                # message['capacity'] = capacity
                # message['discharge_power'] = discharge_power
            # print("Publishing message to topic '{}': {}".format(message_topic, message))
            message_json = json.dumps(message)
            print("Publishing message to topic '{}': {}".format(message_topic, message_json))
            mqtt_connection.publish(
                topic=message_topic,
                payload=message_json,
                qos=mqtt.QoS.AT_LEAST_ONCE)
            time.sleep(sampling_interval)
            publish_count += 1

    # Wait for all messages to be received.
    # This waits forever if count was set to 0.
    if message_count != 0 and not received_all_event.is_set():
        print("Waiting for all messages to be received...")

    received_all_event.wait()
    print("{} message(s) received.".format(received_count))

    # Disconnect
    print("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    print("Disconnected!")