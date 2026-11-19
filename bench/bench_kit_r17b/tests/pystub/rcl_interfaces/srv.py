class ParameterValue:
    def __init__(self, type=0, bool_value=False, integer_value=0, double_value=0.0):
        self.type = type
        self.bool_value = bool_value
        self.integer_value = integer_value
        self.double_value = double_value


class _Req:
    def __init__(self):
        self.names = []


class GetParameters:
    Request = _Req
