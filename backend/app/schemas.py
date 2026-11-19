from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")


def _email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not _EMAIL.match(v):
        raise ValueError("Enter a valid email address.")
    return v


EmailStr = Annotated[str, AfterValidator(_email)]


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class GenerateSettings(BaseModel):
    count: int = Field(default=6, ge=1, le=20)
    min_dur: float = Field(default=20, ge=5, le=170)
    max_dur: float = Field(default=60, ge=8, le=180)
    genre: Literal["auto", "podcast", "gaming", "education", "tutorial", "entertainment", "vlog", "review"] = "auto"
    mood: Literal["any", "funny", "emotional", "intense", "informative", "inspiring"] = "any"
    position: Literal["any", "start", "middle", "end"] = "any"
    aspect: Literal["9:16", "1:1", "4:5", "16:9"] = "9:16"
    crop_mode: Literal["auto", "center", "fit", "facecam"] = "auto"
    captions: bool = True
    caption_preset: str = Field(default="bold_creator", max_length=40)
    caption_transition: Literal["none", "fade_up", "fade_down", "fade_left", "fade_right", "bounce"] = "none"
    caption_effect: Literal["none", "glow", "shadow3d", "typewriter", "tilt"] = "none"
    keyword_emphasis: bool = True
    # What to look for, in the creator's own words ("moments where she shares concrete advice").
    instructions: str = Field(default="", max_length=600)
    zoom_start: bool = False
    zoom_key_phrases: bool = True
    progress_bar: bool = False
    logo_key: str | None = Field(default=None, max_length=200)
    logo_position: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = "top_right"
    music_key: str | None = Field(default=None, max_length=200)
    music_volume: float = Field(default=0.16, ge=0.02, le=1.0)
    transcript_only: bool = False  # Transcript generator: stop after speech-to-text
    language: str = Field(default="auto", max_length=8)
    quality: Literal["draft", "standard", "high"] = "standard"
    silence_removal: bool = False
    context_padding: bool = True
    hook_title: bool = True
    platforms: list[Literal["youtube", "instagram", "tiktok", "linkedin", "facebook", "x"]] = Field(
        default_factory=lambda: ["youtube", "instagram", "tiktok"]
    )
    tone: Literal["compelling", "professional", "funny", "energetic", "educational", "storytelling"] = "compelling"
    use_llm: bool = True

    @field_validator("caption_preset")
    @classmethod
    def _preset(cls, v: str) -> str:
        from .pipeline.captions import PRESETS

        if v not in PRESETS:
            raise ValueError("Unknown caption style.")
        return v

    @model_validator(mode="after")
    def _durations(self) -> GenerateSettings:
        if self.max_dur < self.min_dur + 3:
            raise ValueError("Maximum duration must be at least 3 seconds longer than the minimum.")
        return self


class UrlCheckIn(BaseModel):
    url: str = Field(max_length=2000)


class ProjectCreateIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    upload_id: str | None = None
    url: str | None = Field(default=None, max_length=2000)
    settings: GenerateSettings = Field(default_factory=GenerateSettings)
    start: bool = True  # immediately queue the AI Generate job

    @model_validator(mode="after")
    def _one_source(self) -> ProjectCreateIn:
        if bool(self.upload_id) == bool(self.url):
            raise ValueError("Provide either an uploaded file or a video link.")
        return self


class UploadInitIn(BaseModel):
    filename: str = Field(max_length=255)
    size: int = Field(gt=0)

    @field_validator("filename")
    @classmethod
    def _ext(cls, v: str) -> str:
        if not v.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi")):
            raise ValueError("Supported formats: MP4, MOV, MKV, WEBM, M4V, AVI.")
        return v


class ClipEditIn(BaseModel):
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)
    title: str | None = Field(default=None, max_length=200)
    edits: dict[str, Any] | None = None
    render: bool = True


class PublishIn(BaseModel):
    platforms: list[str] = Field(
        default_factory=lambda: ["youtube", "instagram", "tiktok", "linkedin", "facebook", "x"]
    )
    tone: str = "compelling"


class PublishUpdateIn(BaseModel):
    publish: dict[str, Any]


class FeedbackIn(BaseModel):
    rating: Literal[-1, 0, 1]
    note: str | None = Field(default=None, max_length=500)


class FavoriteIn(BaseModel):
    favorite: bool


class AssistantIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    project_id: str
    clip_id: str | None = None
    execute: bool = True


class BrandKitIn(BaseModel):
    caption_preset: str | None = None
    caption_style: dict[str, Any] | None = None
    watermark: str | None = Field(default=None, max_length=60)
    name: str | None = Field(default=None, max_length=120)
    # Social profiles: platform -> handle or channel URL (shown in the post drawer)
    socials: dict[str, str] | None = None
    timezone: str | None = Field(default=None, max_length=64)


class PostIn(BaseModel):
    status: Literal["draft", "scheduled", "posted"]
    scheduled_at: str | None = Field(default=None, max_length=40)  # ISO 8601 with offset
    timezone: str | None = Field(default=None, max_length=64)
    platforms: dict[str, dict[str, Any]] = Field(default_factory=dict)
