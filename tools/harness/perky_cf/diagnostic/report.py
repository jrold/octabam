import json, sys, collections
c = json.load(open(sys.argv[1] + '/count.json'))
case = [p for p in __import__('pathlib').Path(sys.argv[1]).iterdir() if p.is_dir() and p.name.startswith('PKFM')][0]
cost = json.load(open(case / 'cost.json')); n = cost['completed_ISR'] - 512
fc = collections.Counter(cost['ISR'])
total = sum(fc.values())
print('ISR total %.3f us' % (total / n / 264))
rows = sorted(((v / n / 264, c['entries'].get(k, 0) / n, k, v / max(c['entries'].get(k, 1), 1)) for k, v in fc.items()), reverse=True)
for us, per, name, cyc in rows[:int(sys.argv[2]) if len(sys.argv) > 2 else 40]:
    print('%-34s %7.3f us %6.2f calls/frame %8.1f cyc/call' % (name, us, per, cyc))
bg = sum(cost['background'].values()) / n / 264
print('background %.3f us' % bg)
