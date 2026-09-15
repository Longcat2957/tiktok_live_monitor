from typing import Protocol


class CommentSource(Protocol):
    async def run(self) -> None: ...
