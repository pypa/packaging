"""Shared AIX support functions."""

import sys
from sysconfig import get_config_var

try:
    from subprocess import check_output

    _have_subprocess = True
except ImportError:  # pragma: no cover
    # subprocess is not available early in the build process
    # substitures are necessary for bootstrap and CI coverage tests
    _have_subprocess = False

from ._typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from typing import List, Tuple


def _aix_tag(tl, bd):
    # type: (List[int], int) -> str
    # Infer the ABI bitwidth from maxsize (assuming 64 bit as the default)
    sz = 32 if sys.maxsize == (2 ** 31 - 1) else 64
    # tl[version, release, technology_level]
    return "aix-{:1x}{:1d}{:02d}-{:04d}-{}".format(tl[0], tl[1], tl[2], bd, sz)


# extract version, release and technology level from a VRMF string
def _aix_vrtl(vrmf):
    # type: (str) -> List[int]
    v, r, tl = vrmf.split(".")[:3]
    return [int(v[-1]), int(r), int(tl)]


def _aix_bosmp64():
    # type: () -> Tuple[str, int]
    """
    Return a Tuple[str, int] e.g., ['7.1.4.34', 1806]
    The fileset bos.mp64 is the AIX kernel. It's VRMF and builddate
    reflect the current ABI levels of the runtime environment.
    """
    if _have_subprocess:
        # We expect all AIX systems to have lslpp installed in this location
        out = check_output(["/usr/bin/lslpp", "-Lqc", "bos.mp64"])
        out = out.decode("utf-8").strip().split(":")  # type: ignore
        # Use str() and int() to help mypy see types
        return str(out[2]), int(out[-1])
    else:
        # This code was for CPython bootstrap phase (see Lib/_aix_aupport.py)
        # To pass `pypa/packaging` Windows CI tests mock constants are used
        release, version = 2, 7
        return "{}.{}.0.0".format(version, release), 9898


def aix_platform():
    # type: () -> str
    """
    AIX filesets are identified by four decimal values: V.R.M.F.
    V (version) and R (release) can be retreived using ``uname``
    Since 2007, starting with AIX 5.3 TL7, the M value has been
    included with the fileset bos.mp64 and represents the Technology
    Level (TL) of AIX. The F (Fix) value also increases, but is not
    relevant for comparing releases and binary compatibility.
    For binary compatibility the so-called builddate is needed.
    Again, the builddate of an AIX release is associated with bos.mp64.
    AIX ABI compatibility is described  as guaranteed at: https://www.ibm.com/\
    support/knowledgecenter/en/ssw_aix_72/install/binary_compatability.html

    For pep425 purposes the AIX platform tag becomes:
    "aix-{:1x}{:1d}{:02d}-{:04d}-{}".format(v, r, tl, builddate, bitsize)
    e.g., "aix-6107-1415-32" for AIX 6.1 TL7 bd 1415, 32-bit
    and, "aix-6107-1415-64" for AIX 6.1 TL7 bd 1415, 64-bit
    """
    vrmf, bd = _aix_bosmp64()
    return _aix_tag(_aix_vrtl(vrmf), bd)


# extract vrtl from the BUILD_GNU_TYPE as an int
def _aix_bgt():
    # type: () -> List[int]
    if _have_subprocess:
        bgt = get_config_var("BUILD_GNU_TYPE")
    else:
        bgt = "powerpc-ibm-aix6.1.7.0"
    return _aix_vrtl(vrmf=str(bgt))


def aix_buildtag():
    # type: () -> str
    """
    Return the platform_tag of the system Python was built on.
    """
    # To permit packaging to be used when the variable "AIX_BUILDDATE"
    # is not defined - return an impossible value rather than
    # raise ValueError() as Cpython Lib/_aix_support does
    bd = get_config_var("AIX_BUILDDATE") if _have_subprocess else "9898"
    try:
        bd = str(bd)
    except (TypeError, ValueError):
        bd = "9898"

    return _aix_tag(_aix_bgt(), int(bd))
