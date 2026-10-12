# -*- coding: utf-8 -*-
# author: liucailin

"""黑话词典查询脚本。

用法:
	python scripts/lookup_slang.py DT 66 WJ
	python scripts/lookup_slang.py --list
	python scripts/lookup_slang.py --chapter 4
	python scripts/lookup_slang.py --chapters
"""

import os
import sys

DICT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "slang-dict.md")

ALIAS_SEPS = ("/", "、", "，", ",")

SPECIAL_ENTRIES = {
	"#n": ("九、表情快捷键", "游戏表情快捷键，n = 1 ~ 1000，用例中直接保留原文"),
}

CHAPTER_NUMERALS = {
	"1": "一",
	"2": "二",
	"3": "三",
	"4": "四",
	"5": "五",
	"6": "六",
	"7": "七",
	"8": "八",
	"9": "九",
	"10": "十",
	"11": "十一",
}


def norm(text):
	return text.strip().strip("*`").strip()


def split_aliases(cell):
	parts = [cell]
	for sep in ALIAS_SEPS:
		next_parts = []
		for part in parts:
			next_parts.extend(part.split(sep))
		parts = next_parts
	return [norm(p) for p in parts if norm(p)]


def parse_dict(path):
	chapters = []
	entries = []
	current = None
	subsection = None
	header_seen = False
	row_count = 0

	with open(path, "r", encoding="utf-8") as fp:
		for raw in fp:
			line = raw.rstrip("\n")
			if line.startswith("#"):
				if line.startswith("## "):
					current = norm(line[3:])
					chapters.append(current)
					subsection = None
				elif line.startswith("### "):
					subsection = norm(line[4:])
				header_seen = False
				row_count = 0
				continue
			if current is None or not line.startswith("|"):
				continue
			cells = [norm(c) for c in line.strip().strip("|").split("|")]
			if not cells or not any(cells):
				continue
			if set("".join(cells)) <= set("-: "):
				header_seen = True
				row_count = 0
				continue
			if not header_seen:
				continue
			row_count += 1
			if not cells[0] or cells[0].startswith("——"):
				continue
			if len(cells) < 2:
				continue
			keys = split_aliases(cells[0])
			if len(cells) == 2:
				meaning = cells[1]
				if subsection:
					meaning = "%s：%s" % (subsection, meaning)
			elif len(cells) == 3:
				meaning = "%s：%s" % (cells[1], cells[2])
			elif len(cells) == 5:
				meaning = "%s（%s，%s，编号 %s）" % (cells[2], cells[3], cells[4], cells[0])
				keys.extend(split_aliases(cells[1]))
				keys.extend(split_aliases(cells[2]))
			elif len(cells) >= 7:
				labels = ("普通①", "普通②", "渡劫①", "渡劫②", "三飞①", "三飞②")
				meaning = "普通 %s/%s，渡劫 %s/%s，三飞 %s/%s" % tuple(cells[2:8])
				for label, code in zip(labels, cells[2:8]):
					if code.isdigit():
						entries.append((code, current, "%s %s" % (cells[0], label)))
			else:
				meaning = " | ".join(cells[1:])
			for key in keys:
				entries.append((key, current, meaning))

	all_keys = [k for k, _, _ in entries]
	for key, value in SPECIAL_ENTRIES.items():
		if key not in all_keys:
			entries.append((key, value[0], value[1]))
	return chapters, entries


def do_lookup(entries, terms):
	found = 0
	index = {}
	for key, chapter, meaning in entries:
		index.setdefault(key.lower(), []).append((key, chapter, meaning))

	for term in terms:
		raw = term.strip().strip("\"'")
		key = raw.lower()
		if raw.startswith("#") and raw[1:].isdigit():
			found += 1
			print("[九、表情快捷键] %s -> %s" % (raw, SPECIAL_ENTRIES["#n"][1]))
			continue
		matches = index.get(key)
		if not matches and raw.isdigit() and len(raw) < 4:
			matches = index.get(raw.zfill(4))
			if matches:
				raw = raw.zfill(4)
		if not matches and any(sep in raw for sep in ALIAS_SEPS):
			for alias in split_aliases(raw):
				found += do_lookup(entries, [alias])
			continue
		if not matches:
			print("[未命中] %s" % raw)
			continue
		for _key, chapter, meaning in matches:
			found += 1
			print("[%s] %s -> %s" % (chapter, raw, meaning))
	return found


def main(argv):
	chapters, entries = parse_dict(DICT_PATH)

	if not argv or argv[0] in ("-h", "--help"):
		print("用法: python lookup_slang.py <黑话> [更多黑话...]")
		print("      python lookup_slang.py --chapters          列出全部章节")
		print("      python lookup_slang.py --chapter <章节>      列出某章全部词条（如 四 / 4 / 一之二）")
		return 0

	if argv[0] == "--chapters":
		for name in chapters:
			total = sum(1 for _, ch, _ in entries if ch == name)
			print("%s (%d 条)" % (name, total))
		return 0

	if argv[0] == "--chapter":
		if len(argv) < 2:
			print("[失败] --chapter 需要章节序号")
			return 1
		target = argv[1]
		if target in CHAPTER_NUMERALS:
			target = CHAPTER_NUMERALS[target]
		matched = None
		for name in chapters:
			if name == target or (target and name.startswith(target + "、")) or name.endswith("、" + target):
				matched = name
				break
		if not matched:
			print("[失败] 找不到章节: %s" % target)
			return 1
		print("== %s ==" % matched)
		for key, chapter, meaning in entries:
			if chapter == matched:
				print("%s -> %s" % (key, meaning))
		return 0

	if argv[0] == "--terms":
		seen = []
		for key, _, _ in entries:
			if key not in seen:
				seen.append(key)
		print(" ".join(seen))
		return 0

	found = do_lookup(entries, argv)
	if not found:
		print("[提示] 词典未命中，需回退线上词典或更新 references/slang-dict.md")
		return 1
	return 0


if __name__ == "__main__":
	if hasattr(sys.stdout, "reconfigure"):
		sys.stdout.reconfigure(encoding="utf-8")
	try:
		sys.exit(main(sys.argv[1:]))
	except BrokenPipeError:
		sys.exit(0)
	except Exception as exc:  # noqa: BLE001
		print("[失败] %s: %s" % (type(exc).__name__, exc))
		sys.exit(1)
