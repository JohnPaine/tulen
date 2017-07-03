#!/usr/bin/python
# -*- coding: utf-8 -*-

from functools import wraps
import traceback

import pika

"""
SEAL MANAGEMENT

IDEA.
    For management we got:
    1. Queue name (as post box for each message receiver, e.g manager, <seal_id>, all_seals, etc)
    2. Exchange name, which is chosen automatically depending on sender-receiver: 
        a. manager_to_seals
        b. seals_to_manager
        c. seal_to_seal
    3. Routing key of format: <command>.<sender_id>.<receiver_id>
    Routing keys describe the queue to which message would be sent from exchange
    Each queue (post box) is binned to 1 slot that is used for message dispatching by command type
   
SCHEME.
    routing keys:
    add_friend.manager.12345 - an add-friend command from manager to seal with id 12345
    solve_captcha_request.12345.manager - a solve-captcha request from seal with 12345 to manager
    join_chat.12345.2345678 - an invitation-to-chat command from one seal (id 12345) to another (id 2345678)

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
# manager -> seal
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
    if MANAGER_NAME in keys:
        return MANAGER_TO_SEAL_EXCHANGE if keys[1] == MANAGER_NAME else SEAL_TO_MANAGER_EXCHANGE
    return SEAL_TO_SEAL


def declare_exchange_(channel, exchange):
    channel.exchange_declare(exchange=exchange,
                             type="topic",
                             passive=False,
                             durable=True,
                             auto_delete=False)


def bind_slot_(channel, receiver_id, routing_keys, slot, exchange=None):
    print('binding queue: {} to exchange: {} by routing_keys: {} for slot: {}'
          .format(receiver_id, exchange, routing_keys, slot))

    channel.queue_declare(queue=str(receiver_id), auto_delete=False, durable=True, exclusive=False)

    for routing_key in routing_keys:
        # routing_key:  <command>.<sender_id>.<receiver_id>

        if not exchange:
            exchange = get_exchange_type_(routing_key)
        declare_exchange_(channel, exchange)

        print('\tbinding queue: {} to exchange: {} by routing_key: {} ---> DONE!!!'
              .format(receiver_id, exchange, routing_key))

        channel.queue_bind(queue=str(receiver_id),
                           exchange=exchange,
                           routing_key=routing_key)

    channel.basic_consume(slot,
                          queue=str(receiver_id),
                          no_ack=False)

    print('binding queue: {} to exchange: {} by routing_keys: {} for slot: {} ---> DONE!'
          .format(receiver_id, exchange, routing_keys, slot))


def publish_message_(channel, routing_key, message, content_type='text/plain'):
    msg_props = pika.BasicProperties()
    msg_props.content_type = content_type
    msg_props.durable = True
    msg_props.delivery_mode = 2  # make message persistent

    exchange = get_exchange_type_(routing_key)
    declare_exchange_(channel, exchange)

    # print('\tperforming basic publish: message:{},\n\texchange:{},\n\tprops:{},\n\trouting_key:{}\n'
    #       .format(message, exchange, msg_props, routing_key))

    channel.basic_publish(body=message,
                          exchange=exchange,
                          properties=msg_props,
                          routing_key=routing_key)


def consume_queue_messages_(channel, queue, inactivity_timeout=0.01):
    for reply in channel.consume(str(queue), inactivity_timeout=inactivity_timeout):
        if not reply:
            break
        print(reply)

    channel.cancel()


def check_routing(signal=None):
    def decor(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            g = f.__globals__
            receiver_id = g.get('current_receiver_id', None)
            if not receiver_id:
                return f(*args, **kwargs)

            # print('check_routing for receiver_id: {}, signal: {}'.format(receiver_id, signal))

            method = args[1]
            # print('checking routing_key: {} for receiver_id: {} and signal: {}'
            #       .format(method.routing_key, receiver_id, signal))
            routing_keys = method.routing_key.split('.')
            if signal:
                assert str(routing_keys[0]) == str(signal), \
                    "expected signal: {} doesn't coincide with routed signal: {}" \
                        .format(signal, routing_keys[0])
            assert str(routing_keys[2]) == str(receiver_id), \
                "expected receiver_id: {} doesn't coincide with routing_key receiver_id: {}" \
                    .format(receiver_id, routing_keys[2])
            assert str(routing_keys[1]) != str(receiver_id), \
                "sender_id: {} cannot coincide with receiver_id: {} !!!" \
                    .format(routing_keys[1], receiver_id)

            return f(*args, **kwargs)

        return wrapper

    return decor


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
    def collect_vk_user_action_stats(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            vk_user = args[0]
            if not vk_user:
                return f(*args, **kwargs)
            action_name = f.__name__
            # print('collect_vk_user_action_stats for method: {}'.format(action_name))

            # TODO: do we need args???
            # args_str = str(locals()) if collect_args else ''
            if action_name not in vk_user.action_stats:
                vk_user.action_stats[action_name] = VkUserStatsAction(action_name, '')
            else:
                vk_user.action_stats[action_name].times += 1
                vk_user.action_stats[action_name].args.append('')
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
    def __init__(self, receiver_id):
        self.listener_connection = setup_amqp_connection_()
        self.listener_channel = self.listener_connection.channel()
        self.publisher_connection = None
        self.receiver_id = str(receiver_id)

    def __enter__(self):
        print('BaseAccountManager.__enter__')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('BaseAccountManager.__exit__')

    @staticmethod
    def make_routing_key(signal, sender_id, receiver_id):
        return '{}.{}.{}'.format(signal, sender_id, receiver_id)

    @SealMode.check_standalone_mode
    def publish_message(self, signal, receiver_id, message=''):
        # print('BaseAccountManager publishing message: {}, for signal: {}, sender_id:{}, receiver_id:{}'
        #       .format(message, signal, str(self.receiver_id), str(receiver_id)))

        with setup_amqp_connection_() as self.publisher_connection:
            routing_key = BaseAccountManager.make_routing_key(signal, self.receiver_id, receiver_id)
            if not message:
                message = 'signal: {} from: {} to: {}'.format(signal, self.receiver_id, receiver_id)
            print('\tpublishing message: {} for routing_key: {}'.format(message, routing_key))
            publish_message_(self.publisher_connection.channel(), routing_key, message)

    @SealMode.check_standalone_mode
    def bind_slot(self, sender_id, signal_list, slot, exchange=None):
        routing_keys = []
        for signal in signal_list:
            routing_keys.append(BaseAccountManager.make_routing_key(signal, sender_id, self.receiver_id))

        bind_slot_(self.listener_channel, self.receiver_id, routing_keys, slot, exchange)

    @SealMode.check_standalone_mode
    def consume_messages(self, loop_limit=10):
        for _ in range(loop_limit):
            consume_queue_messages_(self.listener_channel, self.receiver_id)

    def try_process(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            msg = 'Something went wrong while processing: {} for receiver_id: {}, e: {}'\
                .format(func, self.receiver_id, e)
            print(msg)
            traceback.print_exc()

# account manager       ------------------------------------------------------------------------------------------------
