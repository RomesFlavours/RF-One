"""Prepare local entry links only; Kitchen owns all recipe data and photos."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output' / 'visual-menu'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for place, restaurant_id in [('winter-park', 1), ('mount-dora', 2)]:
        address = f'http://127.0.0.1:5097/visual-menu/{restaurant_id}/shrimp-pistacchio'
        (OUT / (place + '.html')).write_text(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0;url={address}"><title>Visual Menu</title>'
            f'<p><a href="{address}">Open live Visual Menu</a></p></html>', encoding='utf-8')
    print('Prepared live entry links only. Kitchen data and photographs are not copied.')


if __name__ == '__main__':
    main()
