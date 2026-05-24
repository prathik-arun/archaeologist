from api.users import get_user, create_user

def test_get_user():
    result = get_user(1)
    assert result["id"] == 1

def test_create_user():
    result = create_user({"name": "test"})
    assert result["created"] == True
