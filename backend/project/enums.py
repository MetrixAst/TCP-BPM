from enum import Enum

class CustomEnum(Enum):

    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))
    
    @classmethod
    def from_value(cls, status):
        res = cls.__dict__.get(status.upper(), None)
        if res is not None:
            return res.value
        return None