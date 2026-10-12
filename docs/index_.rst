Index
=====


.. module:: packaging.index

.. versionadded:: 26.4

Help make requests to and work with responses from index servers implementing
the :ref:`Simple Repository API <simple-repository-api>`.

Usage
-----

.. code-block:: python-console

    >>> from packaging.index import ACCEPT, parse_list
    >>> import requests
    >>> response = requests.get("https://pypi.org/simple/", headers={"ACCEPT": ACCEPT})
    >>> project_list = parse_list(response.headers["content-type"], response.text)
    >>> len(project_list["projects"]) > 900_000
    True


Reference
---------

High Level Interface
''''''''''''''''''''

.. autodata:: packaging.index.ACCEPT_JSON_V1

.. autodata:: packaging.index.ACCEPT_HTML

.. autodata:: packaging.index.ACCEPT


Low Level Interface
'''''''''''''''''''

.. autoclass:: packaging.index.RawProjectList

.. autoclass:: packaging.index.RawProjectDetails

.. autoclass:: packaging.index.RawProjectDetailsFile

.. autofunction:: packaging.index.parse_list

.. autofunction:: packaging.index.parse_details


Exceptions
''''''''''

.. autoclass:: packaging.index.IndexServerException
    :members:

.. autoclass:: packaging.index.InvalidContentType
    :members:

.. autoclass:: packaging.index.InvalidHTMLAttributeValue
    :members:
