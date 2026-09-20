import unittest
from unittest.mock import patch
from backend.learning.schemas import PointContent, ContentReview, SectionTeachingPlan
from backend.learning.quality import language_issues, exercise_type_issues
from backend.workflows.content import review_point

class ContentQualityTests(unittest.TestCase):
    def content(self, body):
        return PointContent(lesson_markdown='unused',lesson_cards=[{'title':'类型转换','body_markdown':body}],summary='test')

    def test_json_literal_cannot_be_published_as_python(self):
        draft=self.content('```python\n{"active": true, "remark": null}\n```')
        with patch('backend.workflows.content._generate_for_role',return_value=ContentReview(approved=True)):
            result=review_point({},SectionTeachingPlan.model_construct(section_goal='test',point_plans=[]),draft)
        self.assertFalse(result.approved)
        self.assertIn('类型转换',result.issues[0])
        self.assertTrue(result.revision_instructions)

    def test_valid_python_json_and_strings_are_not_flagged(self):
        for body in ['```json\n{"active": true,"remark":null}\n```',
                     '```python\n{"active": True,"remark":None}\n```',
                     '```python\nprint("true false null")\n```']:
            self.assertEqual(language_issues(self.content(body)),[])

    def test_python_values_in_json_are_reported(self):
        self.assertTrue(language_issues(self.content('```json\n{"active": True}\n```')))

    def test_choice_and_judgment_stay_separate(self):
        from backend.learning.schemas import ContentExercise
        content=self.content('解释')
        exercise=ContentExercise(kind='single_choice',question='字典用键读取值，对吗？',
            options=[{'label':'A','text':'正确','correct':True},{'label':'B','text':'错误','correct':False}],
            answer='正确',explanation='字典用键读取。')
        content.exercises=[exercise]
        self.assertTrue(exercise_type_issues(content))
        content.exercises=[exercise.model_copy(update={'kind':'true_false'})]
        self.assertEqual(exercise_type_issues(content),[])
        content.exercises=[ContentExercise(kind='single_choice',question='怎样读取字典的 name？',
            options=[{'label':'A','text':"course['name']",'correct':True},{'label':'B','text':'course[0]','correct':False}],
            answer='A',explanation='按键读取。')]
        self.assertEqual(exercise_type_issues(content),[])

    def test_combined_judgments_cannot_be_disguised_as_choices(self):
        from backend.learning.schemas import ContentExercise
        content=self.content('解释')
        content.exercises=[ContentExercise(kind='single_choice', question='两句话分别是否正确？',
            options=[{'label':'A','text':'①正确，②错误','correct':True},
                     {'label':'B','text':'①错误，②正确','correct':False}],
            answer='A', explanation='分别分析。')]
        self.assertIn('正误组合', exercise_type_issues(content)[0])

    def test_solution_questions_cannot_include_choices(self):
        from pydantic import ValidationError
        from backend.learning.schemas import ContentExercise
        with self.assertRaises(ValidationError):
            ContentExercise(kind='short_answer', question='解释原因',
                options=[{'label':'A','text':'正确','correct':True}],
                answer='参考思路', explanation='解析')
