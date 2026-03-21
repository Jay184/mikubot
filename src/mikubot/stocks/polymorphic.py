from typing import Annotated, TypeVar, Type, ClassVar, Unpack
from collections import defaultdict
from pydantic import BaseModel, ConfigDict, BeforeValidator, SerializeAsAny
from pydantic_core import PydanticUndefined


T = TypeVar("T", bound="PolymorphicBase")


class PolymorphicBase(BaseModel):
    """A reusable base class for polymorphic Pydantic models."""
    _subtypes: ClassVar[defaultdict[str, dict[str, type["PolymorphicBase"]]]] = defaultdict(dict)

    type: str

    def __init_subclass__(cls, *, identity: str | None = None, **kwargs: Unpack[ConfigDict]):
        """Called when a subclass is created; sets up subtype identity."""
        super().__init_subclass__(**kwargs)

        # Inherit parent's identity if not explicitly provided
        parent_identity = None
        for base in cls.__mro__[1:]:  # skip cls itself
            if hasattr(base, "_subtypes_identity"):
                parent_identity = getattr(base, "_subtypes_identity")
                break

        cls._subtypes_identity: ClassVar[str] = identity or parent_identity

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Unpack[ConfigDict]):
        """Hook for Pydantic subclass initialization — auto-registers subtypes."""
        super().__pydantic_init_subclass__(**kwargs)

        # Auto-register subclasses with a unique `type` field default
        type_field = cls.model_fields.get("type")

        if type_field and type_field.default is not PydanticUndefined:
            # Store subclass under its identity and type default
            PolymorphicBase._subtypes[cls._subtypes_identity][type_field.default] = cls

    @classmethod
    def get_type(cls: Type[T], type_key: str) -> Type[T] | None:
        """Look up a registered subtype by its type key (per subclass identity)."""
        return PolymorphicBase._subtypes.get(cls._subtypes_identity, {}).get(type_key)


def make_polymorphic_validator(base_cls: Type[T]):
    def parse_polymorphic(value: dict | T) -> T:
        if isinstance(value, base_cls):
            return value

        if isinstance(value, dict):
            type_key = value.get("type")
            type_cls = base_cls.get_type(type_key)

            if type_cls is None:
                raise ValueError(f"Unknown type: {type_key}")

            return type_cls.model_validate(value)

        raise TypeError(f"Unsupported: {value}")

    # Return an Annotated type usable in Pydantic models
    return Annotated[
        base_cls,
        BeforeValidator(parse_polymorphic),
        SerializeAsAny()
    ]
