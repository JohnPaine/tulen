#!/usr/bin/python
# -*- coding: utf-8 -*-

import pika
import os
from abc import abstractmethod
from functools import wraps

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
REPLACE_IN_CHAT_CMD = "replace_in_chat"
SOLVE_CAPTCHA_CMD = "solve_captcha_cmd"
STOP_SEAL_CMD = "stop_seal"

# manager -> seal signals (responses on requests)
SOLVE_CAPTCHA_REQ_RESP = "solve_captcha_request_response"

# seal -> manager  signals (requests)
SOLVE_CAPTCHA_REQ = "solve_captcha_request"

# seal -> manager  signals (one-way messages)
SEND_STATS_MSG = "send_stats"
SEAL_EXCEPTION_OCCURRED_MSG = "seal_exception"

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

SEND_STATS_MSG_format = 'seal_id: {}, action: {}, times: {}, load_balancing: {}, chat_count: {}, args_str: {}'
SEAL_EXCEPTION_OCCURRED_MSG_format = 'seal_id: {}, critical exception occurred: {}'
REPLACE_IN_CHAT_CMD_format = 'replacing_seal_id: {}, chat_id: {}, chat_num: {}'

LOAD_BALANCED_ACTIONS = []


class VkUserStatsAction:
    def __init__(self, action_name, args_str):
        self.action = action_name
        self.times = 1
        self.args = [args_str]


# utils:        --------------------------------------------------------------------------------------------------------
def rem_file(name):
    try:
        os.remove(name)
    except OSError:
        pass


def create_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


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
        print('IterCounter, max_count: {}, raise_exception: {}'.format(max_count, raise_exception))

    def count(self):
        self.counter += 1
        print('IterCounter: {}'.format(self.counter))
        if self.raise_exception and self.counter > self.max_count:
            print("IterCounter loop limit reached - {}".format(self.max_count))
            raise SealManagerException("IterCounter loop limit reached - {}".format(self.max_count))

    @staticmethod
    def step_counter(f):
        def wrapper(*args):
            iter_counter = args[0]
            if isinstance(iter_counter, IterCounter):
                iter_counter.count()
            return f(*args)

        return wrapper


# utils:        --------------------------------------------------------------------------------------------------------


# amqp management:      ------------------------------------------------------------------------------------------------
def setup_amqp_connection_(use_credentials=False):
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
    print('binding slot: {} to routing_key: {}'.format(slot, routing_key))
    # routing_key:  <command>.<from>.<to>
    keys = str(routing_key).split('.')
    exchange = get_exchange_type_(routing_key)

    declare_exchange_(channel, exchange)

    bind_queue_(channel, keys[0], routing_key)

    channel.basic_consume(slot,
                          queue=keys[0],
                          no_ack=False)

    print('binding slot: {} to routing_key: {} ---> DONE!!!'.format(slot, routing_key))


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


# account manager       ------------------------------------------------------------------------------------------------
class BreederMode:
    def __init__(self):
        pass

    NoMode = 'nomode'
    TestMode = 'test_mode'


class SealMode:
    def __init__(self):
        pass

    Standalone = 'standalone'
    TestMode = 'test_mode'
    Breeder = 'breeder'

    @staticmethod
    def check_standalone_mode(f):
        def wrapper(*args):
            account_manager = args[0]
            if not hasattr(account_manager, 'mode'):
                return f(*args)
            if account_manager.mode == SealMode.Standalone:
                return None
            return f(*args)

        return wrapper

    @staticmethod
    def collect_vk_user_action_stats(f, collect_args=False):
        @wraps(f)
        def wrapper(*args, **kwargs):
            vk_user = args[0]
            if not vk_user:
                return f(*args, **kwargs)
            action_name = f.__name__
            print('collect_vk_user_action_stats for method: {}'.format(action_name))

            args_str = str(locals()) if collect_args else ''
            if action_name not in vk_user.action_stats:
                vk_user.action_stats[action_name] = VkUserStatsAction(action_name, args_str)
            else:
                vk_user.action_stats[action_name].times += 1
                vk_user.action_stats[action_name].args.append(args_str)
            return f(*args, **kwargs)

        return wrapper

    @staticmethod
    def mark_action_load_balancing(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            action_name = f.__name__
            print('seal vk_user - marking action: {} as load-balancing!'.format(action_name))
            if action_name not in LOAD_BALANCED_ACTIONS:
                LOAD_BALANCED_ACTIONS.append(action_name)
            return f(*args, **kwargs)

        return wrapper


class BaseAccountManager:
    def __init__(self, slot_map):
        self.slot_map = slot_map
        self.listener_connection = setup_amqp_connection_()
        self.listener_channel = self.listener_connection.channel()
        self.publisher_connection = None

    def __enter__(self):
        print('BaseAccountManager.__enter__')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('BaseAccountManager.__exit__')

    @abstractmethod
    def make_signal_routing_key(self, signal, manager='manager', seal_id=None):
        pass

    @abstractmethod
    def make_slot_routing_key(self, queue_name, manager='manager', seal_id=None):
        pass

    @abstractmethod
    def make_message(self, signal, manager='manager', seal_id=None):
        pass

    @SealMode.check_standalone_mode
    def publish_message(self, signal, message='', seal_id=None, manager='manager'):
        print('BaseAccountManager publishing message for signal: {}, message: {}'.format(signal, message))
        with setup_amqp_connection_() as self.publisher_connection:
            routing_key = self.make_signal_routing_key(signal, manager, seal_id)
            if not message:
                message = self.make_message(signal, manager, seal_id)
            publish_message_(self.publisher_connection.channel(), routing_key, message)

    @SealMode.check_standalone_mode
    def bind_slots(self, seal_id=None, manager='manager'):
        print('BaseAccountManager - connecting slots...')
        slot_map = {}
        for queue_name, slot in self.slot_map.items():
            routing_key = self.make_slot_routing_key(queue_name, manager, seal_id)
            slot_map[routing_key] = slot
        bind_slots_(self.listener_channel, slot_map)

    @SealMode.check_standalone_mode
    def receive_signals(self, loop_limit=10):
        for _ in range(loop_limit):
            for queue_name in self.slot_map:
                receive_signals_(self.listener_channel, queue_name)

# account manager       ------------------------------------------------------------------------------------------------
