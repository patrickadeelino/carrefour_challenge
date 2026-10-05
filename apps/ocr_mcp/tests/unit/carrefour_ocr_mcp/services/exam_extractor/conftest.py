from io import BytesIO

import pytest
from PIL import Image


@pytest.fixture
def checkbox_image(checkbox_request_image: bytes) -> Image.Image:
    with Image.open(BytesIO(checkbox_request_image)) as source:
        return source.convert("RGB")


@pytest.fixture
def partial_mark_image(partial_mark_request_image: bytes) -> Image.Image:
    with Image.open(BytesIO(partial_mark_request_image)) as source:
        return source.convert("RGB")
