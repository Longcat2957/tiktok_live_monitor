import asyncio
from collections.abc import Iterator

from ..schemas.events import Activity, Badge, Comment, LiveInfo, User
from .event_sink import EventSink

SAMPLES = [
    ("민수", "minsu123", "안녕하세요! 👋"),
    ("지연", "jiyeon", "안녕하세요! 오늘 방송도 잘 보고 있어요 💚"),
    ("Alex", "alex_live", "Love this LIVE! 🌹"),
    ("", "new_viewer", "처음 왔어요. 반가워요!"),
    ("별빛 ✨", "star_light", "Rose 보내고 응원할게요 🌹"),
    ("서연", "seoyeon", "@minsu123 같이 봐요!"),
]
ACTIVITIES = {
    0: ("gift", 1),
    3: ("follow", 1),
    5: ("gift", 5),
    7: ("share", 1),
    9: ("subscribe", 1),
    11: ("gift", 25),
}


class DemoStream:
    def __init__(
        self,
        sink: EventSink,
        interval: float,
        sequence: Iterator[int],
    ) -> None:
        self.sink = sink
        self.interval = interval
        self.sequence = sequence

    async def run(self) -> None:
        self.sink.status("connected", "모의 댓글 수신 중")
        while True:
            index = next(self.sequence)
            self.sink.live(
                LiveInfo(
                    state="live",
                    viewers=128 + index % 37,
                    likes=1200 + index * 17,
                )
            )
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
            activity = ACTIVITIES.get(index % 12)
            if activity is not None:
                kind, quantity = activity
                self.sink.publish(
                    Activity.model_validate(
                        {
                            "kind": kind,
                            "user": user,
                            "gift_name": "Rose" if kind == "gift" else "선물",
                            "gift_image_url": "/demo-gift-rose.webp" if kind == "gift" else None,
                            "count": quantity,
                        }
                    )
                )
            await asyncio.sleep(self.interval)
