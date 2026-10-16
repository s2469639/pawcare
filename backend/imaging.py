"""사진 검증·정리. 업로드된 이미지는 반드시 디코딩해 보고(형식 위조·손상 거부), 회전을 적용한 뒤
WebP로 새로 인코딩한다. 새로 저장하므로 EXIF(위치·기기 정보)와 숨겨진 데이터가 모두 사라진다."""
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 40_000_000          # 디코딩 전 헤더의 해상도 기준(이미지 폭탄 방어)
FULL_SIDE, THUMB_SIDE = 1600, 480
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class BadImage(Exception):
    pass


class TooBig(Exception):
    pass


def _encode(im: Image.Image, side: int) -> tuple[bytes, tuple[int, int]]:
    c = im.copy()
    c.thumbnail((side, side), Image.LANCZOS)
    out = BytesIO()
    c.save(out, "WEBP", quality=85, method=4)      # exif/icc_profile을 넘기지 않으므로 메타데이터는 저장되지 않는다
    return out.getvalue(), c.size


def process_photo(data: bytes) -> dict:
    try:
        im = Image.open(BytesIO(data))
        if im.format not in ALLOWED_FORMATS:
            raise BadImage("지원하지 않는 사진 형식입니다.")
        if im.size[0] * im.size[1] > MAX_PIXELS:
            raise TooBig("사진 해상도가 너무 큽니다.")
        im.load()                                   # 잘린·손상된 파일은 여기서 실패한다
    except (BadImage, TooBig):
        raise
    except Image.DecompressionBombError as e:
        raise TooBig("사진 해상도가 너무 큽니다.") from e
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as e:
        raise BadImage("사진 파일이 올바르지 않습니다.") from e
    im = ImageOps.exif_transpose(im)               # 촬영 방향 적용(이후 메타데이터는 버려진다)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if ("A" in im.mode or "transparency" in im.info) else "RGB")
    full, size = _encode(im, FULL_SIDE)
    thumb, _ = _encode(im, THUMB_SIDE)
    return {"full": full, "thumb": thumb, "width": size[0], "height": size[1]}
