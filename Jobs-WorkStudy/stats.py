
import argparse
import collections
import json
import os
import sys


def count_supervisor_titles(path):
	with open(path, 'r', encoding='utf-8') as fh:
		data = json.load(fh)

	if not isinstance(data, list):
		raise ValueError("expected JSON root to be a list of records")

	counter = collections.Counter()
	for rec in data:
		if not isinstance(rec, dict):
			counter['(invalid-record)'] += 1
			continue
		title = rec.get('supervisor_title')
		if title is None or str(title).strip() == '':
			counter['(unspecified)'] += 1
		else:
			# keep the raw value but strip surrounding whitespace
			counter[str(title).strip()] += 1

	return counter, len(data)


def main():
	default_path = os.path.join(os.path.dirname(__file__), 'work_study_jobs.json')
	p = argparse.ArgumentParser(description='Count supervisor_title frequencies in a work-study JSON dump')
	p.add_argument('file', nargs='?', default=default_path, help='path to the JSON file (default: work_study_jobs.json next to this script)')
	p.add_argument('--json', action='store_true', help='print output as JSON')
	args = p.parse_args()

	try:
		counts, total = count_supervisor_titles(args.file)
	except Exception as e:
		print(f"Error reading/processing file: {e}", file=sys.stderr)
		sys.exit(2)

	if args.json:
		out = {'total_records': total, 'counts': dict(counts)}
		print(json.dumps(out, indent=2, ensure_ascii=False))
		return

	print(f"Total records: {total}")
	if total == 0:
		return

	for title, cnt in counts.most_common():
		pct = 100 * cnt / total
		print(f"{cnt:5d}  {pct:6.2f}%  {title}")


if __name__ == '__main__':
	main()
