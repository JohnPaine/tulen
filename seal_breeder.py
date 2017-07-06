#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import logging.config
import time

from parse import compile as parse_compile

from seal_breeder_account_manager import *
from seal_management_utils import *

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
        'seal_breeder': {
            'level': 'DEBUG',
            'handlers': ['console', ]
        },
    }
}

logging.config.dictConfig(LOG_SETTINGS)
logger = logging.getLogger("seal_breeder")


# logging:      --------------------------------------------------------------------------------------------------------


# slots:        --------------------------------------------------------------------------------------------------------
def on_solve_captcha_request(method, header, body):
    """Accepts solve-captcha request from seal."""

    print("on_solve_captcha_request, body - {}, header - {}, method - {}".format(body, header, method))


def on_send_stats_message(method, header, body):
    """Accepts send-stats message from seal."""

    print("on_send_stats_message, body - {}, header - {}, method - {}".format(body, header, method))

    stats_parser = parse_compile(SEND_STATS_MSG_format)

    stats_messages = body.splitlines()
    for message in stats_messages:
        decoded_message = message.decode('utf-8')
        print('\ton_send_stats_message message: {}'.format(decoded_message))

        parsed = stats_parser.parse(decoded_message)

        if not parsed:
            continue

        seal = seal_breeder.seals.get(int(parsed[0]))

        if not seal:
            print('seal is None!!!')
            continue
        print('\tcollecting stats for seal: {}'.format(seal))

        action_name = parsed[1]
        times = int(parsed[2])
        load_balancing = bool(parsed[3])
        chat_count = int(parsed[4])

        seal.action_stats[action_name] += times
        seal.chat_count = chat_count
        if load_balancing:
            seal.lb_action_stats[action_name] += times


def on_seal_exception_message(method, header, body):
    """Accepts seal-exception message from seal."""

    print("on_seal_exception_message, body: {},\n\theader: {},\n\tmethod: {}".format(body, header, method))


# exchange(signal) - slot (from seal to manager)
SEALS_TO_MANAGER_SLOT_MAP = {SOLVE_CAPTCHA_REQ: on_solve_captcha_request,
                             SEND_STATS_MSG: on_send_stats_message,
                             SEAL_EXCEPTION_OCCURRED_MSG: on_seal_exception_message}


@check_routing()
def seal_breeder_main_slot(channel, method, header, body):
    """Accepts ALL the messages from seals."""

    print("seal_breeder_main_slot, routing_key: {}\n".format(method.routing_key))

    signal = method.routing_key.split('.')[0]

    if signal in SEALS_TO_MANAGER_SLOT_MAP:
        SEALS_TO_MANAGER_SLOT_MAP[signal](method, header, body)
    else:
        print('\ndispatch_slot error: no signal: {} in slot_dict: {}'.format(signal, SEALS_TO_MANAGER_SLOT_MAP))

    channel.basic_ack(delivery_tag=method.delivery_tag)

# slots:        --------------------------------------------------------------------------------------------------------


seal_breeder = SealBreeder()
# global receiver_id for amqp management
current_receiver_id = seal_breeder.receiver_id


@IterCounter.step_counter
def process_step(iter_counter, time_to_sleep=1.0):
    try:
        time.sleep(time_to_sleep)
        seal_breeder.try_process(seal_breeder.consume_messages)

        if iter_counter.counter % 20 == 0:
            seal_breeder.try_process(seal_breeder.check_alive)

        if iter_counter.counter % 300 == 0:
            seal_breeder.try_process(seal_breeder.balance_seals_for_chats)

        if iter_counter.counter % random.randint(300, 600) == 0:
            seal_breeder.try_process(seal_breeder.share_friends)

    except Exception as e:
        msg = 'Something went wrong while processing step for seal_breeder, e: {}'.format(e)
        logger.exception(msg)
        traceback.print_exc()


def process(config, mode):
    config_files = config['list_of_config_files']
    iter_counter = IterCounter(MANAGER_NAME, max_count=200, raise_exception=False)

    seal_breeder.start_seals(config_files, mode)
    seal_breeder.friends_sharing_uids = config['friends_sharing_uids']
    seal_breeder.bind_slot('*', list(SEALS_TO_MANAGER_SLOT_MAP.keys()), seal_breeder_main_slot)

    time.sleep(2)
    for seal_id in seal_breeder.seals:
        seal_breeder.send_connect_to_seals_cmd(seal_id)

    while True:
        try:
            process_step(iter_counter)

        except SealManagerException as e:
            print(e)
            print("* manager finishes in 5 sec...")
            seal_breeder.finish_seals()
            time.sleep(1)
            traceback.print_exc()
            break
        except Exception as e:
            print('exception occurred in manager process: {}'.format(e))
            seal_breeder.finish_seals()
            time.sleep(1)
            traceback.print_exc()
            raise

    print("Manager process finished...")


def main():
    parser = argparse.ArgumentParser(description='SealAccountManager breeder program')
    parser.add_argument('-c', '--config', dest='config', metavar='FILE.yaml',
                        help='configuration file to use', default='seal_breeder_default_config.yaml')
    parser.add_argument('-m', '--mode', dest='mode', metavar='mode_name',
                        help="run mode for seal breeder", default='nomode')

    args = parser.parse_args()
    print("************* SealAccountManager breeder - vk.com bot manager ****************")

    config = yaml.load(open(args.config))

    print("Loaded configuration ")
    print(yaml.dump(config))

    process(config, args.mode)


if __name__ == '__main__':
    main()
