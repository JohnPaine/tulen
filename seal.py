#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import logging.config
import random
import time
import uuid

import yaml
from parse import compile as parse_compile

from seal_management import *
from seal_management_utils import *
from vkuser import VkUser

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
    def __init__(self, seal_id, mode, group_spam_list=None):
        super().__init__(seal_id)
        self.mode = mode
        self.vk_user = None
        self.other_seals_ids = []
        self.group_spam_list = group_spam_list if group_spam_list else []

    def __enter__(self):
        print('SealAccountManager.__enter__')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('SealAccountManager.__exit__')

    # BaseAccountManager interface      ================================================================================
    def publish_message_to_seal(self, signal, receiver_id, message=''):
        super().publish_message(signal, receiver_id, message)

    def publish_message_to_manager(self, signal, message=''):
        super().publish_message(signal, MANAGER_NAME, message)

    # BaseAccountManager interface      ================================================================================

    # vk api            ================================================================================================
    def spam_group_invitations(self):
        friends = self.vk_user.get_friends()['items']
        group_id = random.choice(self.group_spam_list)
        group_members = self.vk_user.get_group_members(group_id)['items']
        user_id = random.choice(friends)

        if int(user_id) in group_members:
            print("spam_group_invitations, can't add user_id: {} to group_id: {} - he's already in group!"
                  .format(user_id, group_id))
            return None

        return self.vk_user.send_group_invitation(random.choice(self.group_spam_list), random.choice(friends))

    def add_group_member_friend(self):
        friends = self.vk_user.get_friends()['items']
        group_id = random.choice(self.group_spam_list)
        group_members = self.vk_user.get_group_members(group_id)['items']
        user_id = random.choice(group_members)

        if int(user_id) in friends:
            print("add_group_member_friend, can't add user_id: {} as friend - he's already a friend!".format(user_id))
            return None

        if self.vk_user.friendAdd(user_id):
            print("add_group_member_friend, sent a friend request for user_id{}".format(user_id))
            return self.vk_user.pixelsort_and_post_on_wall(user_id)
        return None

    # vk api            ================================================================================================


seal = None
# amqp management receiver id for check_routing decorator
current_receiver_id = None


# amqp management       ================================================================================================


# slots:        --------------------------------------------------------------------------------------------------------
def on_add_friend_cmd(method, header, body):
    """Accepts add-friend command from manager."""

    print("on_add_friend_cmd, body - {}, header - {}, method - {}".format(body, header, method))


def on_replace_in_chat_cmd(method, header, body):
    """Accepts replace-in-chat command from manager."""

    print("on_replace_in_chat_cmd, body: {},\n\theader: {},\n\tmethod: {}".format(body, header, method))

    cmd_parser = parse_compile(REPLACE_IN_CHAT_CMD_format)
    parsed = cmd_parser.parse(body.decode('utf-8'))

    replacing_seal_id = int(parsed[0])
    chat_id = int(parsed[1])
    chat_num = int(parsed[2])

    def replace_in_chat(_chat_id):
        nonlocal chat_num

        print('seal, replace_in_chat, chat_id:{}. replacing_seal_id:{}'.format(_chat_id, replacing_seal_id))

        users = seal.vk_user.get_chat_users(_chat_id)
        print('\tseal.vk_user.get_chat_users, users: {}'.format(users))

        if int(replacing_seal_id) in users:
            print('\tCAN\'T replace seal_id:{} with replacing_seal_id:{} in chat_id:{} - he\'s already in chat!'
                  .format(seal.receiver_id, replacing_seal_id, _chat_id))
        else:
            print('\ttrying to replace THIS seal_id:{} with replacing_seal_id:{} in chat_id:{}'
                  .format(seal.receiver_id, replacing_seal_id, _chat_id))
            try:
                seal.vk_user.add_chat_user(int(_chat_id), int(replacing_seal_id))

                # TODO: send message to chat about this switch... -

                chat_data = seal.vk_user.get_chat(_chat_id)
                print('\t\treplace_in_chat, chat_data: {}'.format(chat_data))

                encoded_chat_title = chat_data['title'].encode('cp1251')
                print('\t\treplace_in_chat, encoded_chat_title: {}'.format(encoded_chat_title))

                seal.publish_message_to_seal(JOIN_CHAT_CMD,
                                             replacing_seal_id,
                                             JOIN_CHAT_CMD_format.format(encoded_chat_title,
                                                                         chat_data['admin_id'],
                                                                         seal.receiver_id,
                                                                         replacing_seal_id))
                seal.vk_user.remove_chat_user(int(_chat_id), seal.receiver_id)
                chat_num -= 1

            except Exception as e:
                print('Exception: {},\n\t...occurred in replacing THIS seal_id: {} with seal: {} in chat_id: {}'
                      .format(e, seal.receiver_id, replacing_seal_id, _chat_id))
                chat_num -= 1

    if chat_id > 0:
        replace_in_chat(chat_id)
    else:
        dialog_list = seal.vk_user.get_dialogs()

        for dialog in dialog_list:
            if chat_num <= 0:
                break

            message = dialog['message']
            if 'chat_id' not in message:
                continue

            current_chat_id = message['chat_id']

            replace_in_chat(current_chat_id)

    # print('\tdialog_list: {}'.format(json.dumps(dialog_list, indent=4)))


def on_stop_seal_cmd(method, header, body):
    """Accepts stop-seal command from manager."""

    print("on_stop_seal_cmd, body: {},\n\theader: {},\n\tmethod: {}".format(body, header, method))

    if seal:
        raise SealManagerException('SealAccountManager {} received stop_signal from manager - stopping...'
                                   .format(seal.receiver_id))


def on_connect_to_seals_cmd(method, header, body):
    """Accepts connect-to-seals messages from manager."""

    print("on_connect_to_seals_cmd, body - {},\n\theader - {},\n\tmethod - {}".format(body, header, method))

    cmd_parser = parse_compile(CONNECT_TO_SEALS_CMD_format)
    parsed = cmd_parser.parse(body.decode('utf-8'))

    if not parsed[0]:
        return

    seal_ids = parsed[0].split(',')
    print('\t\t\tseal_ids:{}'.format(seal_ids))
    seal.other_seals_ids = seal_ids

    for _seal_id in seal_ids:
        if int(_seal_id) == int(seal.receiver_id):
            continue
        # seal.bind_slots(_seal_id, seal.receiver_id, SEAL_TO_SEAL_SLOT_MAP)
        # TODO: TMP! Test message
        seal.publish_message_to_seal(QUIT_CHAT_CMD,
                                     _seal_id,
                                     uuid.uuid4().hex)


def on_join_chat_cmd(method, header, body):
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

    if str(replacing_seal_id) != str(seal.receiver_id):
        raise SealManagerException('on_join_chat_cmd, replacing_seal_id: {} != THIS seal_id: {}'
                                   .format(replacing_seal_id, seal.receiver_id))

    print('\ton_join_chat_cmd, chat_title: {}, admin_id: {}'.format(chat_title, admin_id))

    for chat_data in seal.vk_user.get_chats_data().values():
        if chat_title == chat_data['title'] and admin_id == chat_data['admin_id']:
            if 'left' in chat_data and int(chat_data['left']) == 1:
                seal.vk_user.add_chat_user(int(chat_data['id']), int(seal.receiver_id))
                print('Seal: {} returns to chat_id: {}'
                      .format(seal.receiver_id, chat_data['id']))
            else:
                print('Seal: {} CANNOT return to chat_id: {} CUZ he never left it!'
                      .format(seal.receiver_id, chat_data['id']))
            break


def on_quit_chat_cmd(method, header, body):
    """Accepts quit-chat command from other seals."""

    print("on_quit_chat_cmd, body - {}, header - {}, method - {}".format(body, header, method))

    # TODO: unused slot???


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

SLOT_DICT = {**MANAGER_TO_SEAL_SLOT_MAP, **SEAL_TO_SEAL_SLOT_MAP}


@check_routing()
def seal_main_slot(channel, method, header, body):
    """Accepts ALL the commands from seals and manager."""

    # print("seal_main_slot, body: {},\n\theader: {},\n\tmethod: {}".format(body, header, method))
    print("\nON_seal_main_slot, routing_key: {}\n\n".format(method.routing_key))

    signal = method.routing_key.split('.')[0]

    if signal in SLOT_DICT:
        SLOT_DICT[signal](method, header, body)
    else:
        print('\ndispatch_slot error: no signal: {} in slot_dict: {}'.format(signal, SLOT_DICT))

    channel.basic_ack(delivery_tag=method.delivery_tag)

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


def send_action_stats():
    print('send_action_stats for seal_id: {}'.format(seal.receiver_id))

    message = ""
    times = 0
    dialog_list = seal.vk_user.get_dialogs()
    chat_count = len([dialog['message']['chat_id'] for dialog in dialog_list if 'chat_id' in dialog['message']])
    for action_name, stats in seal.vk_user.action_stats.items():
        if isinstance(stats, VkUserStatsAction):
            if stats.times > 0:
                message += SEND_STATS_MSG_format.format(seal.receiver_id,
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
                                        SEAL_EXCEPTION_OCCURRED_MSG_format.format(seal.receiver_id, msg))


# vk_api:       --------------------------------------------------------------------------------------------------------


@IterCounter.step_counter
def process_step(iter_counter, to_sleep=None):
    global seal

    try:
        if to_sleep:
            time.sleep(to_sleep)
        seal.try_process(seal.consume_messages)

        if iter_counter.counter % 20 == 0:
            seal.try_process(send_action_stats)

        if iter_counter.counter % random.randint(700, 1200) == 0:
            seal.try_process(seal.spam_group_invitations)

        if iter_counter.counter % random.randint(400, 600) == 0:
            seal.try_process(seal.add_group_member_friend)

        seal.try_process(process_vk_messages, seal.vk_user)

        print("*** process_step ---> seal's processing messages ...")
    except Exception as e:
        msg = 'Something went wrong while processing step for seal: {}, e: {}'.format(seal.receiver_id, e)
        logger.exception(msg)
        traceback.print_exc()
        seal.publish_message_to_manager(SEAL_EXCEPTION_OCCURRED_MSG,
                                        SEAL_EXCEPTION_OCCURRED_MSG_format.format(seal.receiver_id, msg))


def try_save_config(config, config_file_name):
    try:
        with open(config_file_name, 'w') as outfile:
            yaml.dump(config, outfile, default_flow_style=False)
    except Exception as e:
        print('unable to save config file: {}, exception: {}'.format(config_file_name, e))


def process(config, config_file_name, run_mode, test_mode, only_for_uid):
    seal_id = config['access_token']['user_id']

    print("SealAccountManager process started for config_file: {} and seal_id: {}".format(config_file_name, seal_id))

    global seal, current_receiver_id
    seal = SealAccountManager(seal_id, run_mode, config.get('group_spam_list', None))
    current_receiver_id = seal_id
    iter_counter = IterCounter(max_count=random.randint(30, 50), raise_exception=False)

    seal.bind_slot(MANAGER_NAME, list(MANAGER_TO_SEAL_SLOT_MAP.keys()), seal_main_slot)
    seal.bind_slot('*', list(SEAL_TO_SEAL_SLOT_MAP.keys()), seal_main_slot)

    with prepare_vk_user(config, test_mode, run_mode, only_for_uid) as vk_user:
        seal.vk_user = vk_user
        while True:
            try:
                process_step(iter_counter)

            except SealManagerException as e:
                print(e)
                traceback.print_exc()
                break
            except Exception as e:
                print('exception occurred in seal process: {}'.format(e))
                traceback.print_exc()
                seal.publish_message_to_manager(SEAL_EXCEPTION_OCCURRED_MSG,
                                                SEAL_EXCEPTION_OCCURRED_MSG_format.format(seal.receiver_id, e))

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
