#!/usr/bin/python
# -*- coding: utf-8 -*-

import yaml
import time
import argparse
from seal_account_manager import *
import logging.config
from vkuser import VkUser
import random

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


seal = None


# slots:        --------------------------------------------------------------------------------------------------------
def on_add_friend_cmd(channel, method, header, body):
    """Accepts add-friend command from manager."""

    print("on_add_friend_cmd, body - {}, header - {}, method - {}".format(body, header, method))

    channel.basic_ack(delivery_tag=method.delivery_tag)


def on_join_chat_cmd(channel, method, header, body):
    """Accepts join-chat command from manager."""

    print("on_join_chat_cmd, body - {}, header - {}, method - {}".format(body, header, method))

    channel.basic_ack(delivery_tag=method.delivery_tag)


def on_stop_seal_cmd(channel, method, header, body):
    """Accepts stop-seal command from manager."""

    print("on_stop_seal_cmd, body - {}, header - {}, method - {}".format(body, header, method))

    channel.basic_ack(delivery_tag=method.delivery_tag)
    if seal:
        raise SealManagerException('SealAccountManager {} received stop_signal from manager - stopping...'
                                   .format(seal.get_seal_id()))


# signal - slot (from manager to seal)
SEAL_SIGNAL_SLOT_MAP = {ADD_FRIEND_CMD: on_add_friend_cmd,
                        JOIN_CHAT_CMD: on_join_chat_cmd,
                        STOP_SEAL_CMD: on_stop_seal_cmd}

# slots:        --------------------------------------------------------------------------------------------------------


# vk_api:       --------------------------------------------------------------------------------------------------------
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
        logger.exception("Something wrong while processing vk messages: {}".format(e))
        if vk_user.test_mode:
            return False

    return True

# vk_api:       --------------------------------------------------------------------------------------------------------


@IterCounter.step_counter
def process_step(iter_counter, seal, vk_user, to_sleep=None):
    if to_sleep:
        time.sleep(to_sleep)
    seal.receive_signals()

    if not process_vk_messages(vk_user):
        return False

    print("*** process_step ---> seal's processing messages ...")
    return True


def process(config, run_mode, test_mode, only_for_uid):
    print("SealAccountManager process started...")

    seal_id = config['access_token']['user_id']

    global seal
    seal = SealAccountManager(seal_id, run_mode, SEAL_SIGNAL_SLOT_MAP)
    seal.bind_slots()

    iter_counter = IterCounter(max_count=random.randint(30, 50), raise_exception=False)

    with prepare_vk_user(config, test_mode, run_mode, only_for_uid) as vk_user:
        while True:
            try:
                if not process_step(iter_counter, seal, vk_user):
                    break
            except SealManagerException as e:
                print(e)
                break
            except Exception as e:
                print('exception occurred in seal process: {}'.format(e))
                break

    print("SealAccountManager process finished...")


def main():
    parser = argparse.ArgumentParser(description='SealAccountManager breeder program')
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

    process(config, args.run_mode, args.test_mode, args.only_for_uid)


if __name__ == '__main__':
    print('seal.py main func called')
    main()
