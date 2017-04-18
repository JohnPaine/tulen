#!/usr/bin/python
# -*- coding: utf-8 -*-

import pika
import os

########################################################################################################################
# Idea explanation
########################################################################################################################
#
#   We have 2 types of exchanges:
#       1. Manager to seal
#       2. Seal to manager
#   We have routing keys of format:     <command>.<from>.<to>
#   And we have queues for all message types (signals):     add_friend, join_chat, stop_seal, etc
#   So when manager wants to send an add-friend signal(command) to seal with id 123456 he has to publish his message
#       to exchange manager_to_seal with routing key add_friend.manager.123456
#   On the other hand, a seal that wants to receive an add_friend signal(command) from manager has to:
#       1. Declare queue with name add_friend
#       2. Bind it to exchange manager_to_seal and routing key add_friend.manager.123456 or add_friend.*.123456
#       3. Consume messages from this queue with corresponding callback
#   In this case, all messages from queue will be delivered to this callback for this seal
#
########################################################################################################################

# queues (signals):
# manager -> seal signals (commands)
ADD_FRIEND_CMD = "add_friend"
JOIN_CHAT_CMD = "join_chat"
QUIT_CHAT_CMD = "quit_chat"
SOLVE_CAPTCHA_CMD = "solve_captcha_cmd"
STOP_SEAL_CMD = "stop_seal"

# manager -> seal signals (responses on requests)
SOLVE_CAPTCHA_REQ_RESP = "solve_captcha_request_response"

# seal -> manager  signals (requests)
SOLVE_CAPTCHA_REQ = "solve_captcha_request"

# seal -> manager  signals (one-way messages)
SEND_STATS_MSG = "send_stats"

# seal -> manager  signals (responses on requests)
SOLVE_CAPTCHA_CMD_RESP = "solve_captcha_cmd_response"

# exchanges:
MANAGER_TO_SEAL_EXCHANGE = "manager_to_seal"
SEAL_TO_MANAGER_EXCHANGE = "seal_to_manager"

# routing keys:
# <signal(command)>.manager.12345 - meaning route from manager to seal with id 12345
# <signal(command)>.12345.manager - meaning route from seal with id 12345 to manager
# <signal(command)>.12345.2345678 - meaning route from seal with id 12345 to seal with id 2345678

AMQP_SERVER = "localhost"
AMQP_USER = "seal"
AMQP_PASS = "seal2017"
AMQP_VHOST = "/"


# utils:        --------------------------------------------------------------------------------------------------------
def rem_file(name):
    try:
        os.remove(name)
    except OSError:
        pass


class SealManagerException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return u"SealManager exception: {}".format(self.value)


class IterCounter:
    def __init__(self, max_count=10, raise_exception=True):
        self.counter = 0
        self.max_count = max_count
        self.raise_exception = raise_exception

    def count(self):
        self.counter += 1
        if self.raise_exception and self.counter > self.max_count:
            raise SealManagerException("IterCounter loop limit reached - {}".format(self.max_count))

# utils:        --------------------------------------------------------------------------------------------------------


# amqp management:      ------------------------------------------------------------------------------------------------
def setup_amqp_channel_(use_credentials=False):
    if use_credentials:
        creds_broker = pika.PlainCredentials(AMQP_USER, AMQP_PASS)
    else:
        creds_broker = None

    connection_params = pika.ConnectionParameters(host=AMQP_SERVER,
                                            virtual_host=AMQP_VHOST,
                                            credentials=creds_broker)
    return pika.BlockingConnection(connection_params)


def get_exchange_type_(routing_key):
    # routing_key:  <command>.<from>.<to>
    keys = str(routing_key).split('.')
    return MANAGER_TO_SEAL_EXCHANGE if keys[1] == 'manager' else SEAL_TO_MANAGER_EXCHANGE


def declare_exchange_(channel, exchange):
    channel.exchange_declare(exchange=exchange,
                             type="topic",
                             passive=False,
                             durable=True,
                             auto_delete=False)


def bind_queue_(channel, queue_name, routing_key):
    channel.queue_declare(queue=queue_name, auto_delete=False, durable=True, exclusive=False)

    channel.queue_bind(queue=queue_name,
                       exchange=get_exchange_type_(routing_key),
                       routing_key=routing_key)


def bind_slot_(channel, routing_key, slot):
    # routing_key:  <command>.<from>.<to>
    keys = str(routing_key).split('.')
    exchange = get_exchange_type_(routing_key)

    declare_exchange_(channel, exchange)

    bind_queue_(channel, keys[0], routing_key)

    channel.basic_consume(slot,
                          queue=keys[0],
                          no_ack=False)


def bind_slots_(channel, slot_map):
    for routing_key, slot in slot_map.items():
        bind_slot_(channel, routing_key, slot)


def publish_message_(channel, routing_key, message, content_type='text/plain', print_log=False):
    msg_props = pika.BasicProperties()
    msg_props.content_type = content_type
    msg_props.durable = True
    # msg_props.delivery_mode = 2     # make message persistent

    exchange = get_exchange_type_(routing_key)
    declare_exchange_(channel, exchange)

    channel.basic_publish(body=message,
                          exchange=exchange,
                          properties=msg_props,
                          routing_key=routing_key)

    if print_log:
        print("Sent message {} tagged with routing key '{}' to exchange {}."
              .format(message, routing_key, exchange))


def receive_signals_(channel, queue_name, inactivity_timeout=0.01):
    for reply in channel.consume(queue_name, inactivity_timeout=inactivity_timeout):
        if not reply:
            break
        print(reply)

    channel.cancel()

# amqp management:      ------------------------------------------------------------------------------------------------
