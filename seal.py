#!/usr/bin/python
# -*- coding: utf-8 -*-

import yaml
import time
import argparse
from seal_management import *


class SealMode:
    def __init__(self):
        pass

    Standalone = 'standalone'
    TestMode = 'test_mode'
    Breeder = 'breeder'


class Seal:
    def __init__(self, seal_id):
        self.seal_id = seal_id
        self.listener_connection = setup_amqp_channel_()
        self.publisher_connection = None

    def __enter__(self):
        print('Seal.__enter__')
        # self.publisher_channel, self.publisher_connection = setup_amqp_channel_()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('Seal.__exit__')
        if self.publisher_connection:
            self.publisher_connection.close()
            self.publisher_connection = None

    def get_seal_id(self):
        return self.seal_id

    def publish_message(self, signal, message=''):
        if self.publisher_connection:
            self.publisher_connection.close()
        self.publisher_connection = setup_amqp_channel_()

        routing_key = '{}.{}.{}'.format(signal, self.seal_id, 'manager')
        if not message:
            message = 'signal:{} from seal:{} to manager'.format(signal, self.seal_id)
        publish_message_(self.publisher_connection.channel(), routing_key, message)

        self.publisher_connection.close()
        self.publisher_connection = None

    def bind_slots(self):
        slot_map = {}
        for queue_name, slot in SEAL_SIGNAL_SLOT_MAP.items():
            routing_key = '{}.{}.{}'.format(queue_name, 'manager', self.seal_id)
            slot_map[routing_key] = slot
        bind_slots_(self.listener_connection.channel(), slot_map)

    def receive_signals(self):
        for queue_name in SEAL_SIGNAL_SLOT_MAP:
            receive_signals_(self.listener_connection.channel(), queue_name)


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
        raise SealManagerException('Seal {} received stop_signal from manager - stopping...'.format(seal.get_seal_id()))


# exchange(signal) - slot (from manager to seal)
SEAL_SIGNAL_SLOT_MAP = {ADD_FRIEND_CMD: on_add_friend_cmd,
                        JOIN_CHAT_CMD: on_join_chat_cmd,
                        STOP_SEAL_CMD: on_stop_seal_cmd}


# slots:        --------------------------------------------------------------------------------------------------------


def process(config, mode):
    print("Seal process started...")

    seal_id = config['access_token']['user_id']
    global seal
    seal = Seal(seal_id)

    if mode == SealMode.Breeder:
        print('Seal started from seal_breeder - connecting slots...')

        seal.bind_slots()

    while True:
        try:
            time.sleep(0.1)

            if mode == SealMode.Breeder:
                print('seal receiving signals...')
                for i in range(10):
                    seal.receive_signals()

                seal.publish_message(SOLVE_CAPTCHA_REQ,
                                     "seal -> manager: solve captcha for seal with id {}".format(seal.get_seal_id()))

            print("* seal's processing messages ...")
        except SealManagerException as e:
            print(e)
            break
        except Exception as e:
            print('exception occurred in seal process: {}'.format(e))
            break

    print("Seal process finished...")


def main():
    parser = argparse.ArgumentParser(description='Seal breeder program')
    parser.add_argument('-c', '--config', dest='config', metavar='FILE.yaml',
                        help='configuration file to use', default='access.yaml')
    parser.add_argument('-m', '--mode', dest='mode', metavar='mode_name',
                        help="run mode for seal", default='standalone')

    args = parser.parse_args()
    print("************* Seal - vk.com bot ****************")

    config = yaml.load(open(args.config))

    print("Loaded configuration ")
    print(yaml.dump(config))

    process(config, args.mode)


if __name__ == '__main__':
    print('seal.pt main func called')
    main()
