"""显式授权后用合成需求调用现有访谈模型三次；不创建/修改用户会话。"""
import argparse
import json
from sqlalchemy.orm import Session
from backend.database import get_engine
from backend.providers.routing import resolve_routing_snapshot
from backend.ai.client import generate_json_messages
from backend.intake.prompts import interview_question_messages
from backend.intake.extensions import assess
from backend.intake.schemas import DepthOption, GeneratedQuestion, IntakeAnswer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--confirm-live', action='store_true', help='同意三次合成需求模型请求，可能计费')
    if not parser.parse_args().confirm_live:
        parser.error('需要 --confirm-live；不会自动调用模型')
    with Session(get_engine()) as db:
        snapshot = resolve_routing_snapshot(db, ['intake.interview'])
    depth = DepthOption(id='test', title='标准', description='仅合成验收', question_count=3, recommended=True)
    cases = [
        ('scope', 'FastAPI 学习', '已确认：会基础 Python；课程必须从 HTTP 和 FastAPI 基础开始，配练习，完成课程管理接口。每周六小时，项目验收，无考试。尚未决定这期是否进一步学部署与生产运维。不能用选进阶来取消基础。'),
        ('exam_fact', 'IT5005 复习', '已确认从零补基础，覆盖概念、公式理解和计算练习，复习已上传的第二、四章。讲义含概率、损失函数和梯度。尚未明确考试或作业是否要求写 Python；讲义内容不是考试要求的证据。'),
    ]
    for label, name, intro in cases:
        system, payload = interview_question_messages(name=name, intro=intro, selected_depth=depth,
            answers=[], question_number=1, question_count=3)
        result = generate_json_messages(system, payload, GeneratedQuestion, role='intake.interview', snapshot=snapshot)
        print(json.dumps({'case':label,'question':result.model_dump()},ensure_ascii=False),flush=True)
    answer = IntakeAnswer(question_id='q1', focus_key='code_requirement', question_text='课程有明确要求提交代码吗？',
        baseline='基础、概念和计算均纳入', answer_type='custom', answer='不知道，老师还没发考试和作业说明，其他需求都已确认。')
    result = assess(name='IT5005 复习', intro='基础、概念和计算都学，从零开始，每周六小时；其余范围、学习方式和期限均已确认。',
        answers=[answer], question_count=1, history=[], snapshot=snapshot)
    print(json.dumps({'case':'unknown_is_not_ambiguity','extra_question':result},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
