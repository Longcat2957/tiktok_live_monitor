import datetime

from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class LiveChatMessageListRequest(_message.Message):
    __slots__ = ("live_chat_id", "hl", "profile_image_size", "max_results", "page_token", "part")
    LIVE_CHAT_ID_FIELD_NUMBER: _ClassVar[int]
    HL_FIELD_NUMBER: _ClassVar[int]
    PROFILE_IMAGE_SIZE_FIELD_NUMBER: _ClassVar[int]
    MAX_RESULTS_FIELD_NUMBER: _ClassVar[int]
    PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    PART_FIELD_NUMBER: _ClassVar[int]
    live_chat_id: str
    hl: str
    profile_image_size: int
    max_results: int
    page_token: str
    part: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, live_chat_id: _Optional[str] = ..., hl: _Optional[str] = ..., profile_image_size: _Optional[int] = ..., max_results: _Optional[int] = ..., page_token: _Optional[str] = ..., part: _Optional[_Iterable[str]] = ...) -> None: ...

class LiveChatMessageListResponse(_message.Message):
    __slots__ = ("kind", "etag", "offline_at", "page_info", "next_page_token", "items", "active_poll_item")
    KIND_FIELD_NUMBER: _ClassVar[int]
    ETAG_FIELD_NUMBER: _ClassVar[int]
    OFFLINE_AT_FIELD_NUMBER: _ClassVar[int]
    PAGE_INFO_FIELD_NUMBER: _ClassVar[int]
    NEXT_PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_POLL_ITEM_FIELD_NUMBER: _ClassVar[int]
    kind: str
    etag: str
    offline_at: str
    page_info: PageInfo
    next_page_token: str
    items: _containers.RepeatedCompositeFieldContainer[LiveChatMessage]
    active_poll_item: LiveChatMessage
    def __init__(self, kind: _Optional[str] = ..., etag: _Optional[str] = ..., offline_at: _Optional[str] = ..., page_info: _Optional[_Union[PageInfo, _Mapping]] = ..., next_page_token: _Optional[str] = ..., items: _Optional[_Iterable[_Union[LiveChatMessage, _Mapping]]] = ..., active_poll_item: _Optional[_Union[LiveChatMessage, _Mapping]] = ...) -> None: ...

class LiveChatMessage(_message.Message):
    __slots__ = ("kind", "etag", "id", "snippet", "author_details")
    KIND_FIELD_NUMBER: _ClassVar[int]
    ETAG_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    SNIPPET_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_DETAILS_FIELD_NUMBER: _ClassVar[int]
    kind: str
    etag: str
    id: str
    snippet: LiveChatMessageSnippet
    author_details: LiveChatMessageAuthorDetails
    def __init__(self, kind: _Optional[str] = ..., etag: _Optional[str] = ..., id: _Optional[str] = ..., snippet: _Optional[_Union[LiveChatMessageSnippet, _Mapping]] = ..., author_details: _Optional[_Union[LiveChatMessageAuthorDetails, _Mapping]] = ...) -> None: ...

class LiveChatMessageAuthorDetails(_message.Message):
    __slots__ = ("channel_id", "channel_url", "display_name", "profile_image_url", "is_verified", "is_chat_owner", "is_chat_sponsor", "is_chat_moderator")
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_URL_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    PROFILE_IMAGE_URL_FIELD_NUMBER: _ClassVar[int]
    IS_VERIFIED_FIELD_NUMBER: _ClassVar[int]
    IS_CHAT_OWNER_FIELD_NUMBER: _ClassVar[int]
    IS_CHAT_SPONSOR_FIELD_NUMBER: _ClassVar[int]
    IS_CHAT_MODERATOR_FIELD_NUMBER: _ClassVar[int]
    channel_id: str
    channel_url: str
    display_name: str
    profile_image_url: str
    is_verified: bool
    is_chat_owner: bool
    is_chat_sponsor: bool
    is_chat_moderator: bool
    def __init__(self, channel_id: _Optional[str] = ..., channel_url: _Optional[str] = ..., display_name: _Optional[str] = ..., profile_image_url: _Optional[str] = ..., is_verified: _Optional[bool] = ..., is_chat_owner: _Optional[bool] = ..., is_chat_sponsor: _Optional[bool] = ..., is_chat_moderator: _Optional[bool] = ...) -> None: ...

class LiveChatMessageSnippet(_message.Message):
    __slots__ = ("type", "live_chat_id", "author_channel_id", "published_at", "has_display_content", "display_message", "text_message_details", "user_banned_details", "super_chat_details", "super_sticker_details", "new_sponsor_details", "member_milestone_chat_details", "membership_gifting_details", "gift_membership_received_details", "poll_details", "gift_details")
    class TypeWrapper(_message.Message):
        __slots__ = ()
        class Type(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            INVALID_TYPE: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            TEXT_MESSAGE_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            TOMBSTONE: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            FAN_FUNDING_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            CHAT_ENDED_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            SPONSOR_ONLY_MODE_STARTED_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            SPONSOR_ONLY_MODE_ENDED_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            NEW_SPONSOR_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            MEMBER_MILESTONE_CHAT_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            MEMBERSHIP_GIFTING_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            GIFT_MEMBERSHIP_RECEIVED_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            USER_BANNED_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            SUPER_CHAT_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            SUPER_STICKER_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            POLL_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
            GIFT_EVENT: _ClassVar[LiveChatMessageSnippet.TypeWrapper.Type]
        INVALID_TYPE: LiveChatMessageSnippet.TypeWrapper.Type
        TEXT_MESSAGE_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        TOMBSTONE: LiveChatMessageSnippet.TypeWrapper.Type
        FAN_FUNDING_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        CHAT_ENDED_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        SPONSOR_ONLY_MODE_STARTED_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        SPONSOR_ONLY_MODE_ENDED_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        NEW_SPONSOR_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        MEMBER_MILESTONE_CHAT_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        MEMBERSHIP_GIFTING_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        GIFT_MEMBERSHIP_RECEIVED_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        USER_BANNED_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        SUPER_CHAT_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        SUPER_STICKER_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        POLL_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        GIFT_EVENT: LiveChatMessageSnippet.TypeWrapper.Type
        def __init__(self) -> None: ...
    TYPE_FIELD_NUMBER: _ClassVar[int]
    LIVE_CHAT_ID_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    PUBLISHED_AT_FIELD_NUMBER: _ClassVar[int]
    HAS_DISPLAY_CONTENT_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TEXT_MESSAGE_DETAILS_FIELD_NUMBER: _ClassVar[int]
    USER_BANNED_DETAILS_FIELD_NUMBER: _ClassVar[int]
    SUPER_CHAT_DETAILS_FIELD_NUMBER: _ClassVar[int]
    SUPER_STICKER_DETAILS_FIELD_NUMBER: _ClassVar[int]
    NEW_SPONSOR_DETAILS_FIELD_NUMBER: _ClassVar[int]
    MEMBER_MILESTONE_CHAT_DETAILS_FIELD_NUMBER: _ClassVar[int]
    MEMBERSHIP_GIFTING_DETAILS_FIELD_NUMBER: _ClassVar[int]
    GIFT_MEMBERSHIP_RECEIVED_DETAILS_FIELD_NUMBER: _ClassVar[int]
    POLL_DETAILS_FIELD_NUMBER: _ClassVar[int]
    GIFT_DETAILS_FIELD_NUMBER: _ClassVar[int]
    type: LiveChatMessageSnippet.TypeWrapper.Type
    live_chat_id: str
    author_channel_id: str
    published_at: str
    has_display_content: bool
    display_message: str
    text_message_details: LiveChatTextMessageDetails
    user_banned_details: LiveChatUserBannedMessageDetails
    super_chat_details: LiveChatSuperChatDetails
    super_sticker_details: LiveChatSuperStickerDetails
    new_sponsor_details: LiveChatNewSponsorDetails
    member_milestone_chat_details: LiveChatMemberMilestoneChatDetails
    membership_gifting_details: LiveChatMembershipGiftingDetails
    gift_membership_received_details: LiveChatGiftMembershipReceivedDetails
    poll_details: LiveChatPollDetails
    gift_details: LiveChatGiftDetails
    def __init__(self, type: _Optional[_Union[LiveChatMessageSnippet.TypeWrapper.Type, str]] = ..., live_chat_id: _Optional[str] = ..., author_channel_id: _Optional[str] = ..., published_at: _Optional[str] = ..., has_display_content: _Optional[bool] = ..., display_message: _Optional[str] = ..., text_message_details: _Optional[_Union[LiveChatTextMessageDetails, _Mapping]] = ..., user_banned_details: _Optional[_Union[LiveChatUserBannedMessageDetails, _Mapping]] = ..., super_chat_details: _Optional[_Union[LiveChatSuperChatDetails, _Mapping]] = ..., super_sticker_details: _Optional[_Union[LiveChatSuperStickerDetails, _Mapping]] = ..., new_sponsor_details: _Optional[_Union[LiveChatNewSponsorDetails, _Mapping]] = ..., member_milestone_chat_details: _Optional[_Union[LiveChatMemberMilestoneChatDetails, _Mapping]] = ..., membership_gifting_details: _Optional[_Union[LiveChatMembershipGiftingDetails, _Mapping]] = ..., gift_membership_received_details: _Optional[_Union[LiveChatGiftMembershipReceivedDetails, _Mapping]] = ..., poll_details: _Optional[_Union[LiveChatPollDetails, _Mapping]] = ..., gift_details: _Optional[_Union[LiveChatGiftDetails, _Mapping]] = ...) -> None: ...

class LiveChatTextMessageDetails(_message.Message):
    __slots__ = ("message_text",)
    MESSAGE_TEXT_FIELD_NUMBER: _ClassVar[int]
    message_text: str
    def __init__(self, message_text: _Optional[str] = ...) -> None: ...

class LiveChatUserBannedMessageDetails(_message.Message):
    __slots__ = ("banned_user_details", "ban_type", "ban_duration_seconds")
    class BanTypeWrapper(_message.Message):
        __slots__ = ()
        class BanType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            PERMANENT: _ClassVar[LiveChatUserBannedMessageDetails.BanTypeWrapper.BanType]
            TEMPORARY: _ClassVar[LiveChatUserBannedMessageDetails.BanTypeWrapper.BanType]
        PERMANENT: LiveChatUserBannedMessageDetails.BanTypeWrapper.BanType
        TEMPORARY: LiveChatUserBannedMessageDetails.BanTypeWrapper.BanType
        def __init__(self) -> None: ...
    BANNED_USER_DETAILS_FIELD_NUMBER: _ClassVar[int]
    BAN_TYPE_FIELD_NUMBER: _ClassVar[int]
    BAN_DURATION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    banned_user_details: ChannelProfileDetails
    ban_type: LiveChatUserBannedMessageDetails.BanTypeWrapper.BanType
    ban_duration_seconds: int
    def __init__(self, banned_user_details: _Optional[_Union[ChannelProfileDetails, _Mapping]] = ..., ban_type: _Optional[_Union[LiveChatUserBannedMessageDetails.BanTypeWrapper.BanType, str]] = ..., ban_duration_seconds: _Optional[int] = ...) -> None: ...

class LiveChatSuperChatDetails(_message.Message):
    __slots__ = ("amount_micros", "currency", "amount_display_string", "user_comment", "tier")
    AMOUNT_MICROS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_DISPLAY_STRING_FIELD_NUMBER: _ClassVar[int]
    USER_COMMENT_FIELD_NUMBER: _ClassVar[int]
    TIER_FIELD_NUMBER: _ClassVar[int]
    amount_micros: int
    currency: str
    amount_display_string: str
    user_comment: str
    tier: int
    def __init__(self, amount_micros: _Optional[int] = ..., currency: _Optional[str] = ..., amount_display_string: _Optional[str] = ..., user_comment: _Optional[str] = ..., tier: _Optional[int] = ...) -> None: ...

class LiveChatSuperStickerDetails(_message.Message):
    __slots__ = ("amount_micros", "currency", "amount_display_string", "tier", "super_sticker_metadata")
    AMOUNT_MICROS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_DISPLAY_STRING_FIELD_NUMBER: _ClassVar[int]
    TIER_FIELD_NUMBER: _ClassVar[int]
    SUPER_STICKER_METADATA_FIELD_NUMBER: _ClassVar[int]
    amount_micros: int
    currency: str
    amount_display_string: str
    tier: int
    super_sticker_metadata: SuperStickerMetadata
    def __init__(self, amount_micros: _Optional[int] = ..., currency: _Optional[str] = ..., amount_display_string: _Optional[str] = ..., tier: _Optional[int] = ..., super_sticker_metadata: _Optional[_Union[SuperStickerMetadata, _Mapping]] = ...) -> None: ...

class LiveChatFanFundingEventDetails(_message.Message):
    __slots__ = ("amount_micros", "currency", "amount_display_string", "user_comment")
    AMOUNT_MICROS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_DISPLAY_STRING_FIELD_NUMBER: _ClassVar[int]
    USER_COMMENT_FIELD_NUMBER: _ClassVar[int]
    amount_micros: int
    currency: str
    amount_display_string: str
    user_comment: str
    def __init__(self, amount_micros: _Optional[int] = ..., currency: _Optional[str] = ..., amount_display_string: _Optional[str] = ..., user_comment: _Optional[str] = ...) -> None: ...

class LiveChatNewSponsorDetails(_message.Message):
    __slots__ = ("member_level_name", "is_upgrade")
    MEMBER_LEVEL_NAME_FIELD_NUMBER: _ClassVar[int]
    IS_UPGRADE_FIELD_NUMBER: _ClassVar[int]
    member_level_name: str
    is_upgrade: bool
    def __init__(self, member_level_name: _Optional[str] = ..., is_upgrade: _Optional[bool] = ...) -> None: ...

class LiveChatMemberMilestoneChatDetails(_message.Message):
    __slots__ = ("member_level_name", "member_month", "user_comment")
    MEMBER_LEVEL_NAME_FIELD_NUMBER: _ClassVar[int]
    MEMBER_MONTH_FIELD_NUMBER: _ClassVar[int]
    USER_COMMENT_FIELD_NUMBER: _ClassVar[int]
    member_level_name: str
    member_month: int
    user_comment: str
    def __init__(self, member_level_name: _Optional[str] = ..., member_month: _Optional[int] = ..., user_comment: _Optional[str] = ...) -> None: ...

class LiveChatMembershipGiftingDetails(_message.Message):
    __slots__ = ("gift_memberships_count", "gift_memberships_level_name")
    GIFT_MEMBERSHIPS_COUNT_FIELD_NUMBER: _ClassVar[int]
    GIFT_MEMBERSHIPS_LEVEL_NAME_FIELD_NUMBER: _ClassVar[int]
    gift_memberships_count: int
    gift_memberships_level_name: str
    def __init__(self, gift_memberships_count: _Optional[int] = ..., gift_memberships_level_name: _Optional[str] = ...) -> None: ...

class LiveChatGiftMembershipReceivedDetails(_message.Message):
    __slots__ = ("member_level_name", "gifter_channel_id", "associated_membership_gifting_message_id")
    MEMBER_LEVEL_NAME_FIELD_NUMBER: _ClassVar[int]
    GIFTER_CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    ASSOCIATED_MEMBERSHIP_GIFTING_MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    member_level_name: str
    gifter_channel_id: str
    associated_membership_gifting_message_id: str
    def __init__(self, member_level_name: _Optional[str] = ..., gifter_channel_id: _Optional[str] = ..., associated_membership_gifting_message_id: _Optional[str] = ...) -> None: ...

class LiveChatPollDetails(_message.Message):
    __slots__ = ("metadata", "status")
    class PollMetadata(_message.Message):
        __slots__ = ("question_text", "options")
        class PollOption(_message.Message):
            __slots__ = ("option_text", "tally")
            OPTION_TEXT_FIELD_NUMBER: _ClassVar[int]
            TALLY_FIELD_NUMBER: _ClassVar[int]
            option_text: str
            tally: int
            def __init__(self, option_text: _Optional[str] = ..., tally: _Optional[int] = ...) -> None: ...
        QUESTION_TEXT_FIELD_NUMBER: _ClassVar[int]
        OPTIONS_FIELD_NUMBER: _ClassVar[int]
        question_text: str
        options: _containers.RepeatedCompositeFieldContainer[LiveChatPollDetails.PollMetadata.PollOption]
        def __init__(self, question_text: _Optional[str] = ..., options: _Optional[_Iterable[_Union[LiveChatPollDetails.PollMetadata.PollOption, _Mapping]]] = ...) -> None: ...
    class PollStatusWrapper(_message.Message):
        __slots__ = ()
        class PollStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            UNKNOWN: _ClassVar[LiveChatPollDetails.PollStatusWrapper.PollStatus]
            ACTIVE: _ClassVar[LiveChatPollDetails.PollStatusWrapper.PollStatus]
            CLOSED: _ClassVar[LiveChatPollDetails.PollStatusWrapper.PollStatus]
        UNKNOWN: LiveChatPollDetails.PollStatusWrapper.PollStatus
        ACTIVE: LiveChatPollDetails.PollStatusWrapper.PollStatus
        CLOSED: LiveChatPollDetails.PollStatusWrapper.PollStatus
        def __init__(self) -> None: ...
    METADATA_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    metadata: LiveChatPollDetails.PollMetadata
    status: LiveChatPollDetails.PollStatusWrapper.PollStatus
    def __init__(self, metadata: _Optional[_Union[LiveChatPollDetails.PollMetadata, _Mapping]] = ..., status: _Optional[_Union[LiveChatPollDetails.PollStatusWrapper.PollStatus, str]] = ...) -> None: ...

class LiveChatGiftDetails(_message.Message):
    __slots__ = ("gift_name", "gift_duration", "jewels_amount", "gift_url", "alt_text", "language", "has_visual_effect", "combo_count")
    GIFT_NAME_FIELD_NUMBER: _ClassVar[int]
    GIFT_DURATION_FIELD_NUMBER: _ClassVar[int]
    JEWELS_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    GIFT_URL_FIELD_NUMBER: _ClassVar[int]
    ALT_TEXT_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    HAS_VISUAL_EFFECT_FIELD_NUMBER: _ClassVar[int]
    COMBO_COUNT_FIELD_NUMBER: _ClassVar[int]
    gift_name: str
    gift_duration: _duration_pb2.Duration
    jewels_amount: int
    gift_url: str
    alt_text: str
    language: str
    has_visual_effect: bool
    combo_count: int
    def __init__(self, gift_name: _Optional[str] = ..., gift_duration: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., jewels_amount: _Optional[int] = ..., gift_url: _Optional[str] = ..., alt_text: _Optional[str] = ..., language: _Optional[str] = ..., has_visual_effect: _Optional[bool] = ..., combo_count: _Optional[int] = ...) -> None: ...

class SuperChatEventSnippet(_message.Message):
    __slots__ = ("channel_id", "supporter_details", "comment_text", "created_at", "amount_micros", "currency", "display_string", "message_type", "is_super_sticker_event", "super_sticker_metadata")
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    SUPPORTER_DETAILS_FIELD_NUMBER: _ClassVar[int]
    COMMENT_TEXT_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_MICROS_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_STRING_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    IS_SUPER_STICKER_EVENT_FIELD_NUMBER: _ClassVar[int]
    SUPER_STICKER_METADATA_FIELD_NUMBER: _ClassVar[int]
    channel_id: str
    supporter_details: ChannelProfileDetails
    comment_text: str
    created_at: str
    amount_micros: int
    currency: str
    display_string: str
    message_type: int
    is_super_sticker_event: bool
    super_sticker_metadata: SuperStickerMetadata
    def __init__(self, channel_id: _Optional[str] = ..., supporter_details: _Optional[_Union[ChannelProfileDetails, _Mapping]] = ..., comment_text: _Optional[str] = ..., created_at: _Optional[str] = ..., amount_micros: _Optional[int] = ..., currency: _Optional[str] = ..., display_string: _Optional[str] = ..., message_type: _Optional[int] = ..., is_super_sticker_event: _Optional[bool] = ..., super_sticker_metadata: _Optional[_Union[SuperStickerMetadata, _Mapping]] = ...) -> None: ...

class SuperStickerMetadata(_message.Message):
    __slots__ = ("sticker_id", "alt_text", "alt_text_language")
    STICKER_ID_FIELD_NUMBER: _ClassVar[int]
    ALT_TEXT_FIELD_NUMBER: _ClassVar[int]
    ALT_TEXT_LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    sticker_id: str
    alt_text: str
    alt_text_language: str
    def __init__(self, sticker_id: _Optional[str] = ..., alt_text: _Optional[str] = ..., alt_text_language: _Optional[str] = ...) -> None: ...

class ChannelProfileDetails(_message.Message):
    __slots__ = ("channel_id", "channel_url", "display_name", "profile_image_url")
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_URL_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    PROFILE_IMAGE_URL_FIELD_NUMBER: _ClassVar[int]
    channel_id: str
    channel_url: str
    display_name: str
    profile_image_url: str
    def __init__(self, channel_id: _Optional[str] = ..., channel_url: _Optional[str] = ..., display_name: _Optional[str] = ..., profile_image_url: _Optional[str] = ...) -> None: ...

class PageInfo(_message.Message):
    __slots__ = ("total_results", "results_per_page")
    TOTAL_RESULTS_FIELD_NUMBER: _ClassVar[int]
    RESULTS_PER_PAGE_FIELD_NUMBER: _ClassVar[int]
    total_results: int
    results_per_page: int
    def __init__(self, total_results: _Optional[int] = ..., results_per_page: _Optional[int] = ...) -> None: ...
