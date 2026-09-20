"""检查明确的语言混用和题型混用；不执行教学代码或猜测内容难度。"""
import ast
import json
import re

def language_issues(content):
    blocks = []
    texts = [(f'卡片「{c.title}」',c.body_markdown) for c in content.lesson_cards]
    texts += [(f'示例「{e.title}」',e.explanation_markdown) for e in content.examples]
    for location, markdown in texts:
        blocks.extend((location,match[0].lower(),match[1]) for match in re.findall(r'```(python|json)\s*\n(.*?)```',markdown,re.S|re.I))
    blocks.extend((f'示例「{e.title}」',(e.language or '').lower(),e.code) for e in content.examples if e.code)
    issues = []
    for location, language, code in blocks:
        if language == 'python':
            try:
                tree = ast.parse(code)
            except SyntaxError:
                continue  # 代码可能是明确标注的片段，交给语义审查判断完整性。
            assigned = {n.id for n in ast.walk(tree) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store)}
            names = {n.id for n in ast.walk(tree) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load)}
            mistaken = (names-assigned) & {'true','false','null'}
            if mistaken:
                issues.append(f'{location}：Python 代码含未定义的 JSON 字面量 {", ".join(sorted(mistaken))}；改用对应 Python 值或正确标为 JSON，并解释二者区别。')
        elif language == 'json' and '...' not in code:
            try:
                json.loads(code)
            except ValueError:
                issues.append(f'{location}：标为 JSON 的代码无法按 JSON 解析；检查布尔值、空值、引号与注释，或明确改为相应语言/伪代码。')
    return list(dict.fromkeys(issues))


def exercise_type_issues(content):
    issues=[]
    judgments={'正确','错误','对','错','是','否','true','false'}
    for index, exercise in enumerate(content.exercises,1):
        labels=[re.sub(r'[\s。.!！?？]', '', o.text).lower() for o in exercise.options]
        if exercise.kind in {'single_choice','multiple_choice'} and labels and all(label in judgments for label in labels):
            issues.append(f'练习 {index}：选择题选项实际只有正误判断；请改为独立判断题，或用具体结果/做法重新设计选择题。')
        elif exercise.kind in {'single_choice','multiple_choice'} and labels and all(
            len(re.findall(r'(?:[①②③④⑤⑥]|第[一二三四五六\d]+(?:句|项|条)|[1-6][、.)）])\s*(?:是|为)?\s*(?:正确|错误|对|错)', option.text)) >= 2
            for option in exercise.options
        ):
            issues.append(f'练习 {index}：选择题使用多句正误组合；请拆为独立判断题，或改为比较具体结果/做法的选择题。')
        if exercise.kind=='true_false' and set(labels)!={'正确','错误'}:
            issues.append(f'练习 {index}：判断题只保留“正确”和“错误”两个选项，理由移到解析，题干保持一条可判定陈述。')
    return issues
