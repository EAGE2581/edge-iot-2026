
import re
import sys
import xml.etree.ElementTree as ET

import yaml

SEVERITY = {'F': 'critical', 'A': 'warning', 'N': 'info'}
CATEGORY = {'F': 'fault',    'A': 'warn',    'N': 'notice'}
PRIO     = {'F': 0,          'A': 1,         'N': 2}


def parse_number(num_str):
    m = re.match(r'^([FAN])(\d+)\s*(?:\(([^)]+)\))?', num_str.strip())
    if not m:
        return None, []
    main = m.group(1)
    extras = []
    if m.group(3):
        extras = [x.strip() for x in m.group(3).split(',')
                  if x.strip() in ('F', 'A', 'N')]
    return main, [main] + extras


def convert(xml_path, yaml_path):
    root = ET.parse(xml_path).getroot()
    alarms = {}
    stats = {'F': 0, 'A': 0, 'N': 0}
    skipped = 0
    dupes = 0

    for alarm in root.findall('SINAMICSAlarm'):
        nr = alarm.get('nr')
        if not nr:
            skipped += 1
            continue
        try:
            code = int(nr)
        except ValueError:
            skipped += 1
            continue

        main, types = parse_number(alarm.get('Number', ''))
        if main is None:
            skipped += 1
            continue

        text = (alarm.findtext('LongName') or '').strip()
        if not text:
            text = (alarm.findtext('ShortName') or '').strip()
        if not text:
            skipped += 1
            continue

        if code in alarms:
            if PRIO[alarms[code]['_main']] <= PRIO[main]:
                continue
            dupes += 1

        alarms[code] = {
            'text':     text,
            'severity': SEVERITY[main],
            'category': CATEGORY[main],
            '_main':    main,
            '_types':   types,
        }
        stats[main] += 1

    out = {}
    for code in sorted(alarms):
        info = alarms[code]
        entry = {
            'text':     info['text'],
            'severity': info['severity'],
            'category': info['category'],
        }
        if len(info['_types']) > 1:
            entry['types'] = info['_types']
        out[code] = entry

    with open(yaml_path, 'w', encoding='utf-8') as f:
        src = xml_path.replace('\\', '/').split('/')[-1]
        f.write(f"# 由 tools/xml2yaml.py 自动生成，勿手工编辑\n")
        f.write(f"# 源文件: {src}\n")
        f.write(f"# 报警总数: {len(out)} "
                f"(F={stats['F']}, A={stats['A']}, N={stats['N']})\n\n")
        yaml.dump({'alarms': out}, f, allow_unicode=True,
                  sort_keys=False, default_flow_style=False, width=1000)

    print(f"OK: {len(out)} 条已写入 {yaml_path}")
    print(f"    F={stats['F']}  A={stats['A']}  N={stats['N']}  "
          f"冲突覆盖={dupes}  跳过={skipped}")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python3 tools/xml2yaml.py <input.xml> <output.yaml>")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
