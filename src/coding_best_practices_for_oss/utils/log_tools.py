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


def dupLogger(src_name: str, dest_name: str, clear_existing: bool =True):
    src = logging.getLogger(src_name)
    dest = logging.getLogger(dest_name)
    dest.setLevel(src.level)
    if clear_existing:
        dest.handlers.clear()
        dest.filters.clear()
    for handler in src.handlers:
        if handler not in dest.handlers:
            dest.addHandler(handler)
    for filter in src.filters:
        if filter not in dest.filters:
            dest.addFilter(filter)
    dest.propagate = False
