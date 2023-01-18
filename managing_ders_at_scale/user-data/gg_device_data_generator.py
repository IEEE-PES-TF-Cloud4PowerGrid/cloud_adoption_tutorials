import json
import time
import os
import random
from datetime import datetime

import awsiot.greengrasscoreipc
import awsiot.greengrasscoreipc.model as model

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

def get_wind_speed(curr_hour):
    wind_speed = 0
    if curr_hour in [0, 1, 2, 22, 23]:
        wind_speed = int(get_random_number_between(10, 25))
    else:
        wind_speed = int(get_random_number_between(5, 10))
    return wind_speed

if __name__ == '__main__':
    ipc_client = awsiot.greengrasscoreipc.connect()
    device_id = os.getenv("AWS_IOT_THING_NAME")
    device_type = device_id.split('-')[1]
    topic_name = 'DER/{}'.format(device_type)
    message = {}
    metrics = {}
    resource = None
    curr_dir=os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(curr_dir, 'metrics_def.json')) as metrics_file:
        metrics = json.load(metrics_file)
    if device_type == "battery":
        resource = der_class.Battery(device_id, round(get_random_number_between(80, 100), 1))
    elif device_type == "PV":
        resource = der_class.PV(device_id, round(get_random_number_between(20, 30), 1))
    elif device_type == "wind":
        resource = der_class.WindMachine(device_id, 50)

    while True:
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

        op = ipc_client.new_publish_to_iot_core()
        op.activate(model.PublishToIoTCoreRequest(
            topic_name=topic_name,
            qos=model.QOS.AT_LEAST_ONCE,
            payload=json.dumps(message).encode(),
        ))
        try:
            result = op.get_response().result(timeout=5.0)
            print("successfully published message:", result)
        except Exception as e:
            print("failed to publish message:", e)

        time.sleep(sampling_interval)