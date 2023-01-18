# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import time
import json
import os
import random
import awsiot.greengrasscoreipc
from awsiot.greengrasscoreipc.model import (
    PublishToTopicRequest,
    PublishMessage,
    JsonMessage
)


TIMEOUT = 120
publish_interval = 60

ipc_client = awsiot.greengrasscoreipc.connect()


device_id = os.getenv("AWS_IOT_THING_NAME")
device_type = device_id.split('-')[1]
topic_name = 'DER/{}'.format(device_type)


while True:
    telemetry_data = {
            "timestamp": int(round(time.time() * 1000)),
            "nameplate_capacity": 42.5,
            "wind_speed": int(random.random() * 20 + 5),
            "power_output": (random.random() * 30 + 50),
            "location": {
                "longitude": 48.15743,
                "latitude": 11.57549,
            }
    }
    message_json = json.dumps(telemetry_data).encode('utf-8')

    request = PublishToTopicRequest()
    request.topic = topic_name
    publish_message = PublishMessage()
    publish_message.json_message = JsonMessage()
    publish_message.json_message.message = telemetry_data
    request.publish_message = publish_message
    operation = ipc_client.new_publish_to_topic()
    operation.activate(request)
    future = operation.get_response()
    future.result(TIMEOUT)

    print("publish to local topic")
    time.sleep(publish_interval)