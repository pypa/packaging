MULTI_1_0 = {"Platform"}  # type :  typing.Set[str]

TREAT_AS_MULTI_1_0 = {"Keywords"}  # type : typing.Set[str]

SINGLE_1_0 = {
    "Metadata-Version",
    "Name",
    "Version",
    "Summary",
    "Description",
    "Home-page",
    "Author",
    "Author-email",
    "License",
}  # type : typing.Set[str]


MULTI_1_1 = {"Platform", "Supported-Platform", "Classifier"}  # type : typing.Set[str]

TREAT_AS_MULTI_1_1 = {"Keywords"}  # type : typing.Set[str]

SINGLE_1_1 = {
    "Metadata-Version",
    "Name",
    "Version",
    "Summary",
    "Description",
    "Home-page",
    "Download-URL",
    "Author",
    "Author-email",
    "License",
}  # type : typing.Set[str]


MULTI_1_2 = {
    "Platform",
    "Supported-Platform",
    "Classifier",
    "Requires-Dist",
    "Provides-Dist",
    "Obsoletes-Dist",
    "Requires-External",
    "Project-URL",
}  # type : typing.Set[str]

TREAT_AS_MULTI_1_2 = {"Keywords"}  # type : typing.Set[str]

SINGLE_1_2 = {
    "Metadata-Version",
    "Name",
    "Version",
    "Summary",
    "Description",
    "Home-page",
    "Download-URL",
    "Author",
    "Author-email",
    "Maintainer",
    "Maintainer-email",
    "License",
    "Requires-Python",
}  # type : typing.Set[str]


MULTI_2_1 = {
    "Platform",
    "Supported-Platform",
    "Classifier",
    "Requires-Dist",
    "Provides-Dist",
    "Obsoletes-Dist",
    "Requires-External",
    "Project-URL",
    "Provides-Extra",
}  # type : typing.Set[str]

TREAT_AS_MULTI_2_1 = {"Keywords"}  # type : typing.Set[str]

SINGLE_2_1 = {
    "Metadata-Version",
    "Name",
    "Version",
    "Summary",
    "Description",
    "Description-Content-Type",
    "Home-page",
    "Download-URL",
    "Author",
    "Author-email",
    "Maintainer",
    "Maintainer-email",
    "License",
    "Requires-Python",
}  # type : typing.Set[str]


VERSIONED_METADATA_FIELDS = {
    "1.0": {
        "MULTI": MULTI_1_0,
        "TREAT_AS_MULTI": TREAT_AS_MULTI_1_0,
        "SINGLE": SINGLE_1_0,
    },
    "1.1": {
        "MULTI": MULTI_1_1,
        "TREAT_AS_MULTI": TREAT_AS_MULTI_1_1,
        "SINGLE": SINGLE_1_1,
    },
    "1.2": {
        "MULTI": MULTI_1_2,
        "TREAT_AS_MULTI": TREAT_AS_MULTI_1_2,
        "SINGLE": SINGLE_1_2,
    },
    "2.1": {
        "MULTI": MULTI_2_1,
        "TREAT_AS_MULTI": TREAT_AS_MULTI_2_1,
        "SINGLE": SINGLE_2_1,
    },
}  # type : typing.Any

# typing.Dict[typing.Union[typing.List[str],str], typing.Dict[str, typing.Set[str]]]
