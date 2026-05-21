import threading

_local = threading.local()


def set_request_context(user=None, ip_address=None, user_agent=''):
    _local.user = user
    _local.ip_address = ip_address
    _local.user_agent = (user_agent or '')[:2000]


def clear_request_context():
    for attr in ('user', 'ip_address', 'user_agent'):
        if hasattr(_local, attr):
            delattr(_local, attr)


def get_request_context():
    return {
        'user': getattr(_local, 'user', None),
        'ip_address': getattr(_local, 'ip_address', None),
        'user_agent': getattr(_local, 'user_agent', ''),
    }
