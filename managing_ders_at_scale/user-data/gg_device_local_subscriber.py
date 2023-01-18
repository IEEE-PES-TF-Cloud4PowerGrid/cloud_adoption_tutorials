# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os
import time
import json
import awsiot.greengrasscoreipc
import awsiot.greengrasscoreipc.client as client
from awsiot.greengrasscoreipc.model import (
    SubscribeToTopicRequest,
    SubscriptionResponseMessage
)

TIMEOUT = 120
publish_interval = 60

ipc_client = awsiot.greengrasscoreipc.connect()


class StreamHandler(client.SubscribeToTopicStreamHandler):
    def __init__(self):
        super().__init__()

    def on_stream_event(self, event: SubscriptionResponseMessage) -> None:
        message_string = event.json_message.message
        print(message_string)
        with open('/tmp/greengrass_subscriber.log', 'a') as f:
            print(message_string, file=f)

    def on_stream_error(self, error: Exception) -> bool:
        return True

    def on_stream_closed(self) -> None:
        pass


device_id = os.getenv("AWS_IOT_THING_NAME")
device_type = device_id.split('-')[1]
topic_name = 'DER/{}'.format(device_type)
print("topic is {}".format(topic_name))

request = SubscribeToTopicRequest()
request.topic = topic_name
handler = StreamHandler()
operation = ipc_client.new_subscribe_to_topic(handler)
future = operation.activate(request)
while True:
    print('sleep for {} seconds'.format(publish_interval))
    time.sleep(publish_interval)

operation.close()