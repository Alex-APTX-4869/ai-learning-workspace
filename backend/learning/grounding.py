"""Bounded original-source snapshots; retrieval is not proof of semantic support."""
from copy import deepcopy

from backend.materials import retrieval


class MaterialEvidenceError(Exception):
    """Safe, actionable errors that may be shown to the learner."""


def collect_evidence(db, course_id: int, outline_id: int | None, context: dict) -> dict:
    if not retrieval.course_scope(db, course_id, outline_id):
        return {"method": "none", "sources": []}
    point = context["target_point"]
    # Prioritize the actual point, not the broad course name. A second query
    # supplies a fallback for differently worded section headings.
    queries = [f'{point["name"]} {point["intro"]}'[:1200],
               context["target_section"]["section_name"][:300]]
    sources = []
    for query in queries:
        if not retrieval.terms(query):
            continue
        result = retrieval.search(db, course_id, outline_id, query, limit=6)
        for hit in result["hits"]:
            offset = max(0, hit["offset"] - 250)
            # Deduplicate overlapping windows, while allowing separate passages
            # on the same long page. Max 6 x 1800 characters, not the whole PDF.
            if any(s["file_id"] == hit["file_id"] and s["element_id"] == hit["element_id"]
                   and abs(s["offset"] - offset) < 1800 for s in sources):
                continue
            original = retrieval.read_source(db, course_id, outline_id, hit["file_id"],
                                             hit["process_id"], hit["element_id"], offset)
            sources.append({**hit, "id": f"S{len(sources) + 1}", "offset": offset,
                            "excerpt": original["text"][:1800]})
            if len(sources) == 6:
                break
        if sources:
            break
    if not sources:
        raise MaterialEvidenceError("在此目录版本已确认的资料范围内未检索到相关原文，已停止制作，未调用内容模型。请核对知识点名称与资料范围；需要补充资料时请创建新版本。未命中不代表文件中一定没有该内容。")
    return {"method": "keyword", "sources": sources}


def attach_evidence(content, context: dict):
    """Never trust model-generated filenames, pages or source excerpts."""
    evidence = context.get("material_evidence", {"method": "none", "sources": []})
    return content.model_copy(update={"material_evidence": deepcopy(evidence)})


def grounding_issues(content, context: dict) -> list[str]:
    evidence = context.get("material_evidence", {})
    if evidence.get("method") != "keyword":
        return []
    allowed = {source["id"] for source in evidence.get("sources", [])}
    issues = []
    for component in [*content.lesson_cards, *content.examples, *content.exercises,
                      *([content.code_lab] if content.code_lab else [])]:
        if set(component.source_ids) - allowed:
            issues.append("内容引用了未读取的来源编号，不能发布。")
        if component.source_kind == "source_based" and not component.source_ids:
            issues.append("声称依据资料的内容缺少原文引用。")
        if component.source_kind == "supplemental" and component.source_ids:
            issues.append("补充内容不能冒充原文依据；请区分资料改写与自主补充。")
    if not any(card.source_kind == "source_based" and card.source_ids for card in content.lesson_cards):
        issues.append("现有原文未支撑任何讲解卡片；请核对资料覆盖范围，不发布整篇自主补写的资料课程。")
    if content.source_gaps:
        issues.append(("原文依据不足：" + "；".join(content.source_gaps))[:3900])
    return list(dict.fromkeys(issues))
