#!/usr/bin/python
# -*- coding: utf-8 -*-

import yaml
import argparse
import subprocess

from seal_management import *
import time


# slots:        --------------------------------------------------------------------------------------------------------
def on_solve_captcha_request(channel, method, header, body):
    """Accepts solve-captcha command from seal."""

    print("on_solve_captcha_request, body - {}, header - {}, method - {}".format(body, header, method))

    channel.basic_ack(delivery_tag=method.delivery_tag)

# exchange(signal) - slot (from seal to manager)
MANAGER_SIGNAL_SLOT_MAP = {SOLVE_CAPTCHA_REQ: on_solve_captcha_request}

# slots:        --------------------------------------------------------------------------------------------------------


class BreederMode:
    def __init__(self):
        pass

    NoMode = 'nomode'
    TestMode = 'test_mode'


class SealBreeder(BaseAccountManager):
    def __init__(self, slot_map):
        super().__init__(slot_map)
        self.seals = {}
        self.SEALS_PROCESSES = []

    def __enter__(self):
        print('SealBreeder.__enter__')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('SealBreeder.__exit__')

    def get_seals(self):
        return self.seals

    def register_seal(self, seal_id, seal_process):
        self.seals[seal_id] = seal_process

    def make_signal_routing_key(self, signal, manager='manager', seal_id=None):
        return '{}.{}.{}'.format(signal, manager, seal_id)

    def make_slot_routing_key(self, queue_name, manager='manager', seal_id=None):
        return '{}.{}.{}'.format(queue_name, seal_id, manager)

    def make_message(self, signal, manager='manager', seal_id=None):
        return 'signal:{} from {} to seal:{}'.format(signal, manager, seal_id)

    def publish_message(self, signal, message='', seal_id=None, manager='manager'):
        print('Seal breeder publishing message for signal: {}, seal_id: {}, message: {}'.format(signal, seal_id, message))
        super().publish_message(signal, message, seal_id, manager)

    def bind_slots(self, seal_id=None, manager='manager'):
        print('binding slots for seal_breeder...')
        for seal_id in self.seals:
            super().bind_slots(seal_id)

    def finish_seals(self):
        try:
            print('seal_breeder, finish_seals called')

            for seal_id in self.seals:
                self.publish_message(STOP_SEAL_CMD, seal_id=seal_id)
            exit_codes = [p.wait(10) for p in self.seals.values()]

            print('all seals finished with codes: {}'.format(exit_codes))
        except Exception as e:
            print('Exception occurred while finishing seals: {}'.format(e))

    def start_seals(self, config_files, mode):
        for config_file in config_files:
            print(config_file)

            seal_config = yaml.load(open(config_file))
            seal_id = seal_config['access_token']['user_id']

            # TODO: where we put output???
            log_file = str(config_file) + '.out'
            rem_file(log_file)
            proc = subprocess.Popen('python3 seal.py -c ' + str(config_file) +
                                    ' -m breeder {}> '.format('-t ' if mode == BreederMode.TestMode else '')
                                    + log_file,
                                    shell=True)
            self.register_seal(seal_id, proc)


seal_breeder = SealBreeder(MANAGER_SIGNAL_SLOT_MAP)


def process(config, mode):
    config_files = config['list_of_config_files']
    iter_counter = IterCounter(max_count=200, raise_exception=False)

    seal_breeder.start_seals(config_files, mode)
    seal_breeder.bind_slots()

    while True:
        try:
            time.sleep(1.0)
            # print("* manager is running *")

            seal_breeder.receive_signals()

            print('seal_breeder iter counter: {}'.format(iter_counter.counter))

            # for seal_id in seal_breeder.get_seals():
            #     for i in range(5):
            #         time.sleep(0.01)
            #         seal_breeder.publish_message(ADD_FRIEND_CMD,
            #                                      'signal:{} from manager to seal:{} with #{}'
            #                                      .format(ADD_FRIEND_CMD, seal_id, i),
            #                                      seal_id)

                # seal_breeder.publish_message(seal_id, STOP_SEAL_CMD)
            #         time.sleep(0.01)
            #         seal_breeder.publish_message(seal_id, JOIN_CHAT_CMD,
            #                                      'signal:{} from manager to seal:{} with #{}'
            #                                      .format(JOIN_CHAT_CMD, seal_id, i))

            # print("* manager is getting messages...")
            iter_counter.count()
        except SealManagerException as e:
            print(e)
            print("* manager finishes in 5 sec...")
            seal_breeder.finish_seals()
            time.sleep(1)
            break
        # except Exception as e:
        #     print('exception occurred in manager process: {}'.format(e))
        #     break

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
