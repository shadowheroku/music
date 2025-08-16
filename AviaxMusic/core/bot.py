import sys
if sys.platform != "win32":
    import uvloop
    uvloop.install()

from pyrogram import Client
from pyrogram.enums import ParseMode

import config
from ..logging import LOGGER


class Aviax(Client):
    def __init__(self):
        LOGGER(__name__).info("Starting Bot...")
        super().__init__(
            name="AviaxMusic",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            in_memory=True,
            parse_mode=ParseMode.HTML,
            max_concurrent_transmissions=7,
        )

    async def start(self):
        await super().start()
        self.id = self.me.id
        self.name = self.me.first_name
        self.username = self.me.username
        self.mention = self.me.mention

        LOGGER(__name__).info(
            f"Music Bot Started as {self.name} (@{self.username}) | ID: {self.id}"
        )

    async def stop(self):
        await super().stop()
        LOGGER(__name__).info("Music Bot Stopped.")
