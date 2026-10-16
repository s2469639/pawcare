import io
import os

from PIL import Image

from .conftest import ADMIN, AFTERNOON, MORNING, OTHER_ORG, PARENT_BORI

BORI_RECORD = 2        # 보리의 배변 기록(샘플)


def jpeg(w=300, h=200, orientation=None, gps=False, color=(200, 120, 60)):
    im = Image.new("RGB", (w, h), color)
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"                      # Make
    if orientation:
        exif[0x0112] = orientation
    if gps:
        gps_ifd = exif.get_ifd(0x8825)
        gps_ifd[1], gps_ifd[2], gps_ifd[3], gps_ifd[4] = "N", (37.0, 33.0, 59.0), "E", (126.0, 58.0, 41.0)
    out = io.BytesIO()
    im.save(out, "JPEG", exif=exif.tobytes())
    return out.getvalue()


def png(w=64, h=64):
    out = io.BytesIO(); Image.new("RGBA", (w, h), (10, 200, 10, 128)).save(out, "PNG"); return out.getvalue()


def up(client, data, ctype="image/jpeg", record=BORI_RECORD, dogs=None, headers=MORNING):
    url = f"/api/records/{record}/media" + (f"?dog_ids={dogs}" if dogs is not None else "")
    return client.post(url, content=data, headers={**headers, "Content-Type": ctype})


def stored(tmp_path, org=1):
    return sorted((tmp_path / "uploads" / "media" / str(org)).glob("*")) if (tmp_path / "uploads" / "media" / str(org)).exists() else []


# ---------------- 업로드 · 메타데이터 제거 ----------------
def test_upload_strips_exif_and_gps_and_reencodes(client, tmp_path):
    data = jpeg(gps=True)
    assert b"SecretCameraMaker" in data and b"Exif" in data                 # 원본에는 기기·위치 정보가 있음
    r = up(client, data)
    assert r.status_code == 201
    m = r.json()
    assert m["dog_ids"] == [1] and m["dog_names"] == ["보리"] and (m["width"], m["height"]) == (300, 200)
    files = stored(tmp_path)
    assert len(files) == 2                                                    # 원본 크기 + 썸네일
    for f in files:
        raw = f.read_bytes()
        assert raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"                    # 항상 WebP로 새로 인코딩
        assert b"SecretCameraMaker" not in raw and b"Exif" not in raw and b"EXIF" not in raw
        assert not dict(Image.open(io.BytesIO(raw)).getexif())                # 메타데이터 없음


def test_orientation_is_applied_before_metadata_is_dropped(client):
    m = up(client, jpeg(200, 100, orientation=6)).json()                     # 촬영 방향 90도 회전 표시
    assert (m["width"], m["height"]) == (100, 200)


def test_png_with_alpha_and_large_photo_is_resized(client, tmp_path):
    assert up(client, png(), "image/png").status_code == 201
    big = io.BytesIO(); Image.new("RGB", (3200, 2400), (1, 2, 3)).save(big, "JPEG", quality=30)
    m = up(client, big.getvalue()).json()
    assert max(m["width"], m["height"]) == 1600 and m["width"] / m["height"] == 4 / 3        # 긴 변 1600px, 비율 유지
    thumbs = [f for f in stored(tmp_path) if f.name.endswith("-t.webp")]
    assert all(max(Image.open(f).size) <= 480 for f in thumbs)


# ---------------- 거부해야 하는 것들 ----------------
def test_rejects_fake_corrupt_and_disallowed_files(client, tmp_path):
    assert up(client, b"<html><script>alert(1)</script></html>", "image/png").status_code == 415      # 형식 위조
    assert up(client, b"<svg onload=alert(1)>", "image/svg+xml").status_code == 415
    assert up(client, jpeg(), "text/plain").status_code == 415
    whole = jpeg()
    assert up(client, whole[: len(whole) // 2], "image/jpeg").status_code == 415                        # 중간에 잘린 파일
    gif = io.BytesIO(); Image.new("P", (8, 8)).save(gif, "GIF")
    assert up(client, gif.getvalue(), "image/png").status_code == 415                                   # 허용하지 않는 형식
    assert up(client, b"", "image/jpeg").status_code == 415
    assert stored(tmp_path) == []                                                                       # 실패하면 파일이 남지 않음
    assert client.get(f"/api/records/{BORI_RECORD}/media", headers=MORNING).json() == []


def test_rejects_oversized_bytes_and_pixel_bombs(client, tmp_path):
    assert up(client, jpeg() + b"\0" * 2_000_001).status_code == 413
    bomb = io.BytesIO(); Image.new("1", (10000, 10000)).save(bomb, "PNG")          # 파일은 작지만 1억 화소
    assert len(bomb.getvalue()) < 100_000
    r = up(client, bomb.getvalue(), "image/png")
    assert r.status_code == 413 and "해상도" in r.json()["detail"]
    assert stored(tmp_path) == []


def test_max_ten_photos_per_record(client):
    for _ in range(10):
        assert up(client, png()).status_code == 201
    r = up(client, png())
    assert r.status_code == 409 and "10장" in r.json()["detail"]
    assert up(client, png(), record=1).status_code == 201                          # 다른 기록은 별도로 센다


# ---------------- 태그 ----------------
def test_tags_default_custom_and_validation(client):
    assert up(client, png()).json()["dog_ids"] == [1]
    both = up(client, png(), dogs="1,2").json()
    assert both["dog_ids"] == [1, 2] and both["dog_names"] == ["보리", "두부"]
    assert up(client, png(), dogs="2,2,2").json()["dog_ids"] == [2]                 # 중복 제거
    assert up(client, png(), dogs="abc").status_code == 422
    assert up(client, png(), dogs="6").status_code == 404                           # 다른 유치원 반려견(구름)
    assert up(client, png(), dogs="999").status_code == 404
    mid = both["id"]
    r = client.patch(f"/api/media/{mid}", json={"dog_ids": [3, 4]}, headers=AFTERNOON)
    assert r.status_code == 200 and r.json()["dog_ids"] == [3, 4]
    assert client.patch(f"/api/media/{mid}", json={"dog_ids": []}, headers=MORNING).status_code == 422   # 최소 한 마리
    assert client.patch(f"/api/media/{mid}", json={"dog_ids": [6]}, headers=MORNING).status_code == 404


def test_tagged_photo_appears_in_other_dogs_media_and_record_views(client):
    mid = up(client, png(), dogs="1,3").json()["id"]                                # 보리 기록에 첨부, 보리·모카 태그
    assert mid in [m["id"] for m in client.get("/api/dogs/3/media", headers=MORNING).json()]       # 모카 프로필에도 보임
    assert mid not in [m["id"] for m in client.get("/api/dogs/2/media", headers=MORNING).json()]
    rec = [r for r in client.get("/api/dogs/1/records", headers=MORNING).json() if r["id"] == BORI_RECORD][0]
    assert [m["id"] for m in rec["media"]] == [mid]
    assert client.get("/api/dogs/6/media", headers=MORNING).status_code == 404       # 다른 유치원 반려견


# ---------------- 열람 권한 ----------------
def test_file_access_is_limited_to_same_org_staff(client):
    mid = up(client, png()).json()["id"]
    url = f"/api/media/{mid}/file"
    ok = client.get(url, headers=AFTERNOON)
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/webp" and ok.headers["cache-control"].startswith("private")
    assert ok.headers["x-content-type-options"] == "nosniff"
    assert Image.open(io.BytesIO(client.get(url + "?size=thumb", headers=MORNING).content)).size[0] <= 480
    assert client.get(url).status_code == 401                                        # 로그인 안 함
    assert client.get(url, headers=PARENT_BORI).status_code == 403                   # 보호자: 아직 공개 기능 없음(M3 이후)
    assert client.get(url, headers=OTHER_ORG).status_code == 404                     # 다른 유치원: 존재 여부도 모름
    assert client.get("/api/media/999/file", headers=MORNING).status_code == 404
    assert client.get(url + "?size=huge", headers=MORNING).status_code == 422
    assert client.get(f"/api/records/{BORI_RECORD}/media", headers=OTHER_ORG).status_code == 404
    assert up(client, png(), headers=OTHER_ORG).status_code == 404                    # 다른 유치원 기록에 첨부 불가
    assert up(client, png(), headers=PARENT_BORI).status_code == 403
    assert up(client, png(), headers={"Authorization": "Bearer nope"}).status_code == 401


def test_delete_removes_files_and_rows(client, tmp_path):
    mid = up(client, png()).json()["id"]
    assert len(stored(tmp_path)) == 2
    assert client.delete(f"/api/media/{mid}", headers=OTHER_ORG).status_code == 404
    assert len(stored(tmp_path)) == 2
    assert client.delete(f"/api/media/{mid}", headers=ADMIN).status_code == 200
    assert stored(tmp_path) == []
    assert client.get(f"/api/media/{mid}/file", headers=MORNING).status_code == 404
    assert client.get(f"/api/records/{BORI_RECORD}/media", headers=MORNING).json() == []
    from backend.database import connect
    db = connect(); n = db.execute("SELECT COUNT(*) FROM media_dogs").fetchone()[0]; db.close()
    assert n == 0                                                                     # 태그 행도 함께 삭제됨
