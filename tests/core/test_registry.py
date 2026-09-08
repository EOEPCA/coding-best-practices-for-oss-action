import logging
from abc import abstractmethod

from coding_best_practices_for_oss.core.registry import (
    _is_rule_class,
    discover_rules,
    instantiate_rules,
)
from coding_best_practices_for_oss.core.rule import Rule
from coding_best_practices_for_oss.rules.documentation.missing_readme import MissingReadmeRule


class ConcreteRule(Rule):
    id = "TST001"

    def check(self, context):
        return []


class AbstractRule(Rule):
    id = "TST002"

    @abstractmethod
    def helper(self):
        """Not implemented, so this class must not be collected."""


class RuleWithoutId(Rule):
    def check(self, context):
        return []


class UnbuildableRule(Rule):
    id = "TST003"

    def __init__(self):
        raise RuntimeError("cannot build me")

    def check(self, context):
        return []


THIS_MODULE = __name__


class TestIsRuleClass:
    def test_a_concrete_rule_is_collected(self):
        assert _is_rule_class(ConcreteRule, THIS_MODULE) is True

    def test_the_base_class_is_not_collected(self):
        assert _is_rule_class(Rule, THIS_MODULE) is False

    def test_an_abstract_rule_is_not_collected(self):
        assert _is_rule_class(AbstractRule, THIS_MODULE) is False

    def test_a_rule_without_id_is_not_collected(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert _is_rule_class(RuleWithoutId, THIS_MODULE) is False
        assert "no id" in caplog.text

    def test_a_rule_imported_from_another_module_is_not_collected_twice(self):
        # Only the module that defines the rule collects it.
        assert _is_rule_class(ConcreteRule, "some.other.module") is False

    def test_anything_else_is_not_collected(self):
        assert _is_rule_class("not a class", THIS_MODULE) is False
        assert _is_rule_class(object, THIS_MODULE) is False


class TestDiscoverRules:
    def test_the_shipped_rules_are_discovered(self):
        assert MissingReadmeRule in discover_rules()

    def test_every_discovered_rule_is_usable(self):
        for rule_class in discover_rules():
            assert issubclass(rule_class, Rule)
            assert rule_class.id

    def test_rules_are_sorted_by_id(self):
        ids = [rule_class.id for rule_class in discover_rules()]
        assert ids == sorted(ids)

    def test_a_broken_rule_module_does_not_break_the_discovery(self, caplog, monkeypatch):
        import importlib

        real_import = importlib.import_module

        def failing_import(name, *args, **kwargs):
            if name.endswith("missing_readme"):
                raise ImportError("boom")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", failing_import)
        with caplog.at_level(logging.ERROR):
            discovered = discover_rules()
        assert MissingReadmeRule not in discovered
        assert "Could not import the rule module" in caplog.text


class TestInstantiateRules:
    def test_rules_are_instantiated(self):
        instances = instantiate_rules([ConcreteRule])
        assert [type(instance) for instance in instances] == [ConcreteRule]

    def test_a_rule_that_cannot_be_built_is_skipped(self, caplog):
        with caplog.at_level(logging.ERROR):
            assert instantiate_rules([UnbuildableRule, ConcreteRule]) != []
        assert "Could not instantiate the rule UnbuildableRule" in caplog.text

    def test_without_argument_the_discovered_rules_are_instantiated(self):
        assert any(isinstance(rule, MissingReadmeRule) for rule in instantiate_rules())
