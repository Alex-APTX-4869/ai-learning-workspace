from copy import deepcopy

from fastapi import HTTPException

from backend.learning.schemas import PointContent


def build_deck(content: PointContent) -> list[dict]:
    """固定内容顺序，模型只可请求下一张，不能改序或编造卡片。"""
    if not content.lesson_cards:
        raise HTTPException(409, "此内容没有分步卡片，请先重新生成知识点内容。")
    cards = [
        {"id": f"lesson-{index}", "kind": "lesson", **card.model_dump(mode="json")}
        for index, card in enumerate(content.lesson_cards)
    ]
    cards.extend(
        {"id": f"example-{index}", "kind": "example", "title": example.title,
         "body_markdown": example.explanation_markdown, "code": example.code, "language": example.language,
         "source_kind": example.source_kind, "source_ids": example.source_ids}
        for index, example in enumerate(content.examples)
    )
    cards.extend(
        {"id": f"exercise-{index}", "kind": "exercise", "title": f"练习 {index + 1}",
         "exercise": exercise.model_dump(mode="json"),
         "source_kind": exercise.source_kind, "source_ids": exercise.source_ids}
        for index, exercise in enumerate(content.exercises)
    )
    if content.code_lab:
        cards.append({"id": "code-lab", "kind": "code_lab", "title": content.code_lab.title,
                      "lab": content.code_lab.model_dump(mode="json"),
                      "source_kind": content.code_lab.source_kind, "source_ids": content.code_lab.source_ids})
    return cards


def learner_card(card: dict) -> dict:
    result = deepcopy(card)
    if result["kind"] == "exercise":
        # 先作答、再查看反馈，避免讲师上下文无意提前暴露答案。
        result["exercise"].pop("answer", None)
        result["exercise"].pop("explanation", None)
        for option in result["exercise"]["options"]:
            option.pop("correct", None)
    return result


def grade_exercise(card: dict, selected: list[int], written: str) -> dict:
    if card["kind"] != "exercise":
        raise HTTPException(409, "当前卡片不是练习题。")
    exercise = card["exercise"]
    if exercise["kind"] == "short_answer":
        if selected or not written.strip():
            raise HTTPException(422, "请先写下你的思路。")
        correct = None  # 陈述题不能靠字符串匹配伪装自动评分。
    else:
        if written.strip() or not selected or any(index >= len(exercise["options"]) for index in selected):
            raise HTTPException(422, "请选择有效答案。")
        if exercise["kind"] in ("single_choice", "true_false") and len(selected) != 1:
            raise HTTPException(422, "这道题只能选择一个答案。")
        expected = {index for index, option in enumerate(exercise["options"]) if option["correct"]}
        correct = set(selected) == expected
    return {"selected": selected, "written_answer": written.strip(), "correct": correct,
            "answer": exercise["answer"], "explanation": exercise["explanation"]}
