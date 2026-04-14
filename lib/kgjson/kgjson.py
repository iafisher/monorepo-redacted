import decimal
import json
import types
import typing
from typing import Generic, ItemsView, NewType, Self, TypeVar, cast

from iafisher_foundation import timehelper
from iafisher_foundation.prelude import *
from lib import humanunits, oshelper


T = TypeVar("T")


class LockFile(Generic[T]):
    lock_file: oshelper.LockFile

    def __init__(self, p: PathLike, deserialize: Callable[[Dict[str, Any]], T]) -> None:
        self.lock_file = oshelper.LockFile(p, mode="a+", exclusive=True)
        self.deserialize = deserialize

    def __enter__(self) -> Self:
        self.lock_file.acquire()
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        self.lock_file.release()

    # TODO(2025-02): mypy can't handle this type annotation
    def read(self) -> T:
        f = self.lock_file.f
        if f is None:
            raise KgError("tried to read from lock file without acquiring it first")

        f.seek(0)
        text = f.read()
        d: Dict[str, Any] = json.loads(text) if text else {}
        return self.deserialize(d)

    def write(self, t: T) -> None:
        f = self.lock_file.f
        if f is None:
            raise KgError("tried to write to lock file without acquiring it first")

        f.seek(0)
        f.truncate(0)
        f.write(t.serialize())  # type: ignore


class Base:
    def serialize(self, *, camel_case: bool = False) -> str:
        as_dict = dataclasses.asdict(self)  # type: ignore
        if camel_case:
            as_dict = _snake_to_camel_dict(as_dict)
        return json.dumps(as_dict, cls=KgJsonEncoder)

    def save(self, p: PathLike) -> None:
        oshelper.replace_file(p, self.serialize())

    @classmethod
    def kgjson_validate(cls, _o: Self) -> None:
        """
        Subclasses can optionally override this method to validate the deserialized object
        and raise `KgError` on failure.
        """
        pass

    @classmethod
    def deserialize(
        cls, d: StrDict, *, validate: bool = True, camel_case: bool = False
    ) -> Self:
        if camel_case:
            d = _camel_to_snake_dict(d)
        return cls._deserialize_dict(d, path="$", validate=validate)

    @classmethod
    def load(cls, p: PathLike, *, validate: bool = True) -> Self:
        text = pathlib.Path(p).read_text()
        d = json.loads(text)
        return cls.deserialize(d, validate=validate)

    @classmethod
    def with_lock(cls, p: PathLike) -> LockFile[Self]:
        return LockFile(p, cls.deserialize)

    @classmethod
    def _deserialize_value(
        cls, x: Any, expected_type: Any, path: str, *, validate: bool
    ) -> Any:
        def lazy_wrong_type_for_value() -> KgError:
            return KgError(
                "wrong type for value",
                json_path=path,
                value=x,
                expected_type=expected_type,
            )

        if _is_optional_type(expected_type):
            expected_type = typing.get_args(expected_type)[0]
            is_optional = True
        else:
            is_optional = False

        # example: `origin_type` for `typing.List` is `list`
        #
        # important to do this _after_ the check above when `expected_type` might be set to
        # something different
        origin_type = typing.get_origin(expected_type)
        arg_types = typing.get_args(expected_type)

        if isinstance(expected_type, type):
            if is_optional and x is None:
                return None
            elif issubclass(expected_type, Base):
                return expected_type._deserialize_dict(x, path=path, validate=validate)
            elif isinstance(x, expected_type):
                return x
            elif expected_type is datetime.date and isinstance(x, str):
                try:
                    return datetime.date.fromisoformat(x)
                except ValueError:
                    raise KgError(
                        "date field must be in ISO 8601 format (YYYY-MM-DD)",
                        json_path=path,
                        value=x,
                    )
            elif expected_type is datetime.datetime:
                if isinstance(x, int) or isinstance(x, float):
                    return datetime.datetime.fromtimestamp(x, tz=timehelper.TZ_NYC)
                elif isinstance(x, str):
                    try:
                        dt = datetime.datetime.fromisoformat(x)
                    except ValueError:
                        raise KgError(
                            "datetime field must be in ISO 8601 format",
                            json_path=path,
                            value=x,
                        )
                    else:
                        if not timehelper.is_datetime_aware(dt):
                            raise KgError(
                                "if datetime field is represented as a string, it must contain time-zone information",
                                json_path=path,
                                value=x,
                            )

                        return dt
                else:
                    raise KgError(
                        "datetime field must be represented in ISO 8601 format, or as seconds since the Unix epoch",
                        json_path=path,
                        value=x,
                    )
            elif expected_type is datetime.time:
                try:
                    return humanunits.parse_time(x)
                except KgError as e:
                    raise e.attach(json_path=path)
            elif expected_type is decimal.Decimal:
                try:
                    return decimal.Decimal(x)
                except decimal.InvalidOperation:
                    raise KgError(
                        "could not parse decimal value", json_path=path, value=x
                    )
            else:
                raise lazy_wrong_type_for_value()
        elif isinstance(expected_type, NewType):
            if expected_type.__supertype__ is str:
                return x
            else:
                raise KgError(
                    "only str-valued NewTypes are supported", json_path=path, value=x
                )
        else:
            if origin_type is list:
                if not isinstance(x, list):
                    if is_optional and x is None:
                        return None
                    else:
                        raise lazy_wrong_type_for_value()

                return cls._deserialize_list(x, arg_types[0], path, validate=validate)  # type: ignore
            elif origin_type is dict:
                if not isinstance(x, dict):
                    if is_optional and x is None:
                        return None
                    else:
                        raise lazy_wrong_type_for_value()

                if (
                    arg_types[0] is not str
                    # handle the `NewType` case
                    and getattr(arg_types[0], "__supertype__") is not str
                ):
                    raise KgError(
                        "dict keys must be strings", type=arg_types[0], json_path=path
                    )

                return cls._deserialize_typed_dict(
                    x, arg_types[1], path, validate=validate  # type: ignore
                )
            elif origin_type is typing.Literal:
                if x not in arg_types:
                    raise KgError(
                        "unexpected value for literal field",
                        type=expected_type,
                        json_path=path,
                    )

                return x
            else:
                raise KgError(
                    "dataclasses type annotation is not supported",
                    type=expected_type,
                    json_path=path,
                )

    @classmethod
    def _deserialize_list(
        cls, xs: List[Any], expected_type: Any, path: str, *, validate: bool
    ) -> List[Any]:
        r: List[Any] = []

        for i, x in enumerate(xs):
            this_path = path + f"[{i}]"
            v = cls._deserialize_value(
                x, expected_type, path=this_path, validate=validate
            )
            r.append(v)

        return r

    @classmethod
    def _deserialize_typed_dict(
        cls,
        d: Dict[str, Any],
        expected_value_type: Any,
        path: str,
        *,
        validate: bool,
    ) -> Dict[str, Any]:
        r: Dict[str, Any] = {}

        for key, raw_value in d.items():
            this_path = path + f"[{key!r}]"

            if not isinstance(key, str):
                raise KgError("dict keys must be strings", key=key, json_path=path)

            value = cls._deserialize_value(
                raw_value, expected_value_type, path=this_path, validate=validate
            )
            r[key] = value

        return r

    @classmethod
    def _deserialize_dict(
        cls,
        d: StrDict,
        path: str,
        *,
        validate: bool,
    ) -> Self:
        o = cls._deserialize_dict_impl(d, path, validate=validate)
        if validate:
            try:
                cls.kgjson_validate(o)
            except KgError as e:
                raise e.attach(json_path=path)
        return o

    @classmethod
    def _deserialize_dict_impl(cls, d: StrDict, path: str, *, validate: bool) -> Self:
        if not isinstance(d, dict):
            raise KgError(
                "wrong type for value", json_path=path, value=d, expected_type=cls
            )

        kwargs = {}
        dataclass_fields: ItemsView[str, Any] = cast(
            Dict[str, Any], cls.__dataclass_fields__  # type: ignore
        ).items()
        for field_name, field in dataclass_fields:
            this_path = path + f".{field_name}"

            if field_name not in d:
                if not isinstance(field.default, dataclasses._MISSING_TYPE):
                    v = field.default
                elif not isinstance(field.default_factory, dataclasses._MISSING_TYPE):
                    v = field.default_factory()
                elif _is_optional_type(field.type):
                    v = None
                else:
                    raise KgError(
                        "missing value for key", key=field_name, json_path=this_path
                    )
            else:
                v = cls._deserialize_value(
                    d[field_name], field.type, path=this_path, validate=validate
                )

            kwargs[field_name] = v

        return cls(**kwargs)


def _is_optional_type(type_: Any) -> bool:
    # TODO(2026-02): This function is duplicated in `lib/command`.
    origin_type = typing.get_origin(type_)
    arg_types = typing.get_args(type_)
    return (
        (origin_type is Union or origin_type is types.UnionType)
        and len(arg_types) == 2
        and (type(None) is arg_types[1] or type(None) is arg_types[0])
    )


class KgJsonEncoder(json.JSONEncoder):
    @override
    def default(self, o: Any) -> Any:
        if isinstance(o, datetime.date):
            return o.isoformat()
        elif isinstance(o, datetime.time):
            return o.isoformat()
        elif isinstance(o, decimal.Decimal):
            return str(o)

        return super().default(o)


def snake_to_camel(snake_str: str) -> str:
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


_camel_pattern = lazy_re("([a-z])([A-Z])")


def camel_to_snake(camel_str: str) -> str:
    return _camel_pattern.get().sub(
        lambda m: m.group(1) + "_" + m.group(2).lower(), camel_str
    )


def _snake_to_camel_dict(o: Any) -> Any:
    return _dict_transformer(o, snake_to_camel)


def _camel_to_snake_dict(o: Any) -> Any:
    return _dict_transformer(o, camel_to_snake)


def _dict_transformer(o: Any, f: Callable[[str], str]) -> Any:
    if isinstance(o, dict):
        return {
            f(k) if isinstance(k, str) else k: _dict_transformer(v, f)
            for k, v in o.items()
        }
    elif isinstance(o, list):
        return [_dict_transformer(x, f) for x in o]
    else:
        return o
