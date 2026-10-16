"""퇴원한 반려견의 자료 보관·삭제. 정책: 퇴원 처리 후 3개월이 지나면 사진·영상 파일과 보호자 연결을 삭제한다.
글로 된 돌봄 기록과 업무 이력은 유지한다. 삭제는 되돌릴 수 없다."""
import sqlite3
from typing import Optional

from .database import now_iso, upload_dir

RETENTION_MONTHS = 3


def _delete_files(paths: list) -> int:
    n = 0
    for p in paths:
        try:
            p.unlink()
            n += 1
        except FileNotFoundError:
            pass
    return n


def purge_dog(conn: sqlite3.Connection, dog_id: int) -> dict:
    """한 마리의 자료를 삭제한다.
    - 이 아이가 태그된 사진: 이 아이의 태그·공개를 지운다. 다른 아이가 함께 찍혀 있으면 사진은 그 아이들을 위해 남기고,
      아무도 남지 않으면 파일과 행을 삭제한다.
    - 프로필 사진(직접 올린 파일), 보호자 연결·읽음 기록·초대 코드를 삭제한다. 보호자 계정 자체는 남는다.
    """
    dog = conn.execute("SELECT * FROM dogs WHERE id=?", (dog_id,)).fetchone()
    files, removed_photos, kept_group = [], 0, 0
    for m in conn.execute("SELECT m.* FROM media m JOIN media_dogs md ON md.media_id=m.id WHERE md.dog_id=?", (dog_id,)).fetchall():
        conn.execute("DELETE FROM media_shares WHERE media_id=? AND dog_id=?", (m["id"], dog_id))
        conn.execute("DELETE FROM media_dogs WHERE media_id=? AND dog_id=?", (m["id"], dog_id))
        if conn.execute("SELECT 1 FROM media_dogs WHERE media_id=?", (m["id"],)).fetchone() is None:
            folder = upload_dir() / "media" / str(m["org_id"])
            files += [folder / m["file"], folder / m["thumb"]]
            conn.execute("DELETE FROM media WHERE id=?", (m["id"],))
            removed_photos += 1
        else:
            kept_group += 1
    # 이 아이의 기록에 첨부됐지만 태그가 모두 다른 아이인 사진은 그 아이들의 것이므로 그대로 둔다.
    profile = dog["photo"] if dog and dog["photo"] and dog["photo"].startswith("uploads/dogs/") else None
    if profile:
        files.append(upload_dir() / "dogs" / profile.rsplit("/", 1)[1])
    if dog and dog["photo"]:
        conn.execute("UPDATE dogs SET photo=NULL WHERE id=?", (dog_id,))
    links = conn.execute("DELETE FROM guardian_dogs WHERE dog_id=?", (dog_id,)).rowcount
    conn.execute("DELETE FROM parent_reads WHERE dog_id=?", (dog_id,))
    conn.execute("DELETE FROM invites WHERE dog_id=?", (dog_id,))
    conn.execute("UPDATE dogs SET purged_at=?, attending=0 WHERE id=?", (now_iso(), dog_id))
    conn.commit()                       # DB 변경을 확정한 뒤 파일을 지운다(파일 삭제 실패가 DB 상태를 되돌리지 않도록)
    deleted = _delete_files(files)
    return {"dog_id": dog_id, "name": dog["name"] if dog else "", "photos_deleted": removed_photos, "group_photos_kept": kept_group,
            "profile_photo_deleted": bool(profile), "guardian_links_deleted": links, "files_deleted": deleted}


def purge_due(conn: sqlite3.Connection, org_id: Optional[int] = None) -> list[dict]:
    """삭제 예정일이 지난(아직 삭제되지 않은) 퇴원 반려견의 자료를 삭제한다. org_id가 없으면 전체."""
    sql = "SELECT id FROM dogs WHERE purged_at IS NULL AND purge_after IS NOT NULL AND purge_after <= ?"
    args: list = [now_iso()]
    if org_id is not None:
        sql += " AND org_id=?"
        args.append(org_id)
    return [purge_dog(conn, r["id"]) for r in conn.execute(sql, args).fetchall()]
