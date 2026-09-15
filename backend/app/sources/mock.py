import asyncio

from ..models import Comment, Status, User
from ..websocket import WebSocketManager, enqueue_comment

SAMPLES = [
    ("민수", "minsu123", "검정색도 있나요?"),
    ("지연", "jiyeon", "안녕하세요! 오늘 방송도 잘 보고 있어요 💚"),
    ("Alex", "alex_live", "Hello from London! This looks amazing 🙌"),
    ("", "new_viewer", "배송은 얼마나 걸리나요?\n제주도도 가능한가요?"),
    ("별빛 ✨", "star_light", "정말 예뻐요 🥰💖🎉 " * 8),
    ("긴 댓글", "long_text", "아주 긴 한글 댓글 줄바꿈 확인입니다. " * 18),
    ("링크", "url_test", "https://example.com/" + "long-path-without-spaces" * 15),
    ("텍스트", "safe_text", '<script>alert("댓글은 일반 텍스트입니다")</script>'),
]


class MockSource:
    def __init__(
        self, queue: asyncio.Queue[Comment], manager: WebSocketManager, interval: float
    ) -> None:
        self.queue = queue
        self.manager = manager
        self.interval = interval

    async def run(self) -> None:
        self.manager.set_status(
            Status(source="mock", state="connected", message="모의 댓글 수신 중")
        )
        index = 0
        while True:
            nickname, unique_id, body = SAMPLES[index % len(SAMPLES)]
            enqueue_comment(
                self.queue, Comment(user=User(nickname=nickname, unique_id=unique_id), comment=body)
            )
            index += 1
            await asyncio.sleep(self.interval)
