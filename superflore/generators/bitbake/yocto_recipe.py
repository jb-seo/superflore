# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 David Bensoussan, Synapticon GmbH
# Copyright (c) 2017 Open Source Robotics Foundation, Inc.
#
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal  in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#

import hashlib
import os.path
import tarfile
from time import gmtime, strftime
from urllib.request import urlretrieve

from superflore.generators.bitbake.oe_query import OpenEmbeddedLayersDB
from superflore.exceptions import NoPkgXml
from superflore.exceptions import UnresolvedDependency
from superflore.utils import get_license
from superflore.utils import get_pkg_version
from superflore.utils import info
from superflore.utils import resolve_dep


class yoctoRecipe(object):

    resolved_deps_cache = set()
    unresolved_deps_cache = set()

    def __init__(
        self, name, distro, src_uri, tar_dir,
        md5_cache, sha256_cache, patches, incs
    ):
        self.name = name
        self.distro = distro.name
        self.version = get_pkg_version(distro, name)
        self.description = ''
        self.src_uri = src_uri
        self.pkg_xml = None
        self.author = "OSRF"
        self.license = None
        self.depends = set()
        self.depends_external = set()
        self.license_line = None
        self.archive_name = None
        self.license_md5 = None
        self.patch_files = patches
        self.inc_files = incs
        self.tar_dir = tar_dir
        if self.getArchiveName() not in md5_cache or \
           self.getArchiveName() not in sha256_cache:
                self.downloadArchive()
                md5_cache[self.getArchiveName()] = hashlib.md5(
                    open(self.getArchiveName(), 'rb').read()).hexdigest()
                sha256_cache[self.getArchiveName()] = hashlib.sha256(
                    open(self.getArchiveName(), 'rb').read()).hexdigest()
        self.src_sha256 = sha256_cache[self.getArchiveName()]
        self.src_md5 = md5_cache[self.getArchiveName()]
        self.build_type = 'catkin'

    def getFolderName(self):
        return self.name.replace("-", "_") + "-" + str(self.version)

    def getArchiveName(self):
        if not self.archive_name:
            self.archive_name = self.tar_dir + "/" \
                + self.name.replace('-', '_') + '-' + str(self.version) \
                + '-' + self.distro + '.tar.gz'
        return self.archive_name

    def get_license_line(self):
        self.license_line = ''
        self.license_md5 = ''
        i = 0
        if not self.pkg_xml:
            raise NoPkgXml('No package xml file!')
        for line in str(self.pkg_xml, 'utf-8').split('\n'):
            i += 1
            if 'license' in line:
                self.license_line = str(i)
                md5 = hashlib.md5()
                md5.update((line + '\n').encode())
                self.license_md5 = md5.hexdigest()
                break

    def downloadArchive(self):
        if os.path.exists(self.getArchiveName()):
            info("using cached archive for package '%s'..." % self.name)
        else:
            info("downloading archive version for package '%s' from %s..." % (self.name, self.src_uri))
            urlretrieve(self.src_uri, self.getArchiveName())

    def extractArchive(self):
        tar = tarfile.open(self.getArchiveName(), "r:gz")
        tar.extractall()
        tar.close()

    def add_build_depend(self, depend, internal=True):
        if internal:
            if depend not in self.depends_external:
                self.depends.add(depend)
        else:
            if depend not in self.depends:
                self.depends_external.add(depend)

    def get_src_location(self):
        """
        Parse out the folder name.
        TODO(allenh1): add a case for non-GitHub packages,
        after they are supported.
        """
        github_start = 'https://github.com/'
        structure = self.src_uri.replace(github_start, '')
        dirs = structure.split('/')
        return '{0}-{1}-{2}-{3}-{4}'.format(dirs[1], dirs[3],
                                            dirs[4], dirs[5],
                                            dirs[6]).replace('.tar.gz', '')

    def get_patches_line(self):
        ret = ''
        if self.patch_files:
            ret += 'SRC_URI += "\\\n'
            ret += ''.join([' ' * 4 + 'file://' + p.lstrip() + ' \\\n' for p in self.patch_files])
            ret += '"\n\n'
        return ret

    def get_incs_line(self):
        ret = ''
        if self.inc_files:
            ret += '\n'.join(['require %s' % f for f in self.inc_files])
        return ret

    def convert_recipe_name(self, dep):
        return dep.replace('_', '-')

    def get_bbclass_extend(self, name):
        if not name in set(['ament-package', 'osrf-pycommon']):
            return ''
        return 'BBCLASSEXTEND += "native"'

    def get_inherit_line(self):
        ret = 'inherit ros'
        if self.build_type in ['catkin', 'cmake']:
            ret += '\ninherit cmake'
        if self.build_type == 'ament_python':
            ret += '\ninherit setuptools3'
        elif self.build_type == 'ament_cmake':
            ret += '\ninherit ament-cmake'
        return ret + '\n\n'

    def get_recipe_text(self, distributor, license_text):
        """
        Generate the Yocto Recipe, given the distributor line
        and the license text.
        """
        ret = "# Copyright " + strftime("%Y", gmtime()) + " "
        ret += distributor + "\n"
        ret += '# Distributed under the terms of the ' + license_text
        ret += ' license\n\n'

        # description
        if self.description:
            self.description = self.description.replace('\n', ' ')
            ret += 'DESCRIPTION = "' + self.description + '"\n'
        else:
            ret += 'DESCRIPTION = "None"\n'
        # author
        ret += 'AUTHOR = "' + self.author + '"\n'
        # section
        ret += 'SECTION = "devel"\n'
        # ROS distro
        ret += 'ROSDISTRO = "%s"\n' % (self.distro)
        self.get_license_line()
        if isinstance(self.license, str):
            ret += 'LICENSE = "%s"\n' % get_license(self.license)
        elif isinstance(self.license, list):
            ret += 'LICENSE = "'
            ret += ' & '.join([get_license(l) for l in self.license]) + '"\n'
        ret += 'LIC_FILES_CHKSUM = "file://package.xml;beginline='
        ret += str(self.license_line)
        ret += ';endline='
        ret += str(self.license_line)
        ret += ';md5='
        ret += str(self.license_md5)
        ret += '"\n\n'
        # check for catkin
        if self.name == 'catkin':
            ret += 'CATKIN_NO_BIN="True"\n\n'
        # DEPEND
        ret += 'DEPENDS = "'
        has_int_depends = False
        # Internal
        for dep in sorted(self.depends):
            ret += self.convert_recipe_name(dep) + ' '
            has_int_depends = True
            print('Internal dependency add: ' + self.convert_recipe_name(dep))
        has_ext_depends = False
        # External
        for dep in sorted(self.depends_external):
            try:
                has_ext_depends = True
                for res in resolve_dep(dep, 'oe', self.distro)[0]:
                    ret += self.convert_recipe_name(res) + ' '
                    print('External dependency add: ' + self.convert_recipe_name(res))
            except UnresolvedDependency:
                dep = self.convert_recipe_name(dep)
                print('Unresolved dependency: ' + dep)
                if dep in yoctoRecipe.unresolved_deps_cache:
                    ret += dep + ' '
                    print('Failed to resolve (cached): ' + dep)
                    continue
                if dep in yoctoRecipe.resolved_deps_cache:
                    ret += dep + ' '
                    print('Resolved in OE (cached): ' + dep)
                    continue
                oe_query = OpenEmbeddedLayersDB()
                oe_query.query_recipe(dep)
                if oe_query.exists():
                    ret += oe_query.name + ' '
                    yoctoRecipe.resolved_deps_cache.add(dep)
                    print('Resolved in OE: ' + dep + ' as ' + oe_query.name + ' in ' + oe_query.layer)
                else:
                    ret += dep + ' '
                    yoctoRecipe.unresolved_deps_cache.add(dep)
                    print('Failed to resolve: ' + dep)
        ret = ret.rstrip() + '"\n'
        if not has_int_depends and not has_ext_depends:
            print('Recipe ' + self.name + ' has no dependencies!')
        elif not has_int_depends:
            print('Recipe ' + self.name + ' has no internal dependencies!')
        elif not has_ext_depends:
            print('Recipe ' + self.name + ' has no external dependencies!')

        # SRC_URI
        self.src_uri = self.src_uri.replace(self.name, '${PN}')
        ret += 'SRC_URI = "' + self.src_uri + ';'
        ret += 'downloadfilename=${ROS_SP}.tar.gz"\n\n'
        ret += 'SRC_URI[md5sum] = "' + self.src_md5 + '"\n'
        ret += 'SRC_URI[sha256sum] = "' + self.src_sha256 + '"\n'
        ret += 'S = "${WORKDIR}/'
        ret += self.get_src_location() + '"\n\n'
        # Check for patches
        ret += self.get_patches_line()
        # Check for incs
        ret += self.get_incs_line()
        # Inherits
        ret += self.get_inherit_line()
        # BBCLASSEXTEND
        ret += self.get_bbclass_extend(self.name)
        return ret

    @staticmethod
    def get_unresolved_cache():
        return yoctoRecipe.unresolved_deps_cache

    @staticmethod
    def reset_resolved_cache():
        yoctoRecipe.resolved_deps_cache = set()

    @staticmethod
    def reset_unresolved_cache():
        yoctoRecipe.unresolved_deps_cache = set()
