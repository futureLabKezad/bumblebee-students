class Image:
    pass


class BatteryState:
    def __init__(self, voltage=0.0, percentage=0.0, current=0.0, present=True, cell_voltage=None):
        self.voltage = voltage
        self.percentage = percentage
        self.current = current
        self.present = present
        self.cell_voltage = cell_voltage or []
