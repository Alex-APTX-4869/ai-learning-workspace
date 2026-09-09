from backend.ai.schemas import ChapterPointsRequest, CourseRequest


def outline_prompt(course: CourseRequest) -> str:
    return f"""你是一位课程设计专家。请生成适合用户的中文课程目录。
课程主题：{course.topic}
要求说明：{course.intro}

严格采用课程 → 章节 → 小节的结构，不在此次生成知识点或正文。
章节和小节的数量由学习目标决定；划分合理，衔接清晰，组合成完整体系。
只返回合法 JSON，不要 Markdown 围栏或解释文字，严格使用以下字段：
{{"name":"课程名称","chapters":[{{"name":"章节名称","sections":[{{"name":"小节名称"}}]}}]}}
"""


def points_prompt(request: ChapterPointsRequest) -> str:
    existing = "\n".join(request.existing_point_names) or "暂无已生成知识点"
    return f"""你是一位课程设计专家。为指定章节的全部小节补充中文知识点。
课程主题：{request.course.topic}
课程要求：{request.course.intro}
课程目录与已生成内容（用于明确范围）：
{request.course_context}
已有知识点名称：
{existing}
本次章节：{request.chapter.model_dump_json()}

为每个小节生成合理数量的知识点，每个知识点包含 name 和 intro。
不要与已有内容无意义重讲；允许必要复习和进阶应用，进阶须说明新增能力。
不得修改章节名、小节名、小节顺序或增删小节。
只返回合法 JSON，不要 Markdown 围栏或解释文字：
{{"name":"当前章节名称","sections":[{{"name":"当前小节名称","points":[{{"name":"知识点名称","intro":"具体学习内容及范围"}}]}}]}}
"""
