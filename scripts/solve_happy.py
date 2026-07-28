"""Solve the currently loaded level without menu navigation."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from process.memory_reader import MemoryReader
from process.grid_reader import GridReader
from process.vision import Vision
from process.input_controller import InputController
from process.window_manager import WindowManager


def main():
    window = WindowManager()
    window.update_rect()
    window.focus()
    time.sleep(0.3)

    mr = MemoryReader(process_name=config.PROCESS_EXE)
    gr = GridReader(mr)
    info = gr.read_grids()
    print('grid', info['x_max'], info['y_max'])

    v = Vision(window.client_rect())
    mapping, dx, dy = v.build_grid_mapping(info['saved'], info['main'])
    print('mapping', len(mapping), 'spacing', dx, dy)

    ctrl = InputController(window.client_rect())

    def remaining(g):
        return [(x, y) for y in range(g['y_max']) for x in range(g['x_max'])
                if g['main'][y][x] != 0 and g['saved'][y][x] != g['main'][y][x]]

    rem = remaining(info)
    print('remaining', len(rem))

    cells_by_color = {}
    for (x, y) in mapping:
        c = info['main'][y][x]
        if c > 0 and info['saved'][y][x] != c:
            cells_by_color.setdefault(c, []).append((x, y))

    colors = sorted(cells_by_color.keys())
    print('colors', colors, {c: len(v) for c, v in cells_by_color.items()})

    for color in colors:
        ctrl.select_color_by_key(color)
        pts = cells_by_color[color]
        print(f'color {color}: {len(pts)} cells')
        for (x, y) in pts:
            cx, cy = mapping[(x, y)]
            ctrl.click(cx, cy, duration=0.03)
        time.sleep(0.2)
        info = gr.read_grids()
        rem = remaining(info)
        print(f'after color {color}, remaining {len(rem)}')

    final = remaining(gr.read_grids())
    print('done, remaining', len(final))
    v.close()


if __name__ == '__main__':
    main()
