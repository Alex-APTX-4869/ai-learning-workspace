"""实际 LangChain/HTTP 协议验收；只连接本机替身端点，不使用外部额度。"""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app import create_app  # noqa: F401
from backend.ai.client import generate_json_messages, stream_text_messages
from backend.database import Base
from backend.providers import routing
from backend.providers.models import LlmProvider, LLMModelConfig, LLMRoleBinding


class Answer(BaseModel):
    answer: str


class RoutingHTTPTests(unittest.TestCase):
    def test_different_endpoints_models_and_frozen_workflow_routes(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append((self.server.server_port, self.path, request["model"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream" if request.get("stream") else "application/json")
                self.end_headers()
                common = {"id": "test", "created": 1, "model": request["model"]}
                if request.get("stream"):
                    payload = {**common, "object": "chat.completion.chunk", "choices": [
                        {"index": 0, "delta": {"content": "outline"}, "finish_reason": None}]}
                    self.wfile.write(("data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n").encode())
                else:
                    payload = {**common, "object": "chat.completion", "choices": [
                        {"index": 0, "message": {"role": "assistant", "content": '{"answer":"tutor"}'}, "finish_reason": "stop"}]}
                    self.wfile.write(json.dumps(payload).encode())

        servers = [ThreadingHTTPServer(("127.0.0.1", 0), Handler) for _ in range(2)]
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                engine = create_engine(f"sqlite:///{directory}/test.db")
                Base.metadata.create_all(engine)
                try:
                    with Session(engine) as db:
                        for index, role in enumerate(["tutor.answer", "outline.generate"]):
                            provider = LlmProvider(name=role, base_url=f"http://127.0.0.1:{servers[index].server_port}/v1",
                                                   model="legacy", key_ref=f"local-test-{index}", is_active=False)
                            db.add(provider)
                            db.flush()
                            model = LLMModelConfig(provider_id=provider.id, label=role, model=f"model-{index}",
                                                   capabilities_json=routing.legacy_capabilities(), runtime_policy_json={}, is_enabled=True, revision=1)
                            db.add(model)
                            db.flush()
                            db.add(LLMRoleBinding(scope_type="global", scope_key="global", role_key=role,
                                                  model_config_id=model.id, revision=1))
                        db.commit()
                        frozen = routing.resolve_routing_snapshot(db, ["tutor.answer", "outline.generate"])
                        binding = db.scalar(select(LLMRoleBinding).where(LLMRoleBinding.role_key == "tutor.answer"))
                        binding.model_config_id = model.id
                        db.commit()
                    with patch.object(routing, "get_engine", return_value=engine), patch.object(routing.secrets, "get_api_key", return_value="local-test"):
                        answer = generate_json_messages("test", "test", Answer, role="tutor.answer", snapshot=frozen)
                        chunks = list(stream_text_messages("test", "test", role="outline.generate", snapshot=frozen))
                    self.assertEqual(answer.answer, "tutor")
                    self.assertEqual("".join(chunks), "outline")
                    self.assertEqual(received, [(servers[0].server_port, "/v1/chat/completions", "model-0"),
                                                (servers[1].server_port, "/v1/chat/completions", "model-1")])
                finally:
                    engine.dispose()
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
