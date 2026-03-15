import pytest

from taskflow.core.registry import TaskRegistry


def test_register_and_get_by_function_name():
    registry = TaskRegistry()

    @registry.register()
    def my_task(x):
        return x

    func = registry.get("my_task")
    assert func(5) == 5


def test_register_with_explicit_name():
    registry = TaskRegistry()

    @registry.register("custom_name")
    def some_func():
        return "ok"

    assert registry.get("custom_name")() == "ok"
    with pytest.raises(KeyError):
        registry.get("some_func")


def test_get_missing_task_raises_keyerror():
    registry = TaskRegistry()
    with pytest.raises(KeyError):
        registry.get("does_not_exist")


def test_list_tasks():
    registry = TaskRegistry()

    @registry.register("a")
    def a():
        pass

    @registry.register("b")
    def b():
        pass

    assert sorted(registry.list_tasks()) == ["a", "b"]


def test_unregister_removes_task():
    registry = TaskRegistry()

    @registry.register("a")
    def a():
        pass

    assert registry.unregister("a") is True
    assert "a" not in registry.list_tasks()
    with pytest.raises(KeyError):
        registry.get("a")


def test_unregister_missing_task_returns_false():
    registry = TaskRegistry()
    assert registry.unregister("does_not_exist") is False


def test_register_overwrites_existing_name():
    registry = TaskRegistry()

    @registry.register("dup")
    def first():
        return "first"

    @registry.register("dup")
    def second():
        return "second"

    assert registry.get("dup")() == "second"
