import subprocess
import yaml
from collections import namedtuple
from seal_management import *


class SealBreeder(BaseAccountManager):
    def __init__(self, slot_map):
        super().__init__(slot_map)
        self.seals = {}
        self.SEALS_PROCESSES = []
        self.mode = BreederMode.NoMode

    def __enter__(self):
        print('SealBreeder.__enter__')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('SealBreeder.__exit__')

    def get_seals(self):
        return self.seals

    def register_seal(self, seal_id, seal_process, config_file_name):
        SealConfig = namedtuple('SealConfig', ['seal_id', 'process', 'config_file_name'])
        self.seals[seal_id] = SealConfig(seal_id, seal_process, config_file_name)

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
        for seal_id in self.seals.keys():
            super().bind_slots(seal_id)

    def finish_seals(self):
        try:
            print('seal_breeder, finish_seals called')
            exit_codes = []
            for seal_config in self.seals.values():
                self.publish_message(STOP_SEAL_CMD, seal_id=seal_config.seal_id)
                exit_codes.append(seal_config.process.wait(10))

            print('all seals finished with codes: {}'.format(exit_codes))
        except Exception as e:
            print('Exception occurred while finishing seals: {}'.format(e))

    def start_seal_process(self, seal_id, config_file_name):
        print('starting seal process for seal_id: {} and config_file: {}'.format(seal_id, config_file_name))
        log_file_name = SealBreeder.prepare_log_file(config_file_name)

        seal_process = SealBreeder.start_seal(config_file_name, log_file_name, self.mode)
        self.register_seal(seal_id, seal_process, config_file_name)

    def check_alive(self):
        print('Seal breeder checking seals for running')
        for seal_id, seal_config in self.seals.items():
            if seal_config.process.poll() is None:
                continue

            self.start_seal_process(seal_id, seal_config.config_file_name)

    def start_seals(self, config_files, mode):
        self.mode = mode
        for config_file_name in config_files:
            seal_id, seal_config = SealBreeder.get_config(config_file_name)

            self.start_seal_process(seal_id, config_file_name)

    @staticmethod
    def get_seal_id(config_file):
        return config_file['access_token']['user_id']

    @staticmethod
    def get_config(config_file_name):
        print(config_file_name)

        seal_config = yaml.load(open(config_file_name))
        return SealBreeder.get_seal_id(seal_config), seal_config

    @staticmethod
    def prepare_log_file(config_file_name):
        # TODO: where we put output???
        log_file_name = str(config_file_name) + '.log'
        rem_file(log_file_name)
        return log_file_name

    @staticmethod
    def start_seal(config_file_name, log_file_name, mode):
        return subprocess.Popen('python3 seal.py -c {} -m breeder {}> {}'
                                .format(str(config_file_name),
                                        '-t ' if mode == BreederMode.TestMode else '',
                                        log_file_name),
                                shell=True)

