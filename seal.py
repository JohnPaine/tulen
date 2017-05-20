#!/usr/bin/python
# -*- coding: utf-8 -*-

import yaml
import time
import argparse
from seal_management import *
import logging.config
from vkuser import VkUser
import random
from parse import compile as parse_compile
import traceback

# logging:      --------------------------------------------------------------------------------------------------------
LOG_SETTINGS = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'default',
            'stream': 'ext://sys.stdout',
        },
    },
    'formatters': {
        'default': {
            '()': 'multiline_formatter.formatter.MultilineMessagesFormatter',
            'format': '[%(levelname)s] %(message)s'
        },
    },
    'loggers': {
        'seal': {
            'level': 'DEBUG',
            'handlers': ['console', ]
        },
    }
}

logging.config.dictConfig(LOG_SETTINGS)
logger = logging.getLogger("seal")


# logging:      --------------------------------------------------------------------------------------------------------


# amqp management       ================================================================================================
class SealAccountManager(BaseAccountManager):
    def __init__(self, seal_id, mode):
        super().__init__()
        self.seal_id = seal_id
        self.mode = mode
        self.vk_user = None

    def __enter__(self):
        print('SealAccountManager.__enter__')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('SealAccountManager.__exit__')

    # BaseAccountManager interface      ================================================================================
    def publish_message_to_seal(self, signal, receiver_id, message=''):
        super().publish_message(signal, self.seal_id, receiver_id, message)

    def publish_message_to_manager(self, signal, message=''):
        super().publish_message(signal, self.seal_id, MANAGER_NAME, message)

    def publish_message(self, signal, sender_id=None, receiver_id=None, message=''):
        if not receiver_id:
            if signal in MANAGER_TO_SEAL_SLOT_MAP:
                receiver_id = MANAGER_NAME
            else:
                raise SealManagerException('SealAccountManager, publish_message: cannot deduce receiver id!')
        sender_id = self.seal_id
        super().publish_message(signal, sender_id, receiver_id, message)

        # BaseAccountManager interface      ================================================================================


seal = None


# amqp management       ================================================================================================


# slots:        --------------------------------------------------------------------------------------------------------
def on_add_friend_cmd(channel, method, header, body):
    """Accepts add-friend command from manager."""

    print("on_add_friend_cmd, body - {}, header - {}, method - {}".format(body, header, method))

    channel.basic_ack(delivery_tag=method.delivery_tag)


def on_replace_in_chat_cmd(channel, method, header, body):
    """Accepts replace-in-chat command from manager."""

    print("on_replace_in_chat_cmd, body: {},\n\theader: {},\n\tmethod: {}".format(body, header, method))

    cmd_parser = parse_compile(REPLACE_IN_CHAT_CMD_format)
    parsed = cmd_parser.parse(body.decode('utf-8'))

    replacing_seal_id = int(parsed[0])
    chat_id = int(parsed[1])
    chat_num = int(parsed[2])

    def replace_in_chat(_chat_id, _replacing_seal_id):
        nonlocal chat_num

        print('\t\tseal, replace_in_chat, chat_id:{}. replacing_seal_id:{}'.format(_chat_id, _replacing_seal_id))

        users = seal.vk_user.get_chat_users(_chat_id)

        if int(_replacing_seal_id) in users:
            print('CAN\'T replace seal_id:{} with replacing_seal_id:{} in chat_id:{} - he\'s already in chat!'
                  .format(seal.seal_id, _replacing_seal_id, _chat_id))
        else:
            print('trying to replace THIS seal_id:{} with replacing_seal_id:{} in chat_id:{}'
                  .format(seal.seal_id, _replacing_seal_id, _chat_id))
            try:
                seal.vk_user.add_chat_user(int(_chat_id), int(_replacing_seal_id))
                chat_data = seal.vk_user.get_chat(_chat_id)
                print('chat_data: {}'.format(chat_data))
                seal.publish_message_to_seal(JOIN_CHAT_CMD,
                                             _replacing_seal_id,
                                             JOIN_CHAT_CMD_format.format(chat_data['title'].encode('utf-8'),
                                                                         chat_data['admin_id'],
                                                                         seal.seal_id,
                                                                         _replacing_seal_id))
                seal.vk_user.remove_chat_user(int(_chat_id), seal.seal_id)
                chat_num -= 1
            except Exception as e:
                print('Exception occurred in replacing THIS seal_id: {} with seal: {} in chat_id: {}'
                      .format(seal.seal_id, _replacing_seal_id, _chat_id))

    if chat_id > 0:
        replace_in_chat(chat_id, replacing_seal_id)
    else:
        dialog_list = seal.vk_user.get_dialogs()
        print('\tdialog list length: {}'.format(len(dialog_list)))

        for dialog in dialog_list:
            if chat_num <= 0:
                break

            message = dialog['message']
            if 'chat_id' not in message:
                continue

            current_chat_id = message['chat_id']
            print('\t\t\tCHAT_ID: {}'.format(current_chat_id))

            replace_in_chat(current_chat_id, replacing_seal_id)

    # print('\tdialog_list: {}'.format(json.dumps(dialog_list, indent=4)))

    channel.basic_ack(delivery_tag=method.delivery_tag)


def on_stop_seal_cmd(channel, method, header, body):
    """Accepts stop-seal command from manager."""

    print("on_stop_seal_cmd, body: {},\n\theader: {},\n\tmethod: {}".format(body, header, method))

    channel.basic_ack(delivery_tag=method.delivery_tag)
    if seal:
        raise SealManagerException('SealAccountManager {} received stop_signal from manager - stopping...'
                                   .format(seal.seal_id))


def on_connect_to_seals_cmd(channel, method, header, body):
    """Accepts connect-to-seals messages from manager."""

    print("on_connect_to_seals_cmd, body - {},\n\theader - {},\n\tmethod - {}".format(body, header, method))

    cmd_parser = parse_compile(CONNECT_TO_SEALS_CMD_format)
    parsed = cmd_parser.parse(body.decode('utf-8'))

    seal_ids = parsed[0].split(',')
    print('\t\t\tseal_ids:{}'.format(seal_ids))

    for seal_id in seal_ids:
        if int(seal_id) == int(seal.seal_id):
            continue
        seal.bind_slots(seal_id, seal.seal_id, SEAL_TO_SEAL_SLOT_MAP)

    channel.basic_ack(delivery_tag=method.delivery_tag)


def on_join_chat_cmd(channel, method, header, body):
    """Accepts join-chat command from other seals."""

    print("on_join_chat_cmd, body: {},\n\theader: {},\n\tmethod: {}".format(body, header, method))

    cmd_parser = parse_compile(JOIN_CHAT_CMD_format)
    parsed = cmd_parser.parse(body.decode('utf-8'))

    chat_title = bytes(parsed[0], encoding='utf-8').decode('utf-8')
    admin_id = int(parsed[1])
    replaceable_seal_id = int(parsed[2])
    replacing_seal_id = int(parsed[3])
    print('\ton_join_chat_cmd, replaceable_seal_id: {}, replacing_seal_id: {}'
          .format(replaceable_seal_id, replacing_seal_id))
    if replacing_seal_id != seal.seal_id:
        raise SealManagerException('on_join_chat_cmd, replacing_seal_id: {} != THIS seal_id: {}'
                                   .format(replacing_seal_id, seal.seal_id))
    print('\ton_join_chat_cmd, chat_title: {}, admin_id: {}'.format(chat_title, admin_id))
    chat_num = 10
    start_from = 1
    while True:
        try:
            chat_ids = list(str(i) for i in range(start_from, start_from + chat_num))
            chats_data = seal.vk_user.get_chat(chat_id='', chat_ids=chat_ids)
            stop = False
            for chat_data in chats_data:
                print('\t\tchecking chat_data: {}'.format(chat_data))
                if chat_data['admin_id'] == 0:
                    print('\t\t\tstopping chat_data checks')
                    stop = True
                    break
                if chat_title == chat_data['title'] and admin_id == chat_data['admin_id']:
                    if 'left' in chat_data:
                        seal.vk_user.add_chat_user(chat_data['id'], seal.seal_id)
                        print('Seal: {} returns to chat_id: {}'
                              .format(seal.seal_id, chat_data['id']))
                    else:
                        print('Seal: {} CANNOT return to chat_id: {} CUZ he never left it!'
                              .format(seal.seal_id, chat_data['id']))
                    stop = True
                    break
            if stop:
                break
            start_from += chat_num

        except Exception as e:
            print('on_join_chat_cmd, exception occurred: {}'.format(e))
            traceback.print_exc()
            break

    channel.basic_ack(delivery_tag=method.delivery_tag)


def on_quit_chat_cmd(channel, method, header, body):
    """Accepts quit-chat command from other seals."""

    print("on_quit_chat_cmd, body - {}, header - {}, method - {}".format(body, header, method))

    # TODO: unused slot???

    channel.basic_ack(delivery_tag=method.delivery_tag)


# signal: slot (from manager to seal)
MANAGER_TO_SEAL_SLOT_MAP = {
    ADD_FRIEND_CMD: on_add_friend_cmd,
    STOP_SEAL_CMD: on_stop_seal_cmd,
    REPLACE_IN_CHAT_CMD: on_replace_in_chat_cmd,
    CONNECT_TO_SEALS_CMD: on_connect_to_seals_cmd
}

SEAL_TO_SEAL_SLOT_MAP = {
    JOIN_CHAT_CMD: on_join_chat_cmd,
    QUIT_CHAT_CMD: on_quit_chat_cmd
}


# slots:        --------------------------------------------------------------------------------------------------------


# vk_api:       --------------------------------------------------------------------------------------------------------
def try_pull_args(stats, skip=True):
    try:
        if skip:
            return '{Skipped}'
        return ''.join(stats.args)
    except Exception as e:
        print('\ttry_pull_args exception: {}'.format(e))
        return '{None}'


def send_action_stats(seal):
    print('send_action_stats for seal_id: {}'.format(seal.seal_id))

    message = ""
    times = 0
    dialog_list = seal.vk_user.get_dialogs()
    chat_count = len([dialog['message']['chat_id'] for dialog in dialog_list if 'chat_id' in dialog['message']])
    for action_name, stats in seal.vk_user.action_stats.items():
        if isinstance(stats, VkUserStatsAction):
            if stats.times > 0:
                message += SEND_STATS_MSG_format.format(seal.seal_id,
                                                        action_name,
                                                        stats.times,
                                                        action_name in LOAD_BALANCED_ACTIONS,
                                                        chat_count,
                                                        try_pull_args(stats) + '\n')
                print('\taction stats message: {}'.format(message))
                times += stats.times

    if not len(message) or not times:
        print('send_action_stats: message is empty!')
        return
    seal.publish_message_to_manager(SEND_STATS_MSG, message)
    seal.vk_user.action_stats.clear()


def prepare_vk_user(config, test_mode, run_mode, only_for_uid):
    vk_user = VkUser(config, test_mode, run_mode, only_for_uid)

    logger.info("Created user api")
    logger.info("Starting processing... ")

    return vk_user


def process_vk_messages(vk_user):
    try:
        msg = vk_user.poll_messages()
        vk_user.process_messages(msg)
    except Exception as e:
        msg = "Something wrong while processing vk messages: {}".format(e)
        logger.exception(msg)
        traceback.print_exc()
        seal.publish_message_to_manager(SEAL_EXCEPTION_OCCURRED_MSG,
                                        SEAL_EXCEPTION_OCCURRED_MSG_format.format(seal.seal_id, msg))


# vk_api:       --------------------------------------------------------------------------------------------------------


@IterCounter.step_counter
def process_step(iter_counter, seal, to_sleep=None):
    if to_sleep:
        time.sleep(to_sleep)
    seal.receive_signals()

    process_vk_messages(seal.vk_user)

    if iter_counter.counter % 10 == 0:
        send_action_stats(seal)

    print("*** process_step ---> seal's processing messages ...")


def try_save_config(config, config_file_name):
    try:
        with open(config_file_name, 'w') as outfile:
            yaml.dump(config, outfile, default_flow_style=False)
    except Exception as e:
        print('unable to save config file: {}, exception: {}'.format(config_file_name, e))


def process(config, config_file_name, run_mode, test_mode, only_for_uid):
    seal_id = config['access_token']['user_id']

    print("SealAccountManager process started for config_file: {} and seal_id: {}".format(config_file_name, seal_id))

    global seal
    seal = SealAccountManager(seal_id, run_mode)
    seal.bind_slots(MANAGER_NAME, seal_id, MANAGER_TO_SEAL_SLOT_MAP)

    iter_counter = IterCounter(max_count=random.randint(30, 50), raise_exception=False)

    with prepare_vk_user(config, test_mode, run_mode, only_for_uid) as vk_user:
        seal.vk_user = vk_user
        while True:
            try:
                process_step(iter_counter, seal)
            except SealManagerException as e:
                print(e)
                break
            except Exception as e:
                print('exception occurred in seal process: {}'.format(e))
                traceback.print_exc()
                seal.publish_message_to_manager(SEAL_EXCEPTION_OCCURRED_MSG,
                                                SEAL_EXCEPTION_OCCURRED_MSG_format.format(seal.seal_id, e))
                break

    # try_save_config(config, config_file_name)
    print("SealAccountManager process finished...")


def main():
    parser = argparse.ArgumentParser(description='Seal - neat vk_bot')
    parser.add_argument('-c', '--config', dest='config', metavar='FILE.yaml',
                        help='configuration file to use', default='access.yaml')
    parser.add_argument('-m', '--mode', dest='run_mode', metavar='run_mode_name',
                        help="run mode for seal", default='standalone')
    parser.add_argument("-t", "--test", dest="test_mode",
                        help="test mode", action="store_true", default=False)
    parser.add_argument("-o", "--only_for_uid", dest="only_for_uid",
                        help="work only with master's messages")

    args = parser.parse_args()
    print("************* SealAccountManager - vk.com bot ****************")

    config = yaml.load(open(args.config))

    print("Loaded configuration ")
    print(yaml.dump(config))

    process(config, args.config, args.run_mode, args.test_mode, args.only_for_uid)


if __name__ == '__main__':
    print('seal.py main func called')
    main()
