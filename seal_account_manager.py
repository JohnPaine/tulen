from seal_management import *


class SealAccountManager(BaseAccountManager):
    def __init__(self, seal_id, mode, slot_map):
        super().__init__(slot_map)
        self.seal_id = seal_id
        self.mode = mode

    def __enter__(self):
        print('SealAccountManager.__enter__')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('SealAccountManager.__exit__')

    def make_signal_routing_key(self, signal, manager='manager', seal_id=None):
        return '{}.{}.{}'.format(signal, self.seal_id, manager)

    def make_slot_routing_key(self, queue_name, manager='manager', seal_id=None):
        return '{}.{}.{}'.format(queue_name, manager, self.seal_id)

    def make_message(self, signal, manager='manager', seal_id=None):
        return 'signal:{} from seal:{} to {}'.format(signal, self.seal_id, manager)
