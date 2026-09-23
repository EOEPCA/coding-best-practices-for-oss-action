import logging


def getLogger(name, prefix: str|None = None):
    logger = logging.getLogger(name)
    logger.propagate = False
    if prefix:
        formatter = logging.Formatter(
            fmt=f"%(asctime)s  %(levelname)-8s[{prefix}] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            fmt=f"%(asctime)s  %(levelname)-8s%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger