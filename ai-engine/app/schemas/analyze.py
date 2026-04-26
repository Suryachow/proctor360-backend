from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    image_base64: str
    include_advanced: bool = False
    reference_face_image_base64: str | None = None


class VerifyIdentityRequest(BaseModel):
    registered_face_image_base64: str
    live_image_base64: str
    id_card_image_base64: str
