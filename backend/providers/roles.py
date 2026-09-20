from dataclasses import dataclass


CAPABILITY_KEYS = (
    "text_chat",
    "structured_output",
    "streaming",
    "vision",
    "embeddings",
)


@dataclass(frozen=True)
class RoleDefinition:
    key: str
    name: str
    description: str
    required_capabilities: tuple[str, ...]
    default_role: str


def _structured(key: str, name: str, description: str) -> RoleDefinition:
    return RoleDefinition(
        key=key,
        name=name,
        description=description,
        required_capabilities=("text_chat", "structured_output"),
        default_role="default.chat",
    )


ROLE_DEFINITIONS = (
    RoleDefinition(
        "default.chat",
        "默认对话模型",
        "没有专项覆盖时供文本职责继承。",
        ("text_chat",),
        "default.chat",
    ),
    RoleDefinition(
        "default.vision",
        "默认视觉模型",
        "没有专项覆盖时供需要图片输入的职责继承。",
        ("text_chat", "vision"),
        "default.vision",
    ),
    RoleDefinition(
        "default.embedding",
        "默认向量模型",
        "没有专项覆盖时供文本向量化继承；不回退到聊天模型。",
        ("embeddings",),
        "default.embedding",
    ),
    _structured("intake.depth", "需求深度", "判断需求确认所需的提问深度。"),
    _structured("intake.interview", "逐题确认", "一次生成一个适合当前用户的问题。"),
    _structured("intake.brief", "需求归纳", "把已确认答案归纳成课程信息。"),
    _structured(
        "intake.explain",
        "选项解释",
        "只解释当前问题的选项，不推进需求会话。",
    ),
    RoleDefinition(
        "materials.vision",
        "文档识别",
        "结合页面图像读取扫描文字、公式、表格与图示；与资料摘要分开配置。",
        ("text_chat", "structured_output", "vision"),
        "default.vision",
    ),
    _structured("materials.summarize", "资料分析与摘要", "生成可追溯的资料主题清单。"),
    _structured("outline.propose", "补章提案", "提出补充章节及理由，但不能自行批准。"),
    RoleDefinition(
        "outline.generate",
        "目录生成",
        "依据已确认需求与批准资料流式生成课程目录。",
        ("text_chat", "structured_output", "streaming"),
        "default.chat",
    ),
    _structured("points.generate", "知识点生成", "依据全局范围、资料与先修生成知识点。"),
    _structured("content.plan", "教学分工", "规划知识卡片、示例、练习和代码实验的必要性。"),
    _structured("content.lesson", "课程讲解", "制作聚焦当前知识点的教学卡片。"),
    _structured("content.examples", "示例", "仅在有助于理解时制作示例。"),
    _structured("content.exercises", "练习", "制作以选择题、判断题为主的练习。"),
    _structured("content.code_lab", "代码实验", "仅在可通过动手编码学习时制作实验。"),
    _structured("content.review", "内容审查", "检查实质性教学问题并给出有限修订建议。"),
    _structured("content.revise", "内容修订", "仅修复审查确认的问题。"),
    _structured("tutor.answer", "讲师答疑", "围绕当前知识卡片回答并控制教学推进。"),
    RoleDefinition(
        "tutor.vision",
        "讲师看图",
        "回答用户附图相关的问题。",
        ("text_chat", "structured_output", "vision"),
        "default.vision",
    ),
    RoleDefinition(
        "retrieval.embed",
        "文本向量化",
        "为资料片段和查询生成兼容的向量；不是聊天 Agent。",
        ("embeddings",),
        "default.embedding",
    ),
)

ROLE_BY_KEY = {item.key: item for item in ROLE_DEFINITIONS}


def get_role(role_key: str) -> RoleDefinition:
    try:
        return ROLE_BY_KEY[role_key]
    except KeyError as error:
        raise ValueError("未知的模型职责。") from error
