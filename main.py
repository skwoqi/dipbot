from bot import bot, validate_config


if __name__ == "__main__":
    validate_config()
    bot.run_forever()
