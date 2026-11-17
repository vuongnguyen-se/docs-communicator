import json

from clouddocs.handlers import me

from .conftest import USER_A, api_event


def test_me_returns_sub_from_jwt_claims():
    resp = me.handler(api_event("GET /me", user=USER_A), None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]) == {"userId": USER_A}


def test_me_without_claims_is_401():
    resp = me.handler(api_event("GET /me", user=None), None)
    assert resp["statusCode"] == 401
