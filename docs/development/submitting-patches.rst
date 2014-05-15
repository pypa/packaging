Submitting patches
==================

* Always make a new branch for your work.
* Patches should be small to facilitate easier review. `Studies have shown`_
  that review quality falls off as patch size grows. Sometimes this will result
  in many small PRs to land a single large feature.
* Larger changes should be discussed in a ticket before submission.
* New features and significant bug fixes should be documented in the
  :doc:`/changelog`.

If you believe you've identified a security issue in packaging, please
follow the directions on the :doc:`security page </security>`.

Code
----

When in doubt, refer to :pep:`8` for Python code. You can check if your code
meets our automated requirements by running ``flake8`` against it. If you've
installed the development requirements this will automatically use our
configuration. You can also run the ``tox`` job with ``tox -e pep8``.

`Write comments as complete sentences.`_

Every code file must start with the boilerplate notice of the Apache License.
Additionally, every Python code file must contain

.. code-block:: python

    from __future__ import absolute_import, division, print_function


Tests
-----

All code changes must be accompanied by unit tests with 100% code coverage (as
measured by the combined metrics across our build matrix).


Documentation
-------------

All features should be documented with prose in the ``docs`` section.

When referring to a hypothetical individual (such as "a person receiving an
encrypted message") use gender neutral pronouns (they/them/their).

Docstrings are typically only used when writing abstract classes, but should
be written like this if required:

.. code-block:: python

    def some_function(some_arg):
        """
        Does some things.

        :param some_arg: Some argument.
        """

So, specifically:

* Always use three double quotes.
* Put the three double quotes on their own line.
* No blank line at the end.
* Use Sphinx parameter/attribute documentation `syntax`_.


.. _`Write comments as complete sentences.`: http://nedbatchelder.com/blog/201401/comments_should_be_sentences.html
.. _`syntax`: http://sphinx-doc.org/domains.html#info-field-lists
.. _`Studies have shown`: http://www.ibm.com/developerworks/rational/library/11-proven-practices-for-peer-review/