"""Tests for the append-only integration comment thread + image attachments."""
import struct
import zlib

from .conftest import ADMIN, USER, create_integration


def _png_bytes() -> bytes:
    """A minimal valid 1x1 PNG."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00")
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _post_comment(client, iid, headers, body="", files=None):
    return client.post(
        f"/api/integrations/{iid}/comments",
        data={"body": body},
        files=files or [],
        headers=headers,
    )


def test_any_user_can_add_text_comment(client):
    i = create_integration(client, "Commentable").json()
    r = _post_comment(client, i["id"], USER, body="general note")
    assert r.status_code == 201
    body = r.json()
    assert body["body"] == "general note"
    assert body["author_email"] == "user@example.com"
    assert body["attachments"] == []
    assert _post_comment(client, i["id"], ADMIN, body="admin note").status_code == 201


def test_comments_listed_newest_first_and_paginated(client):
    i = create_integration(client, "Threaded").json()
    for n in range(3):
        _post_comment(client, i["id"], USER, body=f"note {n}")
    res = client.get(f"/api/integrations/{i['id']}/comments?page_size=2", headers=USER).json()
    assert res["total"] == 3
    assert len(res["items"]) == 2
    assert res["items"][0]["body"] == "note 2"  # newest first


def test_comment_writes_audit_entry(client):
    i = create_integration(client, "Logged").json()
    _post_comment(client, i["id"], USER, body="tech note")
    aud = client.get(f"/api/integrations/{i['id']}/audit", headers=ADMIN).json()["items"]
    commented = [e for e in aud if e["action"] == "commented"]
    assert commented and "tech note" in (commented[0]["new_value"] or "")
    assert commented[0]["changed_by_email"] == "user@example.com"
    feed = client.get("/api/audit?action=commented", headers=ADMIN).json()
    assert feed["total"] >= 1


def test_empty_comment_rejected(client):
    i = create_integration(client, "NoBlank").json()
    # No text and no files.
    assert _post_comment(client, i["id"], USER, body="   ").status_code == 422
    assert _post_comment(client, i["id"], USER, body="").status_code == 422


def test_comments_have_no_delete_route(client):
    i = create_integration(client, "Permanent").json()
    c = _post_comment(client, i["id"], ADMIN, body="forever").json()
    r = client.delete(f"/api/integrations/{i['id']}/comments/{c['id']}", headers=ADMIN)
    assert r.status_code in (404, 405)


def test_cannot_comment_on_deleted_integration_but_history_remains(client):
    i = create_integration(client, "ToDelete").json()
    _post_comment(client, i["id"], ADMIN, body="before delete")
    client.delete(f"/api/integrations/{i['id']}", headers=ADMIN)
    assert _post_comment(client, i["id"], ADMIN, body="after").status_code == 404
    res = client.get(f"/api/integrations/{i['id']}/comments", headers=ADMIN).json()
    assert res["total"] == 1 and res["items"][0]["body"] == "before delete"


# --- attachments ----------------------------------------------------------


def test_comment_with_image_attachment(client):
    i = create_integration(client, "Screenshots").json()
    png = _png_bytes()
    r = _post_comment(
        client,
        i["id"],
        USER,
        body="see screenshot",
        files=[("files", ("shot.png", png, "image/png"))],
    )
    assert r.status_code == 201
    c = r.json()
    assert len(c["attachments"]) == 1
    att = c["attachments"][0]
    assert att["content_type"] == "image/png"
    assert att["size_bytes"] == len(png)
    assert "data" not in att  # bytes are not inlined in JSON

    # The bytes are served back with a nosniff header and the right type.
    got = client.get(
        f"/api/integrations/{i['id']}/comments/{c['id']}/attachments/{att['id']}", headers=USER
    )
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/png")
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.content == png


def test_image_only_comment_allowed(client):
    i = create_integration(client, "ImageOnly").json()
    r = _post_comment(
        client, i["id"], USER, body="", files=[("files", ("a.png", _png_bytes(), "image/png"))]
    )
    assert r.status_code == 201
    assert len(r.json()["attachments"]) == 1


def test_svg_and_mismatched_content_rejected(client):
    i = create_integration(client, "NoScript").json()
    # SVG is rejected outright (can carry script).
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert (
        _post_comment(client, i["id"], USER, files=[("files", ("x.svg", svg, "image/svg+xml"))]).status_code
        == 415
    )
    # A file claiming to be PNG but isn't is rejected by the magic-byte check.
    assert (
        _post_comment(
            client, i["id"], USER, files=[("files", ("fake.png", b"<html>nope</html>", "image/png"))]
        ).status_code
        == 422
    )


def test_attachment_size_limit(client, monkeypatch):
    import backend.routers.comments as comments_router

    monkeypatch.setattr(comments_router, "MAX_ATTACHMENT_BYTES", 8)
    i = create_integration(client, "TooBig").json()
    r = _post_comment(
        client, i["id"], USER, files=[("files", ("big.png", _png_bytes(), "image/png"))]
    )
    assert r.status_code == 413
