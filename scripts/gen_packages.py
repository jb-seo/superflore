# generates ebuilds from ros distribution data
import xmltodict

from rosinstall_generator.distro import get_distro, get_package_names, _generate_rosinstall
from rosdistro.dependency_walker import DependencyWalker, SourceDependencyWalker
from rosdistro.manifest_provider import get_release_tag
from rosdistro.rosdistro import RosPackage

from .ebuild import Ebuild
from .metadata_xml import metadata_xml

def _gen_ebuild_for_package(distro_name, pkg_name):
    distro = get_distro(distro_name)
    pkg = distro.release_packages[pkg_name]
    repo = distro.repositories[pkg.repository_name].release_repository
    ros_pkg = RosPackage(pkg_name, repo)

    pkg_rosinstall = _generate_rosinstall(pkg_name, repo.url, get_release_tag(repo, pkg_name), True)
    pkg_ebuild = Ebuild()

    pkg_ebuild.distro = distro.name
    pkg_ebuild.src_uri = pkg_rosinstall[0]['tar']['uri']
    pkg_dep_walker = DependencyWalker(distro)

    pkg_build_deps = pkg_dep_walker.get_depends(pkg_name, "build")
    pkg_run_deps   = pkg_dep_walker.get_depends(pkg_name, "run")

    pkg_keywords = [ 'x86', 'amd64', 'arm', 'arm64' ]

    # add run dependencies
    for rdep in pkg_run_deps:
        pkg_ebuild.add_run_depend(rdep)

    # add build dependencies
    for bdep in pkg_build_deps:
        pkg_ebuild.add_build_depend(bdep)

    # add keywords
    for key in pkg_keywords:
        pkg_ebuild.add_keyword(key)

    # parse throught package xml
    pkg_xml = ros_pkg.get_package_xml(distro.name)
    pkg_fields = xmltodict.parse(pkg_xml)

    pkg_ebuild.upstream_license = pkg_fields['package']['license']
    pkg_ebuild.description = pkg_fields['package']['description']

    """
    @todo: homepage
    """
    return pkg_ebuild
