import sys
from typing import Any

import pytest

from notifications_utils.serialised_model import (
    SerialisedModel,
    SerialisedModelCollection,
)


def test_cant_be_instatiated_with_abstract_properties():
    class CustomCollection(SerialisedModelCollection):
        pass

    with pytest.raises(TypeError) as e:
        SerialisedModelCollection()

    if sys.version_info >= (3, 12):
        assert str(e.value) == (
            "Can't instantiate abstract class SerialisedModelCollection without an implementation "
            "for abstract method 'model'"
        )
    else:
        assert str(e.value) == "Can't instantiate abstract class SerialisedModelCollection with abstract method model"

    with pytest.raises(TypeError) as e:
        CustomCollection()

    if sys.version_info >= (3, 12):
        assert str(e.value) == (
            "Can't instantiate abstract class CustomCollection without an implementation for abstract method 'model'"
        )
    else:
        assert str(e.value) == "Can't instantiate abstract class CustomCollection with abstract method model"


def test_looks_up_from_dict():
    class Custom(SerialisedModel):
        foo: Any

    assert Custom({"foo": "bar"}).foo == "bar"


def test_cant_override_custom_property_from_dict():
    class Custom(SerialisedModel):
        foo: Any

        @property
        def foo(self):
            return "bar"

    with pytest.raises(AttributeError) as e:
        Custom({"foo": "NOPE"})

    assert str(e.value) == (
        "property 'foo' of 'test_cant_override_custom_property_from_dict.<locals>.Custom' object has no setter"
    )


@pytest.mark.parametrize(
    "json_response",
    (
        {},
        {"foo": "bar"},  # Should still raise an exception
    ),
)
def test_model_raises_for_unknown_attributes(json_response):
    class Custom(SerialisedModel):
        pass

    model = Custom(json_response)

    with pytest.raises(AttributeError) as e:
        model.foo  # noqa

    assert str(e.value) == ("'Custom' object has no attribute 'foo'")


def test_model_raises_keyerror_if_item_missing_from_dict():
    class Custom(SerialisedModel):
        foo: Any

    with pytest.raises(KeyError) as e:
        Custom({}).foo  # noqa

    assert str(e.value) == "'foo'"


@pytest.mark.parametrize(
    "json_response",
    (
        {},
        {"foo": "bar"},  # Should be ignored
    ),
)
def test_model_doesnt_swallow_attribute_errors(json_response):
    class Custom(SerialisedModel):

        @property
        def foo(self):
            raise AttributeError("Something has gone wrong")

    with pytest.raises(AttributeError) as e:
        Custom(json_response).foo  # noqa

    assert str(e.value) == "Something has gone wrong"


def test_dynamic_properties_are_introspectable():
    class Custom(SerialisedModel):
        foo: Any
        bar: Any
        baz: Any

    instance = Custom({"foo": "", "bar": "", "baz": ""})

    assert dir(instance)[-3:] == ["bar", "baz", "foo"]


def test_empty_serialised_model_collection():
    class CustomCollection(SerialisedModelCollection):
        model = None

    instance = CustomCollection([])

    assert not instance
    assert len(instance) == 0


def test_serialised_model_collection_returns_models_from_list():
    class Custom(SerialisedModel):
        x: Any

    class CustomCollection(SerialisedModelCollection):
        model = Custom

    instance = CustomCollection(
        [
            {"x": "foo"},
            {"x": "bar"},
            {"x": "baz"},
        ]
    )

    assert instance
    assert len(instance) == 3

    assert instance[0].x == "foo"
    assert instance[1].x == "bar"
    assert instance[2].x == "baz"

    assert [item.x for item in instance] == [
        "foo",
        "bar",
        "baz",
    ]

    assert [type(item) for item in instance + [1, 2, 3]] == [
        Custom,
        Custom,
        Custom,
        int,
        int,
        int,
    ]

    instance_2 = CustomCollection(
        [
            {"x": "red"},
            {"x": "green"},
            {"x": "blue"},
        ]
    )

    assert [item.x for item in instance + instance_2] == [
        "foo",
        "bar",
        "baz",
        "red",
        "green",
        "blue",
    ]

    assert [item.x for item in instance_2 + instance] == [
        "red",
        "green",
        "blue",
        "foo",
        "bar",
        "baz",
    ]
