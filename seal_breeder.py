#!/usr/bin/python
# -*- coding: utf-8 -*-

import yaml
import argparse
import subprocess

from seal_management import *
import time


class BreederMode:
    def __init__(self):
        pass

    NoMode = 'nomode'
    TestMode = 'test_mode'


class SealBreeder:
    def __init__(self):
        self.seals = {}
        self.SEALS_PROCESSES = []
        self.listener_connection = setup_amqp_channel_()
        self.publisher_connection = None

    def __enter__(self):
        print('SealBreeder.__enter__')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('SealBreeder.__exit__')

    def get_seals(self):
        return self.seals

    def register_seal(self, seal_id, seal_process):
        self.seals[seal_id] = seal_process

    def publish_message(self, seal_id, signal, message=''):
        with setup_amqp_channel_() as self.publisher_connection:
            routing_key = '{}.{}.{}'.format(signal, 'manager', seal_id)
            if not message:
                message = 'signal:{} from manager to seal:{}'.format(signal, seal_id)
            publish_message_(self.publisher_connection.channel(), routing_key, message)

    def bind_slots(self):
        slot_map = {}
        for queue_name, slot in MANAGER_SIGNAL_SLOT_MAP.items():
            for seal_id in self.seals:
                routing_key = '{}.{}.{}'.format(queue_name, seal_id, 'manager')
                slot_map[routing_key] = slot
        bind_slots_(self.listener_connection.channel(), slot_map)

    def receive_signals(self):
        for queue_name in MANAGER_SIGNAL_SLOT_MAP:
            receive_signals_(self.listener_connection.channel(), queue_name)

    def finish_seals(self):
        print('seal_breeder, finish_seals called')

        for seal_id in self.seals:
            self.publish_message(seal_id, STOP_SEAL_CMD)
        exit_codes = [p.wait(10) for p in self.seals.values()]

        print('all seals finished with codes: {}'.format(exit_codes))


seal_breeder = SealBreeder()


# slots:        --------------------------------------------------------------------------------------------------------
def on_solve_captcha_request(channel, method, header, body):
    """Accepts solve-captcha command from seal."""

    print("on_solve_captcha_request, body - {}, header - {}, method - {}".format(body, header, method))

    channel.basic_ack(delivery_tag=method.delivery_tag)

# exchange(signal) - slot (from seal to manager)
MANAGER_SIGNAL_SLOT_MAP = {SOLVE_CAPTCHA_REQ: on_solve_captcha_request}

# slots:        --------------------------------------------------------------------------------------------------------


def process(config, mode):
    config_files = config['list_of_config_files']
    iter_counter = IterCounter(max_count=15, raise_exception=(mode == BreederMode.TestMode))

    for config_file in config_files:
        print(config_file)

        seal_config = yaml.load(open(config_file))
        seal_id = seal_config['access_token']['user_id']

        # TODO: where we put output???
        log_file = str(config_file) + '.out'
        rem_file(log_file)
        proc = subprocess.Popen('python3 seal.py -c ' + str(config_file) + ' -m breeder > ' + log_file, shell=True)
        seal_breeder.register_seal(seal_id, proc)

    seal_breeder.bind_slots()

    while True:
        try:
            time.sleep(0.2)
            print("* manager is running *")

            for i in range(10):
                seal_breeder.receive_signals()

            for seal_id in seal_breeder.get_seals():
                for i in range(5):
                    time.sleep(0.01)
                    seal_breeder.publish_message(seal_id, ADD_FRIEND_CMD,
                                                 'signal:{} from manager to seal:{} with #{}'
                                                 .format(ADD_FRIEND_CMD, seal_id, i))
                    time.sleep(0.01)
                    seal_breeder.publish_message(seal_id, JOIN_CHAT_CMD,
                                                 'signal:{} from manager to seal:{} with #{}'
                                                 .format(JOIN_CHAT_CMD, seal_id, i))

            print("* manager is getting messages...")
            iter_counter.count()
        except SealManagerException as e:
            print(e)
            print("* manager finishes in 5 sec...")
            seal_breeder.finish_seals()
            time.sleep(1)
            break
        except Exception as e:
            print('exception occurred in manager process: {}'.format(e))
            break

    print("Manager process finished...")


def main():
    parser = argparse.ArgumentParser(description='Seal breeder program')
    parser.add_argument('-c', '--config', dest='config', metavar='FILE.yaml',
                        help='configuration file to use', default='seal_breeder_default_config.yaml')
    parser.add_argument('-m', '--mode', dest='mode', metavar='mode_name',
                        help="run mode for seal breeder", default='nomode')

    args = parser.parse_args()
    print("************* Seal breeder - vk.com bot manager ****************")

    config = yaml.load(open(args.config))

    print("Loaded configuration ")
    print(yaml.dump(config))

    process(config, args.mode)


if __name__ == '__main__':
    main()
