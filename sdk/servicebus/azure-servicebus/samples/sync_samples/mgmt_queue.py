#!/usr/bin/env python

# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Example to show managing queue entities under a ServiceBus Namespace, including
    - Create a queue
    - Get queue properties and runtime information
    - Update a queue
    - Delete a queue
    - List queues under the given ServiceBus Namespace
"""

import os
import uuid
from azure.servicebus.management import ServiceBusAdministrationClient

CONNECTION_STR = os.environ['SERVICE_BUS_CONNECTION_STR']
QUEUE_NAME = "sb_mgmt_queue" + str(uuid.uuid4())


def create_queue(servicebus_mgmt_client):
    print("-- Create Queue")
    servicebus_mgmt_client.create_queue(QUEUE_NAME, max_delivery_count=10, dead_lettering_on_message_expiration=True)
    print("Queue {} is created.".format(QUEUE_NAME))
    print("")


def delete_queue(servicebus_mgmt_client):
    print("-- Delete Queue")
    servicebus_mgmt_client.delete_queue(QUEUE_NAME)
    print("Queue {} is deleted.".format(QUEUE_NAME))
    print("")


def list_queues(servicebus_mgmt_client):
    print("-- List Queues")
    for queue_properties in servicebus_mgmt_client.list_queues():
        print("Queue Name:", queue_properties.name)
    print("")


def get_and_update_queue(servicebus_mgmt_client):
    print("-- Get and Update Queue")
    queue_properties = servicebus_mgmt_client.get_queue(QUEUE_NAME)
    print("Queue Name:", queue_properties.name)
    print("Queue Settings:")
    print("Auto Delete on Idle:", queue_properties.auto_delete_on_idle)
    print("Default Message Time to Live:", queue_properties.default_message_time_to_live)
    print("Dead Lettering on Message Expiration:", queue_properties.dead_lettering_on_message_expiration)
    print("Please refer to QueueDescription for complete available settings.")
    print("")
    # update by updating the properties in the model
    queue_properties.max_delivery_count = 5
    servicebus_mgmt_client.update_queue(queue_properties)

    # update by passing keyword arguments
    queue_properties = servicebus_mgmt_client.get_queue(QUEUE_NAME)
    servicebus_mgmt_client.update_queue(queue_properties, max_delivery_count=3)


def get_queue_runtime_properties(servicebus_mgmt_client):
    print("-- Get Queue Runtime Properties")
    queue_runtime_properties = servicebus_mgmt_client.get_queue_runtime_properties(QUEUE_NAME)
    print("Queue Name:", queue_runtime_properties.name)
    print("Queue Runtime Properties:")
    print("Updated at:", queue_runtime_properties.updated_at_utc)
    print("Size in Bytes:", queue_runtime_properties.size_in_bytes)
    print("Message Count:", queue_runtime_properties.total_message_count)
    print("Active Message Count:", queue_runtime_properties.active_message_count)
    print("Scheduled Message Count:", queue_runtime_properties.scheduled_message_count)
    print("Dead-letter Message Count:", queue_runtime_properties.dead_letter_message_count)
    print("Please refer to QueueRuntimeProperties from complete available runtime properties.")
    print("")


with ServiceBusAdministrationClient.from_connection_string(CONNECTION_STR) as servicebus_mgmt_client:
    create_queue(servicebus_mgmt_client)
    list_queues(servicebus_mgmt_client)
    get_and_update_queue(servicebus_mgmt_client)
    get_queue_runtime_properties(servicebus_mgmt_client)
    delete_queue(servicebus_mgmt_client)
