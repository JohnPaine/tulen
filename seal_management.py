#!/usr/bin/python
# -*- coding: utf-8 -*-

import pika
from abc import abstractmethod
from functools import wraps
from seal_management_utils import *

"""
SEAL MANAGEMENT

IDEA.
   We have 2 types of exchanges:
       1. Manager to seal
       2. Seal to manager
   We have routing keys of format:     <command>.<from>.<to>
   And we have queues for all message types (signals):     add_friend, join_chat, stop_seal, etc
   So when manager wants to send an add-friend signal(command) to seal with id 123456 he has to publish his message
       to exchange manager_to_seal with routing key add_friend.manager.123456
   On the other hand, a seal that wants to receive an add_friend signal(command) from manager has to:
       1. Declare queue with name add_friend
       2. Bind it to exchange manager_to_seal and routing key add_friend.manager.123456 or add_friend.*.123456
       3. Consume messages from this queue with corresponding callback
   In this case, all messages from queue will be delivered to this callback for this seal
   
SCHEME.
    routing keys:
    <signal(command)>.manager.12345 - meaning route from manager to seal with id 12345
    <signal(command)>.12345.manager - meaning route from seal with id 12345 to manager
    <signal(command)>.12345.2345678 - meaning route from seal with id 12345 to seal with id 2345678

"""
# queues (signals):
# manager -> seal signals (commands)
ADD_FRIEND_CMD = "add_friend"
SOLVE_CAPTCHA_CMD = "solve_captcha_cmd"
STOP_SEAL_CMD = "stop_seal"
CONNECT_TO_SEALS_CMD = "connect_to_seals"

# manager -> seal signals (responses on requests)
SOLVE_CAPTCHA_REQ_RESP = "solve_captcha_request_response"

# seal -> manager  signals (requests)
SOLVE_CAPTCHA_REQ = "solve_captcha_request"

# seal -> manager  signals (one-way messages)
SEND_STATS_MSG = "send_stats"
SEAL_EXCEPTION_OCCURRED_MSG = "seal_exception"

# seal -> manager  signals (responses on requests)
SOLVE_CAPTCHA_CMD_RESP = "solve_captcha_cmd_response"

"""
CHAT MANAGEMENT

IDEA. 

    manager detects replacing (seal_2, least loaded) and replaceable (seal_1, most loaded) seals
    manager -> to seal_1: replace yourself in N chats with seal_2
    seal_1 takes first N dialogs in which seal_2 ain't present yet

    [simplified a bit]
    foreach dialog in selected_dialogs:
        result = vk_user.addChatUser(seal_2)
        if result == ok:
            vk_user.send_message('seal_1 switched with seal_2 in this chat. Adios!')
            vk_user.removeChatUser(seal_1)
        elif result == already_in_chat:
            chat_data = vk_user.collect_chat_data(dialog.id)
            emit_signal(seal_2, JOIN_CHAT_BY_DATA...

    seal_2.on_join_chat_by_data(...):
        # discuss:
        seal_2 could iterate through all it's chats (from 0 to last_chat_id??) with vk_user.getChat() e.g.
        searching for property: "left": 1 - it will be set for chats that seal_2 left by himself
        and also comparing chat data

"""

# CHAT MANAGEMENT COMMANDS
# seal -> other seal
JOIN_CHAT_CMD = "join_chat"
QUIT_CHAT_CMD = "quit_chat"
# maanger -> seal
REPLACE_IN_CHAT_CMD = "replace_in_chat"

# exchanges:
MANAGER_TO_SEAL_EXCHANGE = "manager_to_seal"
SEAL_TO_MANAGER_EXCHANGE = "seal_to_manager"
SEAL_TO_SEAL = "seal_to_seal"

AMQP_SERVER = "localhost"
AMQP_USER = "seal"
AMQP_PASS = "seal2017"
AMQP_VHOST = "/"

MANAGER_NAME = 'manager'

SEND_STATS_MSG_format = 'seal_id: {}, action: {}, times: {}, load_balancing: {}, chat_count: {}, args_str: {}'
SEAL_EXCEPTION_OCCURRED_MSG_format = 'seal_id: {}, critical exception occurred: {}'
REPLACE_IN_CHAT_CMD_format = 'replacing_seal_id: {}, chat_id: {}, chat_num: {}'
CONNECT_TO_SEALS_CMD_format = 'seal_ids: {}'
JOIN_CHAT_CMD_format = 'title: {}, admin_id: {}, replaceable_seal_id: {}, replacing_seal_id: {}'

LOAD_BALANCED_ACTIONS = []


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
    manager_exchange = 'manager'
    if manager_exchange in keys:
        return MANAGER_TO_SEAL_EXCHANGE if keys[1] == manager_exchange else SEAL_TO_MANAGER_EXCHANGE
    return SEAL_TO_SEAL


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

    print('\tperforming basic publish: message:{},\n\texchange:{},\n\tprops:{},\n\trouting_key:{}\n'
          .format(message, exchange, msg_props, routing_key))

    channel.basic_publish(body=message,
                          exchange=exchange,
                          properties=msg_props,
                          routing_key=routing_key)

    if print_log:
        print("Sent message {} tagged with routing key '{}' to exchange {}."
              .format(message, routing_key, exchange))


def process_signal_(channel, signal, inactivity_timeout=0.01):
    for reply in channel.consume(signal, inactivity_timeout=inactivity_timeout):
        if not reply:
            break
        print(reply)

    channel.cancel()


# amqp management:      ------------------------------------------------------------------------------------------------


# account manager       ------------------------------------------------------------------------------------------------
class VkUserStatsAction:
    def __init__(self, action_name, args_str):
        self.action = action_name
        self.times = 1
        self.args = [args_str]


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
        @wraps(f)
        def wrapper(*args, **kwargs):
            account_manager = args[0]
            if not hasattr(account_manager, 'mode'):
                return f(*args, **kwargs)
            if account_manager.mode == SealMode.Standalone:
                return None
            return f(*args, **kwargs)

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
    def __init__(self):
        self.slot_map = {}
        self.listener_connection = setup_amqp_connection_()
        self.listener_channel = self.listener_connection.channel()
        self.publisher_connection = None

    def __enter__(self):
        print('BaseAccountManager.__enter__')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('BaseAccountManager.__exit__')

    @staticmethod
    def make_routing_key(signal, sender_id, receiver_id):
        return '{}.{}.{}'.format(signal, sender_id, receiver_id)

    @SealMode.check_standalone_mode
    def publish_message(self, signal, sender_id, receiver_id, message=''):
        print('BaseAccountManager publishing message for signal: {}, message: {}, sender_id:{}, receiver_id:{}'
              .format(signal, message, str(sender_id), str(receiver_id)))

        with setup_amqp_connection_() as self.publisher_connection:
            routing_key = BaseAccountManager.make_routing_key(signal, sender_id, receiver_id)
            if not message:
                message = 'signal:{} from: {} to: {}'.format(signal, sender_id, receiver_id)
            print('\tpublishing message: {} for routing_key: {}'.format(message, routing_key))
            publish_message_(self.publisher_connection.channel(), routing_key, message)

    @SealMode.check_standalone_mode
    def bind_slots(self, sender_id, receiver_id, slot_map):
        print('BaseAccountManager - connecting slots for sender_id:{},\n\treceiver_id:{},\n\tslot_map:{}'
              .format(sender_id, receiver_id, slot_map))
        slots = {}
        added_slots = {}

        if sender_id == receiver_id:
            print('Binding slots error: receiver and sender cannot coincide!!!')
            return

        for signal, slot in slot_map.items():
            routing_key = BaseAccountManager.make_routing_key(signal, sender_id, receiver_id)
            slots[routing_key] = slot
            if not signal in slot_map:
                added_slots[signal] = slot

        bind_slots_(self.listener_channel, slots)
        self.slot_map = {**slot_map, **added_slots}

    @SealMode.check_standalone_mode
    def receive_signals(self, loop_limit=10, slot_map=None):
        if not slot_map:
            slot_map = self.slot_map

        for _ in range(loop_limit):
            for signal in slot_map:
                process_signal_(self.listener_channel, signal)

# account manager       ------------------------------------------------------------------------------------------------
