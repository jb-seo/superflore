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
from datetime import datetime
from time import gmtime, strftime
from urllib.request import urlretrieve

from superflore.exceptions import NoPkgXml
from superflore.exceptions import UnresolvedDependency
from superflore.generators.bitbake.oe_query import OpenEmbeddedLayersDB
from superflore.PackageMetadata import PackageMetadata
from superflore.utils import err
from superflore.utils import get_license
from superflore.utils import get_pkg_version
from superflore.utils import info
from superflore.utils import make_dir
from superflore.utils import ok
from superflore.utils import resolve_dep


class yoctoRecipe(object):

    resolved_deps_cache = set()
    unresolved_deps_cache = set()
    generated_recipes = set()

    def __init__(
        self, component_name, num_pkgs, pkg_name, pkg_xml, distro, src_uri, tar_dir,
        md5_cache, sha256_cache, skip_keys
    ):
        self.component_name = yoctoRecipe.convert_to_oe_name(component_name)
        self.num_pkgs = num_pkgs
        self.name = pkg_name
        self.distro = distro.name
        self.version = get_pkg_version(distro, pkg_name, is_oe=True)
        self.src_uri = src_uri
        self.pkg_xml = pkg_xml
        if self.pkg_xml:
            pkg_fields = PackageMetadata(pkg_xml)
            self.author = pkg_fields.upstream_name + ' <' + pkg_fields.upstream_email + '>'
            self.license = pkg_fields.upstream_license
            self.description = pkg_fields.description
            self.homepage = pkg_fields.homepage
            self.build_type = pkg_fields.build_type
        else:
            self.description = ''
            self.license = None
            self.homepage = None
            self.build_type = 'catkin'
            self.author = "OSRF"
        self.depends = set()
        self.depends_external = set()
        self.buildtool_depends = set()
        self.buildtool_depends_external = set()
        self.export_depends = set()
        self.export_depends_external = set()
        self.buildtool_export_depends = set()
        self.buildtool_export_depends_external = set()
        self.rdepends = set()
        self.rdepends_external = set()
        self.tdepends = set()
        self.tdepends_external = set()
        self.license_line = None
        self.archive_name = None
        self.license_md5 = None
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
        self.skip_keys = skip_keys

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
            info("downloading archive version for package '%s' from %s..." %
                 (self.name, self.src_uri))
            urlretrieve(self.src_uri, self.getArchiveName())

    def extractArchive(self):
        tar = tarfile.open(self.getArchiveName(), "r:gz")
        tar.extractall()
        tar.close()

    def add_build_depend(self, depend, internal=True):
        if depend not in self.skip_keys:
            if internal:
                if depend not in self.depends_external:
                    self.depends.add(depend)
            else:
                if depend not in self.depends:
                    self.depends_external.add(depend)

    def add_buildtool_depend(self, bdepend, internal=True):
        if bdepend not in self.skip_keys:
            if internal:
                if bdepend not in self.buildtool_depends_external:
                    self.buildtool_depends.add(bdepend)
            else:
                if bdepend not in self.buildtool_depends:
                    self.buildtool_depends_external.add(bdepend)

    def add_export_depend(self, edepend, internal=True):
        if edepend not in self.skip_keys:
            if internal:
                if edepend not in self.export_depends_external:
                    self.export_depends.add(edepend)
            else:
                if edepend not in self.export_depends:
                    self.export_depends_external.add(edepend)

    def add_buildtool_export_depend(self, tedepend, internal=True):
        if tedepend not in self.skip_keys:
            if internal:
                if tedepend not in self.buildtool_export_depends_external:
                    self.buildtool_export_depends.add(tedepend)
            else:
                if tedepend not in self.buildtool_export_depends:
                    self.buildtool_export_depends_external.add(tedepend)

    def add_run_depend(self, rdepend, internal=True):
        if rdepend not in self.skip_keys:
            if not internal:
                self.rdepends_external.add(rdepend)
            else:
                self.rdepends.add(rdepend)

    def add_test_depend(self, tdepend, internal=True):
        if tdepend not in self.skip_keys:
            if not internal:
                self.tdepends_external.add(tdepend)
            else:
                self.tdepends.add(tdepend)

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

    def get_inherit_line(self):
        return 'inherit ros_superflore_generated\ninherit ros_${ROS_DISTRO}\ninherit ros_${ROS_BUILD_TYPE}\n'

    @staticmethod
    def convert_to_oe_name(dep):
        # Discard meta-layer information past '@'
        dep = dep.split('@')[0]
        if dep.endswith('_native'):
            dep = dep[:-len('_native')] + '-rosnative'
        return dep.replace('_', '-')

    @staticmethod
    def get_spacing_prefix():
        return '\n' + ' ' * 4

    @classmethod
    def generate_multiline_variable(cls, var, container, sort=False):
        if sort:
            container = sorted(container)
        assignment = '{0} = "'.format(var)
        expression = '"\n'
        if container:
            expression = ' \\' + cls.get_spacing_prefix()
            expression += cls.get_spacing_prefix().join(
                [item + ' \\' for item in container]) + '\n"\n'
        return assignment + expression

    def get_depends_line(self, var, internal_depends, external_depends, is_native=False):
        def get_spacing_suffix(is_native):
            if is_native:
                return '-native \\'
            return ' \\'

        ret = '{0} = "'.format(var)
        union_deps = internal_depends | external_depends
        if len(union_deps) <= 0:
            return ret + '"\n\n'
        ret += ' \\'
        has_int_depends = False
        has_ext_depends = False
        for dep in sorted(union_deps):
            if dep in internal_depends:
                has_int_depends = True
                ret += yoctoRecipe.get_spacing_prefix() + yoctoRecipe.convert_to_oe_name(dep) + \
                    get_spacing_suffix(is_native)
                info('Internal dependency add: ' +
                      yoctoRecipe.convert_to_oe_name(dep))
            else:
                has_ext_depends = True
                try:
                    for res in resolve_dep(dep, 'openembedded', self.distro)[0]:
                        ret += yoctoRecipe.get_spacing_prefix() + yoctoRecipe.convert_to_oe_name(res) + \
                            get_spacing_suffix(is_native)
                        info('External dependency add: ' +
                              yoctoRecipe.convert_to_oe_name(res))
                except UnresolvedDependency:
                    dep = yoctoRecipe.convert_to_oe_name(dep)
                    info('Unresolved dependency: ' + dep)
                    if dep in yoctoRecipe.unresolved_deps_cache:
                        ret += yoctoRecipe.get_spacing_prefix() + dep + get_spacing_suffix(is_native)
                        info('Failed to resolve (cached): ' + dep)
                        continue
                    if dep in yoctoRecipe.resolved_deps_cache:
                        ret += yoctoRecipe.get_spacing_prefix() + dep + get_spacing_suffix(is_native)
                        info('Resolved in OE (cached): ' + dep)
                        continue
                    oe_query = OpenEmbeddedLayersDB()
                    oe_query.query_recipe(dep)
                    if oe_query.exists():
                        ret += yoctoRecipe.get_spacing_prefix() + oe_query.name + get_spacing_suffix(is_native)
                        yoctoRecipe.resolved_deps_cache.add(dep)
                        info('Resolved in OE: ' + dep + ' as ' +
                              oe_query.name + ' in ' + oe_query.layer)
                    else:
                        ret += yoctoRecipe.get_spacing_prefix() + dep + get_spacing_suffix(is_native)
                        yoctoRecipe.unresolved_deps_cache.add(dep)
                        info('Failed to resolve: ' + dep)

        if not has_int_depends and not has_ext_depends:
            info(self.name + ' has no ' + var + ' dependencies!')
        elif not has_int_depends:
            info(self.name + ' has no ' + var + ' internal dependencies!')
        elif not has_ext_depends:
            info(self.name + ' has no ' + var + ' external dependencies!')

        return ret.rstrip() + '\n"\n\n'

    def get_recipe_text(self, distributor, license_text):
        """
        Generate the Yocto Recipe, given the distributor line
        and the license text.
        """
        ret = "# Generated by superflore -- DO NOT EDIT\n#\n"
        ret += "# Copyright " + strftime("%Y", gmtime()) + " "
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
        if self.homepage:
            ret += 'HOMEPAGE = "' + self.homepage + '"\n'
        # section
        ret += 'SECTION = "devel"\n'
        # license
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
        # depends
        ret += self.get_depends_line('ROS_BUILD_DEPENDS',
                                     self.depends, self.depends_external)
        ret += self.get_depends_line('ROS_BUILDTOOL_DEPENDS', self.buildtool_depends,
                                     self.buildtool_depends_external, is_native=True)
        ret += self.get_depends_line('ROS_EXPORT_DEPENDS',
                                     self.export_depends, self.export_depends_external)
        ret += self.get_depends_line('ROS_BUILDTOOL_EXPORT_DEPENDS',
                                     self.buildtool_export_depends, self.buildtool_export_depends_external, is_native=True)
        ret += self.get_depends_line('ROS_EXEC_DEPENDS',
                                     self.rdepends, self.rdepends_external)
        ret += '# Currently informational only -- see http://www.ros.org/reps/rep-0149.html#dependency-tags.\n'
        ret += self.get_depends_line('ROS_TEST_DEPENDS',
                                     self.tdepends, self.tdepends_external)
        ret += 'DEPENDS = "${ROS_BUILD_DEPENDS} ${ROS_BUILDTOOL_DEPENDS}"' + '\n'
        ret += '# Bitbake doesn\'t support the "export" concept, so build them as if we needed them to build this package (even though we actually\n'
        ret += '# don\'t) so that they\'re guaranteed to have been staged should this package appear in another\'s DEPENDS.\n'
        ret += 'DEPENDS += "${ROS_EXPORT_DEPENDS} ${ROS_BUILDTOOL_EXPORT_DEPENDS}"' + '\n\n'
        ret += 'RDEPENDS_${PN} += "${ROS_EXEC_DEPENDS}"' + '\n\n'
        # SRC_URI
        ret += 'SRC_URI = "' + self.src_uri + ';'
        ret += 'downloadfilename=${ROS_SP}.tar.gz"\n'
        ret += 'SRC_URI[md5sum] = "' + self.src_md5 + '"\n'
        ret += 'SRC_URI[sha256sum] = "' + self.src_sha256 + '"\n'
        ret += 'S = "${WORKDIR}/'
        ret += self.get_src_location() + '"\n\n'

        ret += 'ROS_BUILD_TYPE = "' + self.build_type + '"\n'
        ret += 'ROS_RECIPES_TREE = "recipes-ros2"\n\n'
        # include
        ret += '# Allow the above settings to be overridden.\n'
        inc_prefix = 'include ${ROS_LAYERDIR}/'
        component_path = '/' + self.component_name + '/' + self.component_name
        inc_suffix = '_common.inc\n'
        ret += inc_prefix + 'recipes-ros' + component_path + inc_suffix
        ret += inc_prefix + 'recipes-ros2' + component_path + inc_suffix
        ret += inc_prefix + '${ROS_RECIPES_TREE}' + \
            component_path + '-${PV}' + inc_suffix
        if self.num_pkgs > 1:
            # Generated if component generates more than one package
            path_prefix = inc_prefix + \
                '${ROS_RECIPES_TREE}/' + self.component_name
            ret += path_prefix + '/${BPN}.inc\n'
            ret += path_prefix + '/${BPN}-${PV}.inc\n'
        # Inherits
        ret += '\n' + self.get_inherit_line()
        return ret

    @staticmethod
    def generate_rosdistro_conf(basepath, distro, skip_keys=[]):
        conf_path = "{0}/conf/".format(basepath)
        conf_file_path = '{0}generated-{1}.conf'.format(conf_path, distro)
        try:
            make_dir(conf_path)
            with open(conf_file_path, "w") as conf_file:
                conf_file.write('# Generated by superflore -- DO NOT EDIT\n')
                conf_file.write('#\n')
                conf_file.write(
                    '# Copyright 2019 Open Source Robotics Foundation\n')
                conf_file.write(
                    '# Distributed under the terms of the BSD license\n')
                conf_file.write('\nROS_SUPERFLORE_GENERATION_SCHEME = "1"\n')
                conf_file.write('# When superflore was started, in UTC:\n')
                conf_file.write('ROS_SUPERFLORE_GENERATION_DATETIME = "{0}"\n'.format(datetime.utcnow().strftime('%Y%m%d%H%M%S')))
                conf_file.write(yoctoRecipe.generate_multiline_variable(
                    'ROS_SUPERFLORE_GENERATION_SKIP_LIST', skip_keys))
                ok('Wrote {0}'.format(conf_file_path))
        except Exception as e:
            err("Failed to write conf {0} to disk!".format(conf_file_path))
            raise e

    @staticmethod
    def generate_packagegroup_ros_world(basepath, distro, skip_keys=[]):
        pkggrp_path = "{0}/generated-recipes-{1}/packagegroups/".format(
            basepath, distro)
        pkggrp_file_path = '{0}packagegroup-ros-world.bb'.format(pkggrp_path)
        try:
            make_dir(pkggrp_path)
            with open(pkggrp_file_path, "w") as pkggrp_file:
                pkggrp_file.write('# Generated by superflore -- DO NOT EDIT\n')
                pkggrp_file.write('#\n')
                pkggrp_file.write(
                    '# Copyright 2019 Open Source Robotics Foundation\n')
                pkggrp_file.write(
                    '# Distributed under the terms of the BSD license\n')
                pkggrp_file.write('\nDESCRIPTION = "${ROS_EDITION} world package group"\n')
                pkggrp_file.write('LICENSE = "MIT"\n\n')
                pkggrp_file.write('inherit packagegroup\n\n')
                pkggrp_file.write('PACKAGES = "${PN}"\n\n')
                pkggrp_file.write(yoctoRecipe.generate_multiline_variable(
                    'RDEPENDS_${PN}', yoctoRecipe.generated_recipes, sort=True))
                ok('Wrote {0}'.format(pkggrp_file_path))
        except Exception as e:
            err("Failed to write packagegroup {0} to disk!".format(
                pkggrp_file_path))
            raise e

    @staticmethod
    def generate_distro_cache(basepath, distro, skip_keys=[]):
        distro_cache_path = "{0}/files/".format(basepath)
        distro_cache_file_path = '{0}{1}-cache.yaml'.format(
            distro_cache_path, distro)
        try:
            make_dir(distro_cache_path)
            from rosdistro import get_index, get_index_url, _get_dist_file_data
            import gzip
            try:
                from urllib.request import urlopen
            except ImportError:
                from urllib2 import urlopen
            try:
                from cStringIO import StringIO
            except ImportError:
                from io import BytesIO as StringIO
            index_url = get_index_url()
            index = get_index(index_url)
            dist = index.distributions.get(distro, None)
            if not dist:
                raise RuntimeError(
                    'Unknown distribution {0} when looking at {1}'.format(distro, index_url))
            cache_url = dist.get('distribution_cache', None)
            if not cache_url:
                raise RuntimeError(
                    'Distribution {0} has no cache'.format(distro))
            raw_data = urlopen(cache_url, timeout=10).read()
            if cache_url.endswith('.yaml.gz'):
                yaml_gz_stream = StringIO(raw_data)
                f = gzip.GzipFile(fileobj=yaml_gz_stream, mode='rb')
                yaml_str = f.read()
                f.close()
                if not isinstance(yaml_str, str):
                    yaml_str = yaml_str.decode('utf-8')
            else:
                yaml_str = raw_data.decode('utf-8')
            with open(distro_cache_file_path, "w") as distro_cache_file:
                distro_cache_file.write(yaml_str)
                ok('Wrote {0}'.format(distro_cache_file_path))
        except Exception as e:
            err("Failed to write distro cache {0} to disk!".format(
                distro_cache_file_path))
            raise e
