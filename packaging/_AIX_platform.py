"""Shared AIX support functions."""

import sys
from sysconfig import get_config_var

# subprocess is not available early in the build process, test this
try:
    import subprocess

    _subprocess_rdy = True
except ImportError:  # pragma: no cover
    _subprocess_rdy = False

from ._typing import MYPY_CHECK_RUNNING

if MYPY_CHECK_RUNNING:  # pragma: no cover
    from typing import List, Tuple


# if var("AIX_BUILDDATE") is unknown, provide a substitute,
# impossible builddate to specify 'unknown'
_tmp = str(get_config_var("AIX_BUILDDATE"))
_bd = 9898 if (_tmp == "None") else int(_tmp)
_bgt = get_config_var("BUILD_GNU_TYPE")
_sz = 32 if sys.maxsize == 2147483647 else 64


def _aix_tag(v, bd):
    # type: (List[int], int) -> str
    # v is used as variable name so line below passes pep8 length test
    # v[version, release, technology_level]
    return "AIX-{:1x}{:1d}{:02d}-{:04d}-{}".format(v[0], v[1], v[2], bd, _sz)


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
    if _subprocess_rdy:
        out = subprocess.check_output(["/usr/bin/lslpp", "-Lqc", "bos.mp64"])
        out = out.decode("utf-8").strip().split(":")  # type: ignore
        # Use str() and int() to help mypy see types
        return str(out[2]), int(out[-1])
    else:
        # pretend os.uname() => ('AIX', 'localhost', '2', '5', '00C286454C00')
        # osname, host, release, version, machine = os.uname()
        return "{}.{}.0.0".format("5", "2"), 9898


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
    "AIX-{:1x}{:1d}{:02d}-{:04d}-{}".format(v, r, tl, builddate, bitsize)
    e.g., "AIX-6107-1415-32" for AIX 6.1 TL7 bd 1415, 32-bit
    and, "AIX-6107-1415-64" for AIX 6.1 TL7 bd 1415, 64-bit
    """
    vrmf, bd = _aix_bosmp64()
    return _aix_tag(_aix_vrtl(vrmf), bd)


# extract vrtl from the BUILD_GNU_TYPE as an int
def _aix_bgt():
    # type: () -> List[int]
    assert _bgt
    return _aix_vrtl(vrmf=_bgt)


def aix_buildtag():
    # type: () -> str
    """
    Return the platform_tag of the system Python was built on.
    """
    return _aix_tag(_aix_bgt(), _bd)
