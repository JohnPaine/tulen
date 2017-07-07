import subprocess
from collections import defaultdict, namedtuple
from functools import reduce
from operator import itemgetter

import yaml
import random

from seal_management import *
from seal_management_utils import *


class SealBalancingConditions:
    def __init__(self):
        pass

    BY_ACTION_COUNT = (1, 'action_count')
    BY_CHAT_COUNT = (2, 'chat_count')


ChatSealBalancingResponse = namedtuple('ChatSealBalancingResponse', ['cmd_message',
                                                                     'being_replaced_seal_id',
                                                                     'replacing_seal_id'])
BalancingListItem = namedtuple('BalancingListItem', ['seal_id',
                                                     SealBalancingConditions.BY_ACTION_COUNT[1],
                                                     SealBalancingConditions.BY_CHAT_COUNT[1]])


class ChatSealBalancing:
    def __init__(self):
        pass

    @staticmethod
    def balance_seals(seal_configs_dict, condition=SealBalancingConditions.BY_CHAT_COUNT):
        return ChatSealBalancing.balance_seals_by_condition(seal_configs_dict, condition)

    @staticmethod
    def choose_seals_for_balancing(sorted_balancing_list: list) -> tuple:
        if len(sorted_balancing_list) < 2:
            return None, None

        # TODO: change??
        being_replaced = sorted_balancing_list[0]
        replacing = sorted_balancing_list[-1]
        diff = abs(being_replaced.chat_count - replacing.chat_count)
        if diff < 3:
            print('\tchoose_seals_for_balancing, chat_count diff: {} almost equal - replacing abandoned'.format(diff))
            return None, None
        print('\tBALANCING seals, being_replaced: {}, replacing: {}'.format(being_replaced, replacing))
        return being_replaced, replacing

    @staticmethod
    def generate_response(sorted_balancing_list, chat_id=-1, chat_count=1):
        being_replaced, replacing = ChatSealBalancing.choose_seals_for_balancing(sorted_balancing_list)
        if not being_replaced or not replacing or replacing == being_replaced:
            print('\tunable to choose seals for chat balancing...')
            return None
        return ChatSealBalancingResponse(cmd_message=REPLACE_IN_CHAT_CMD_format.format(replacing.seal_id,
                                                                                       chat_id,
                                                                                       chat_count),
                                         being_replaced_seal_id=being_replaced.seal_id,
                                         replacing_seal_id=replacing.seal_id)

    @staticmethod
    def form_balancing_list(seal_configs: dict) -> list:
        """Forms a list of BalancingListItem-items containing info for seal balancing

        :param dict seal_configs: a dict in format: {seal_id: SealConfig obj} 
        :rtype: list of ids for balancing
        """
        balancing_list = []
        for seal_id, seal_config in seal_configs.items():
            if not len(seal_config.lb_action_stats) or not seal_config.chat_count:
                continue
            times_sum = reduce(lambda x, y: x + y,
                               [times for action, times in seal_config.lb_action_stats.items()])
            balancing_list.append(BalancingListItem(seal_id=seal_id,
                                                    action_count=times_sum,
                                                    chat_count=seal_config.chat_count))
        return balancing_list

    @staticmethod
    def balance_seals_by_condition(seal_configs_dict, condition):
        balancing_list = ChatSealBalancing.form_balancing_list(seal_configs_dict)
        sorted_bl_by_actions = sorted(balancing_list,
                                      key=itemgetter(condition[0]),
                                      reverse=True)
        print('sorted_bl_by_actions - {}'.format(sorted_bl_by_actions))

        return ChatSealBalancing.generate_response(sorted_bl_by_actions)


class SealConfig:
    def __init__(self, seal_id, seal_process, config_file_name, start_counter):
        # seal id from seal config
        self.seal_id = seal_id
        # seal process object
        self.process = seal_process
        # filename for seal config
        self.config_file_name = config_file_name
        # stats (times occurred) for all vk_user actions
        self.action_stats = defaultdict(int)
        # stats (times occurred) for load-balancing vk_user actions: send_message, post_sticker, post_picture, etc
        self.lb_action_stats = defaultdict(int)
        # chat counter for seal
        self.chat_count = 0
        # seal start counter in single seal_breeder session
        self.start_counter = start_counter


class SealBreeder(BaseAccountManager):
    def __init__(self, receiver_id=MANAGER_NAME):
        super().__init__(receiver_id)
        self.seals = {}
        self.SEALS_PROCESSES = []
        self.mode = BreederMode.NoMode
        self.friends_sharing_uids = []

    def __enter__(self):
        print('SealBreeder.__enter__')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('SealBreeder.__exit__')

    def send_connect_to_seals_cmd(self, seal_id):
        seal_ids = ",".join((str(_seal_id) for _seal_id in self.seals.keys() if _seal_id != seal_id))
        if not seal_ids:
            return
        self.publish_message(signal=CONNECT_TO_SEALS_CMD,
                             receiver_id=seal_id,
                             message=CONNECT_TO_SEALS_CMD_format.format(seal_ids))

    def register_seal(self, seal_id, seal_process, config_file_name, start_counter):
        self.seals[seal_id] = SealConfig(seal_id, seal_process, config_file_name, start_counter)

        if start_counter > 1:
            self.send_connect_to_seals_cmd(seal_id)

    def finish_seals(self):
        try:
            print('seal_breeder, finish_seals called')
            exit_codes = []
            for seal_config in self.seals.values():
                self.publish_message(STOP_SEAL_CMD, receiver_id=seal_config.seal_id)
                exit_codes.append(seal_config.process.wait(10))

            print('all seals finished with codes: {}'.format(exit_codes))
        except Exception as e:
            print('Exception occurred while finishing seals: {}'.format(e))

    def start_seal_process(self, seal_id, config_file_name):
        print('starting seal process for seal_id: {} and config_file: {}'.format(seal_id, config_file_name))
        start_counter = 1
        if seal_id in self.seals:
            start_counter = self.seals[seal_id].start_counter + 1

        log_file_name = SealBreeder.prepare_log_file('./seal_logs', config_file_name, start_counter)

        seal_process = SealBreeder.start_seal(config_file_name, log_file_name, self.mode)
        self.register_seal(seal_id, seal_process, config_file_name, start_counter)

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

    def balance_seals_for_chats(self, condition=SealBalancingConditions.BY_CHAT_COUNT):
        result = ChatSealBalancing.balance_seals(self.seals, condition)
        if not result:
            return
        print('being_replaced_seal_id: {} with replacing_seal_id: {}\n'
              .format(result.being_replaced_seal_id, result.replacing_seal_id))
        self.publish_message(REPLACE_IN_CHAT_CMD, result.being_replaced_seal_id, result.cmd_message)

    def share_friends(self, seal_id=None):
        if not len(self.friends_sharing_uids):
            print("Can't share friends - sharing list is empty!")
            return

        friends_source_uid = random.choice(self.friends_sharing_uids)

        if seal_id:
            self.publish_message(ADD_FRIEND_CMD, seal_id,
                                 ADD_FRIEND_CMD_format.format(friends_source_uid))
        else:
            for seal_id, _ in self.seals.items():
                self.publish_message(ADD_FRIEND_CMD, seal_id,
                                     ADD_FRIEND_CMD_format.format(friends_source_uid))

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
        log_file_name = os.path.join(dir_path, str(config_file_name) + '_#_{}'.format(run_time) + '.log')
        rem_file(log_file_name)
        return log_file_name

    @staticmethod
    def start_seal(config_file_name, log_file_name, mode):
        return subprocess.Popen('python3 seal.py -c {} -m breeder {}> {}'
                                .format(str(config_file_name),
                                        '-t ' if mode == BreederMode.TestMode else '',
                                        log_file_name),
                                shell=True)
