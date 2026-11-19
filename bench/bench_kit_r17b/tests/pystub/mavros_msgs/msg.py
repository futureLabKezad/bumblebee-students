class State:
    def __init__(self, connected=False, armed=False, mode=''):
        self.connected = connected
        self.armed = armed
        self.mode = mode


class StatusText:
    def __init__(self, severity=6, text=''):
        self.severity = severity
        self.text = text
