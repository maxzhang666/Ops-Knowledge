#!/usr/bin/env python
"""Reset a user's password (运维/灾难恢复工具).

不输入 --password 时使用默认密码 `ChangeMe@123`。重置后调用
`revoke_user_tokens` 让该用户已签发的 JWT 全部失效（Redis-backed，
跨进程生效，不需要重启 API）。

用法：
    uv run scripts/reset_password.py <username>
    uv run scripts/reset_password.py <username> -p "NewPwd123!"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 让脚本能从项目根 import `app.*` —— 不依赖 cwd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402


DEFAULT_PASSWORD = "ChangeMe@123"
MIN_PASSWORD_LEN = 8


async def _reset(username: str, password: str) -> int:
    from app.auth.models import User
    from app.auth.service import _hash_password, revoke_user_tokens
    from app.core.database import async_session

    async with async_session() as db:
        user = (
            await db.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if user is None:
            print(f"[ERROR] user not found: {username}", file=sys.stderr)
            return 1

        user.hashed_password = _hash_password(password)
        await db.commit()
        revoke_user_tokens(str(user.id))

        print(f"[OK]   reset password for user '{username}'")
        print(f"       new password: {password}")
        print(f"       all existing tokens revoked (redis)")
        if password == DEFAULT_PASSWORD:
            print(f"[WARN] using default password — change it after first login")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset a user's password. Default password used when --password omitted.",
    )
    parser.add_argument("username", help="target username to reset")
    parser.add_argument(
        "-p", "--password",
        default=DEFAULT_PASSWORD,
        help=f"new password (default: {DEFAULT_PASSWORD!r}, min {MIN_PASSWORD_LEN} chars)",
    )
    args = parser.parse_args()

    if len(args.password) < MIN_PASSWORD_LEN:
        print(
            f"[ERROR] password must be ≥ {MIN_PASSWORD_LEN} chars (got {len(args.password)})",
            file=sys.stderr,
        )
        return 2

    return asyncio.run(_reset(args.username, args.password))


if __name__ == "__main__":
    sys.exit(main())
