"""显式原章编号是归属标识，不是可重复生成的展示标题。"""
import re


def chapter_key(name: str):
    match = re.match(r'^\s*第\s*([0-9一二三四五六七八九十百零〇两]+)\s*章', name)
    return match.group(1) if match else None


def group_chapters(chapters: list[dict]) -> list[dict]:
    from copy import deepcopy
    result, numbered = [], {}
    for original in chapters:
        chapter = deepcopy(original)
        key = chapter_key(chapter['name'])
        if key and key in numbered:
            target = numbered[key]
            target['sections'].extend(chapter['sections'])
            # 不用第一个子模块的标题冒充整章；明确保留各模块名。
            tail = re.sub(r'^\s*第\s*[^章]+章\s*', '', chapter['name'])
            if tail not in target['name']:
                target['name'] += ' / ' + tail
        else:
            result.append(chapter)
            if key:
                numbered[key] = chapter
    return result
