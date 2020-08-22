# -*- coding: UTF-8 -*-

from packaging.metadata import Metadata
import json
import os


VALID_PACKAGE_2_1_RFC822 = open(
    os.path.join(os.path.dirname(__file__), "2_1_pkginfo_string.txt")
).read()

VALID_PACKAGE_2_1_DICT = Metadata._rfc822_string_to_dict(VALID_PACKAGE_2_1_RFC822)

VALID_PACKAGE_2_1_JSON = json.dumps(VALID_PACKAGE_2_1_DICT, sort_keys=True)


VALID_PACKAGE_1_0_RFC822 = """Metadata-Version: 1.0
Name: sampleproject
Version: 2.0.0
Summary: A sample Python project
Home-page: https://github.com/pypa/sampleproject
Author: A. Random Developer
Author-email: author@example.com
License: UNKNOWN
Description: # A sample Python project
        A longer description
Keywords: sample,setuptools,development
Platform: UNKNOWN
"""

VALID_PACKAGE_1_0_REPEATED_DESC = """Metadata-Version: 1.0
Name: sampleproject
Version: 2.0.0
Summary: A sample Python project
Home-page: https://github.com/pypa/sampleproject
Author: A. Random Developer
Author-email: author@example.com
License: UNKNOWN
Description: # A sample Python project
        A longer description
Keywords: sample,setuptools,development
Platform: UNKNOWN

# This is the long description

This will overwrite the Description field
"""
VALID_PACKAGE_1_0_SINGLE_LINE_DESC = """Metadata-Version: 1.0
Name: sampleproject
Version: 2.0.0
Summary: A sample Python project
Home-page: https://github.com/pypa/sampleproject
Author: A. Random Developer
Author-email: author@example.com
License: UNKNOWN
Description: # A sample Python project
Keywords: sample,setuptools,development
Platform: UNKNOWN
"""

VALID_PACKAGE_1_0_DICT = Metadata._rfc822_string_to_dict(VALID_PACKAGE_1_0_RFC822)
VALID_PACKAGE_1_0_JSON = json.dumps(VALID_PACKAGE_1_0_DICT, sort_keys=True)


VALID_PACKAGE_1_2_RFC822 = """Metadata-Version: 1.2
Name: sampleproject
Version: 2.0.0
Summary: A sample Python project
Home-page: https://github.com/pypa/sampleproject
Author: A. Random Developer
Author-email: author@example.com
License: UNKNOWN
Description: # A sample Python project
        A longer description
Keywords: sample,setuptools,development
Platform: UNKNOWN
Requires-Python: >=3.5, <4
"""

VALID_PACKAGE_1_2_DICT = Metadata._rfc822_string_to_dict(VALID_PACKAGE_1_2_RFC822)
VALID_PACKAGE_1_2_JSON = json.dumps(VALID_PACKAGE_1_2_DICT, sort_keys=True)

VALID_PACKAGE_1_1_RFC822 = """Metadata-Version: 1.1
Name: sampleproject
Version: 2.0.0
Summary: A sample Python project
Home-page: https://github.com/pypa/sampleproject
Author: A. Random Developer
Author-email: author@example.com
License: UNKNOWN
Description: # A sample Python project
        A longer description
Keywords: sample,setuptools,development
Platform: UNKNOWN
Classifier: Development Status :: 3 - Alpha
Classifier: Intended Audience :: Developers
Classifier: Topic :: Software Development :: Build Tools
"""

VALID_PACKAGE_1_1_DICT = Metadata._rfc822_string_to_dict(VALID_PACKAGE_1_1_RFC822)
VALID_PACKAGE_1_1_JSON = json.dumps(VALID_PACKAGE_1_1_DICT, sort_keys=True)
