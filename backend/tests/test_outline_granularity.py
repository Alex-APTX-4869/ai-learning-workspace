import unittest
from backend.ai.prompts import OUTLINE_GRANULARITY_RULES, COURSE_RULES, outline_messages
from backend.ai.schemas import CourseRequest
from backend.outlines.prompts import outline_stream_messages
from backend.intake.prompts import brief_messages
from backend.intake.schemas import DepthOption


class OutlineGranularityTests(unittest.TestCase):
    def test_saved_and_preview_outlines_share_scope_and_granularity(self):
        preview, _ = outline_messages(CourseRequest(topic='HTTP', intro='20 分钟'))
        streamed, _ = outline_stream_messages({'course_brief': None})
        for rules in (COURSE_RULES, OUTLINE_GRANULARITY_RULES):
            self.assertIn(rules, preview)
            self.assertIn(rules, streamed)
        self.assertIn('不设置或暗示统一的章节/小节数量', streamed)

    def test_brief_distinguishes_missing_material_from_excluded_scope(self):
        system, _ = brief_messages(name='HTTP', intro='读懂响应', answers=[],
            selected_depth=DepthOption(id='custom', title='快速', description='一题',
                                       question_count=1, recommended=True))
        self.assertIn('不能自动改写成 scope_out', system)
        self.assertIn('不能假装用户已批准', system)
