import os


# utils:        --------------------------------------------------------------------------------------------------------
def rem_file(name):
    try:
        os.remove(name)
    except OSError:
        pass


def create_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


class SealManagerException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return u"SealManager exception: {}".format(self.value)


class IterCounter:
    def __init__(self, worker_id, max_count=10, raise_exception=True):
        self.counter = 0
        self.max_count = max_count
        self.raise_exception = raise_exception
        self.worker_id = worker_id
        print('IterCounter, max_count: {}, raise_exception: {}'.format(max_count, raise_exception))

    def count(self):
        self.counter += 1
        print('IterCounter: {}'.format(self.counter))
        if self.raise_exception and self.counter > self.max_count:
            msg = "IterCounter loop limit : {} was reached for receiver" \
                  "_id: {}".format(self.max_count, self.worker_id)
            print(msg)
            raise SealManagerException(msg)

    @staticmethod
    def step_counter(f):
        def wrapper(*args, **kwargs):
            iter_counter = args[0]
            if isinstance(iter_counter, IterCounter):
                iter_counter.count()
            return f(*args, **kwargs)

        return wrapper


# utils:        --------------------------------------------------------------------------------------------------------
