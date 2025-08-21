# app/userutils/user_helpers.py (or keep inside user.py if you prefer)
from fastapi import Request
from typing import Union, List
from app.user.models.user import User

def add_absolute_image_url(
    user_or_users: Union[User, List[User]], request: Request
) -> Union[User, List[User]]:
    """
    Ensure user.image_url is returned as an absolute URL.
    Works for a single User or a list of Users.
    """
    def _fix(u: User):
        if u and u.image_url and not u.image_url.startswith("http"):
            u.image_url = str(request.base_url) + u.image_url.lstrip("/")
        return u

    if isinstance(user_or_users, list):
        return [_fix(u) for u in user_or_users]
    else:
        return _fix(user_or_users)
