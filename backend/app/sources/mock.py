import asyncio
from collections.abc import Iterator
from typing import Literal

from ..models import Activity, Badge, Comment, LiveInfo, User
from .base import SourceSink

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
        self,
        sink: SourceSink,
        interval: float,
        sequence: Iterator[int],
    ) -> None:
        self.sink = sink
        self.interval = interval
        self.sequence = sequence

    async def run(self) -> None:
        self.sink.status("connected", "모의 댓글 수신 중")
        step = 0
        while True:
            phase = step % 24
            state: Literal["live", "paused", "ended"] = (
                "paused" if phase in (12, 13) else "ended" if phase in (20, 21) else "live"
            )
            self.sink.live(
                LiveInfo(
                    state=state,
                    viewers=128 + step % 37,
                    likes=1200 + step * 17,
                )
            )
            if state == "live":
                index = next(self.sequence)
                nickname, unique_id, body = SAMPLES[index % len(SAMPLES)]
                badges = []
                if index % 3 != 2:
                    badges.append(Badge(kind="subscriber"))
                if index % 3 != 0:
                    badges.append(Badge(kind="fan", level=index % 25 + 1))
                user = User(
                    nickname=nickname,
                    unique_id=unique_id,
                    badges=badges,
                    avatar_url=f"/demo-avatar-{index % 3}.svg" if index % 4 != 3 else None,
                )
                self.sink.publish(Comment(user=user, comment=f"[데모 #{index + 1}] {body}"))
                activity_kind = {2: "gift", 4: "follow", 6: "share", 8: "subscribe"}.get(phase)
                if activity_kind is not None:
                    self.sink.publish(
                        Activity.model_validate(
                            {
                                "kind": activity_kind,
                                "user": user,
                                "gift_name": "장미",
                                "count": 5 if activity_kind == "gift" else 1,
                            }
                        )
                    )
            step += 1
            await asyncio.sleep(self.interval)
