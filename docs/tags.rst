Tags
====

.. currentmodule:: packaging.tags

XXX

Usage
-----

XXX explanation
XXX doctests


Reference
---------

.. attribute:: INTERPRETER_SHORT_NAMES

    XXX

.. class:: Tag(interpreter, abi, platform)

    XXX equality
    XXX immutable/hashable

    :param str interpreter: XXX
    :param str abi: XXX
    :param str platform: XXX

    .. attribute:: interpreter

        XXX

    .. attribute:: abi

        XXX

    .. attribute:: platform

        XXX


.. function:: parse_tag(tag)

    XXX

    :param str tag: XXX


.. function:: parse_wheel_filename(path)

    XXX

    :param typing.Union[str,os.PathLike] path: XXX


.. function:: sys_tags()

    XXX
