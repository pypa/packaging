import pytest

import packaging.errors


def test_error_collector_collect() -> None:
    collector = packaging.errors.ErrorCollector()

    with collector.collect():
        raise ValueError("first error")

    with collector.collect():
        raise KeyError("second error")

    collector.error(TypeError("third error"))

    with pytest.raises(packaging.errors.ExceptionGroup) as exc_info:
        collector.finalize("collected errors")

    exception_group = exc_info.value
    assert exception_group.message == "collected errors"
    assert len(exception_group.exceptions) == 3
    assert isinstance(exception_group.exceptions[0], ValueError)
    assert str(exception_group.exceptions[0]) == "first error"
    assert isinstance(exception_group.exceptions[1], KeyError)
    assert str(exception_group.exceptions[1]) == "'second error'"
    assert isinstance(exception_group.exceptions[2], TypeError)
    assert str(exception_group.exceptions[2]) == "third error"


def test_error_collector_no_errors() -> None:
    collector = packaging.errors.ErrorCollector()

    with collector.collect():
        pass  # No error

    collector.finalize("no errors")  # Should not raise


def test_error_collector_exception_group() -> None:
    collector = packaging.errors.ErrorCollector()

    with collector.collect():
        raise packaging.errors.ExceptionGroup(
            "inner group",
            [ValueError("inner error 1"), KeyError("inner error 2")],
        )

    with pytest.raises(packaging.errors.ExceptionGroup) as exc_info:
        collector.finalize("outer group")

    exception_group = exc_info.value
    assert exception_group.message == "outer group"
    assert len(exception_group.exceptions) == 2
    assert isinstance(exception_group.exceptions[0], ValueError)
    assert str(exception_group.exceptions[0]) == "inner error 1"
    assert isinstance(exception_group.exceptions[1], KeyError)
    assert str(exception_group.exceptions[1]) == "'inner error 2'"
