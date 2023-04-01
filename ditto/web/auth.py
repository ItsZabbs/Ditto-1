from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import aiohttp
from aiohttp.web import HTTPUnauthorized, Request
from aiohttp_security import AbstractAuthorizationPolicy
from discord import User
from discord.http import Route

from ..config import CONFIG

if TYPE_CHECKING:
    from ..core.bot import BotBase

AUTH_URI = Route.BASE + "/oauth2/authorize?client_id={0}&redirect_uri={1}&response_type=code&scope=identify"
USER_AGENT = "{0} ({1} {2}) Python/{3[0]}.{3[1]} aiohttp/{4}"


async def validate_login(bot: BotBase, request: Request) -> str:
    if "code" not in request.query:
        raise HTTPUnauthorized

    async with aiohttp.ClientSession(headers={"User-Agent": bot.user_agent}) as session:
        uri = Route.BASE + "/oauth2/token"
        payload = {
            "client_id": bot.application_id,
            "client_secret": CONFIG.APPLICATION.SECRET,
            "grant_type": "authorization_code",
            "code": request.query["code"],
            "redirect_uri": CONFIG.APPLICATION.REDIRECT_URI,
            "scope": "identify",
        }

        async with session.post(uri, data=payload) as resp:
            if resp.status != 200:
                raise HTTPUnauthorized

            data = await resp.json()
            if "access_token" not in data:
                raise HTTPUnauthorized
            token = data["access_token"]

        uri = Route.BASE + "/users/@me"

        async with session.get(uri, headers={"Authorization": f"Bearer {token}"}) as resp:
            result = await resp.json()
            return result["id"]


class DiscordAuthorizationPolicy(AbstractAuthorizationPolicy):
    def __init__(self, bot: BotBase) -> None:
        self.bot: BotBase = bot

    async def authorized_userid(self, identity: str) -> User:
        user_id = int(identity)
        return self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)

    async def permits(self, identity: str, permission: str, context: Optional[Request]) -> bool:
        user = await self.authorized_userid(identity)

        if permission in self.bot._permission_checks:
            return await self.bot._permission_checks[permission](self.bot, user)

        return False  # TODO: DB/CONFIG system for permissions
