from pathlib import Path

path = Path('app.py')
source = path.read_text(encoding='utf-8-sig')
marker = '\n    import os\nimport sqlite3\n'
entrypoint = source.find('if __name__ == "__main__":')
start = source.find(marker, entrypoint)
if entrypoint < 0 or start < 0:
    raise SystemExit('Expected duplicated app source tail was not found; no change made.')
path.write_text(source[:start].rstrip() + '\n)\n', encoding='utf-8')
