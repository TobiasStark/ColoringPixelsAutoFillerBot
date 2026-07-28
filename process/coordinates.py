"""Map logical grid cells to screen/client coordinates."""


class CoordinateMapper:
    def __init__(self, origin_x: float, origin_y: float, cell_w: float, cell_h: float,
                 client_left: int = 0, client_top: int = 0):
        """origin is in client coordinates. logical (0,0) maps to (origin_x, origin_y)."""
        self.ox = origin_x
        self.oy = origin_y
        self.cell_w = cell_w
        self.cell_h = cell_h
        self.client_left = client_left
        self.client_top = client_top

    def to_screen(self, logical_x: int, logical_y: int):
        """Return absolute screen coordinates."""
        return (int(self.client_left + self.ox + logical_x * self.cell_w),
                int(self.client_top + self.oy + logical_y * self.cell_h))

    def to_client(self, logical_x: int, logical_y: int):
        return (int(self.ox + logical_x * self.cell_w),
                int(self.oy + logical_y * self.cell_h))

    def logical_to_client(self, logical_x: int, logical_y: int):
        return self.to_client(logical_x, logical_y)
