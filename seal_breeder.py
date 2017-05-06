#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
from seal_breeder_account_manager import *
import time
from parse import compile as parse_compile


# slots:        --------------------------------------------------------------------------------------------------------
def on_solve_captcha_request(channel, method, header, body):
    """Accepts solve-captcha request from seal."""

    print("on_solve_captcha_request, body - {}, header - {}, method - {}".format(body, header, method))

    channel.basic_ack(delivery_tag=method.delivery_tag)


def on_send_stats_message(channel, method, header, body):
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

        seal = seal_breeder.get_seals().get(int(parsed[0]))

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

    channel.basic_ack(delivery_tag=method.delivery_tag)


def on_seal_exception_message(channel, method, header, body):
    """Accepts seal-exception message from seal."""

    print("on_seal_exception_message, body - {}, header - {}, method - {}".format(body, header, method))

    channel.basic_ack(delivery_tag=method.delivery_tag)


# exchange(signal) - slot (from seal to manager)
MANAGER_SIGNAL_SLOT_MAP = {SOLVE_CAPTCHA_REQ: on_solve_captcha_request,
                           SEND_STATS_MSG: on_send_stats_message,
                           SEAL_EXCEPTION_OCCURRED_MSG: on_seal_exception_message}

# slots:        --------------------------------------------------------------------------------------------------------


seal_breeder = SealBreeder(MANAGER_SIGNAL_SLOT_MAP)


@IterCounter.step_counter
def process_step(iter_counter, breeder):
    time.sleep(1.0)
    breeder.receive_signals()

    if iter_counter.counter % 20 == 0:
        breeder.check_alive()
        breeder.balance_seals()


def process(config, mode):
    config_files = config['list_of_config_files']
    iter_counter = IterCounter(max_count=200, raise_exception=False)

    seal_breeder.start_seals(config_files, mode)
    seal_breeder.bind_slots()

    while True:
        try:
            process_step(iter_counter, seal_breeder)

            # TODO:
            # 1. Seal running checks - DONE
            # 2. Statistics - DONE
            # 3. Logging errors/exception in seal breeder - DONE
            # 4. join/leave chat

        except SealManagerException as e:
            print(e)
            print("* manager finishes in 5 sec...")
            seal_breeder.finish_seals()
            time.sleep(1)
            break
        except Exception as e:
            print('exception occurred in manager process: {}'.format(e))
            seal_breeder.finish_seals()
            time.sleep(1)
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
