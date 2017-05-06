import subprocess
import yaml
from seal_management import *
from functools import reduce
from collections import defaultdict, OrderedDict
from operator import itemgetter


class SealConfig:
    def __init__(self, seal_id, seal_process, config_file_name, run_time):
        self.seal_id = seal_id
        self.process = seal_process
        self.config_file_name = config_file_name
        self.action_stats = defaultdict(int)
        # load-balancing actions
        self.lb_action_stats = defaultdict(int)
        self.chat_count = 0
        self.run_time = run_time


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

    def register_seal(self, seal_id, seal_process, config_file_name, run_time):
        self.seals[seal_id] = SealConfig(seal_id, seal_process, config_file_name, run_time)

    def make_signal_routing_key(self, signal, manager='manager', seal_id=None):
        return '{}.{}.{}'.format(signal, manager, seal_id)

    def make_slot_routing_key(self, queue_name, manager='manager', seal_id=None):
        return '{}.{}.{}'.format(queue_name, seal_id, manager)

    def make_message(self, signal, manager='manager', seal_id=None):
        return 'signal:{} from {} to seal:{}'.format(signal, manager, seal_id)

    def publish_message(self, signal, message='', seal_id=None, manager='manager'):
        print(
            'Seal breeder publishing message: {} for signal: {}, seal_id: {}'.format(message, signal, seal_id))
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
        run_time = 1
        if seal_id in self.seals:
            run_time = self.seals[seal_id].run_time + 1

        log_file_name = SealBreeder.prepare_log_file('./seal_logs', config_file_name, run_time)

        seal_process = SealBreeder.start_seal(config_file_name, log_file_name, self.mode)
        self.register_seal(seal_id, seal_process, config_file_name, run_time)

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
    def choose_seals_for_balancing(sorted_balancing_list):
        # TODO: choose some appropriate algorithm!!
        if len(sorted_balancing_list) < 2:
            return None, None
        return sorted_balancing_list[0], sorted_balancing_list[-1]

    def balance_seals(self):
        balancing_dict = {}
        for seal_id, seal_config in self.seals.items():
            if not len(seal_config.lb_action_stats):
                continue
            times_sum = reduce(lambda x, y: x + y,
                               [times for action, times in seal_config.lb_action_stats.items()])
            balancing_dict[seal_id] = times_sum

        sorted_balancing_list = [(key, value) for key, value in
                                 sorted(balancing_dict.items(), key=itemgetter(1), reverse=True)]
        print('sorted_balancing_list - {}'.format(sorted_balancing_list))

        replaceable_seal_stats, replacing_seal_stats = SealBreeder.choose_seals_for_balancing(sorted_balancing_list)
        print('\tBALANCING seals, replaceable: {}, replacing: {}'.format(replaceable_seal_stats, replacing_seal_stats))
        if not replaceable_seal_stats or not replacing_seal_stats:
            print('\tunable to choose seals for balancing')
            return
        replace_cmd = REPLACE_IN_CHAT_CMD_format.format(replacing_seal_stats[0], 'any', 10)
        self.publish_message(REPLACE_IN_CHAT_CMD, replace_cmd, replaceable_seal_stats[0])

    @staticmethod
    def get_seal_id(config_file):
        return config_file['access_token']['user_id']

    @staticmethod
    def get_config(config_file_name):
        print(config_file_name)

        seal_config = yaml.load(open(config_file_name))
        return SealBreeder.get_seal_id(seal_config), seal_config

    @staticmethod
    def prepare_log_file(dir_path, config_file_name, run_time):
        create_dir(dir_path)
        # TODO: where and how we store output???
        log_file_name = os.path.join(dir_path, str(config_file_name) + '_#{}_'.format(run_time) + '.log')
        rem_file(log_file_name)
        return log_file_name

    @staticmethod
    def start_seal(config_file_name, log_file_name, mode):
        return subprocess.Popen('python3 seal.py -c {} -m breeder {}> {}'
                                .format(str(config_file_name),
                                        '-t ' if mode == BreederMode.TestMode else '',
                                        log_file_name),
                                shell=True)
