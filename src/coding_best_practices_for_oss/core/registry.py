# Registry auto-discovers rules so adding a new rule file is enough
# No central "register everything" list to maintain by hand
import importlib
import inspect
import logging
import pkgutil
from types import ModuleType

from coding_best_practices_for_oss import rules
from coding_best_practices_for_oss.core.rule import Rule

logger = logging.getLogger(__name__)


def discover_rules(package: ModuleType = rules) -> list[type[Rule]]:
    """Every concrete `Rule` subclass defined under the rules package.

    Rules are returned sorted by id, so that a run is reproducible whatever
    order the filesystem hands the modules over. A rule module that fails to
    import is reported and skipped rather than aborting the whole run.
    """
    discovered: dict[type[Rule], None] = {}  # dict, to keep insertion order

    for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        try:
            module = importlib.import_module(module_name)
        except Exception as error:  # a broken rule must not break the others
            logger.error("Could not import the rule module %s: %s", module_name, error)
            continue

        for obj in vars(module).values():
            if _is_rule_class(obj, module_name):
                discovered[obj] = None

    #logger.debug("Found %s rule%s.", len(discovered), "" if len(discovered) == 1 else "s")

    return sorted(discovered, key=lambda rule: (rule.id, rule.__name__))


def _is_rule_class(obj: object, module_name: str) -> bool:
    """Whether `obj` is a rule *defined* in `module_name`.

    The module check keeps a rule imported by another rule module from being
    collected twice, and drops the imported `Rule` base class itself.
    """
    if not inspect.isclass(obj) or not issubclass(obj, Rule):
        return False
    if obj is Rule or inspect.isabstract(obj):
        return False
    if obj.__module__ != module_name:
        return False
    if not obj.id:
        logger.warning("Ignoring rule %s: it has no id.", obj.__name__)
        return False
    return True


def instantiate_rules(rule_classes: list[type[Rule]] | None = None) -> list[Rule]:
    """Instantiate discovered rules, skipping the ones failing to build."""
    instances = []
    for rule_class in discover_rules() if rule_classes is None else rule_classes:
        try:
            instances.append(rule_class())
        except Exception as error:
            logger.error("Could not instantiate the rule %s: %s", rule_class.__name__, error)
    return instances
