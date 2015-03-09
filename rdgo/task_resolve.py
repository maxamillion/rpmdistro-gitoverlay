#!/usr/bin/env python
#
# Copyright (C) 2015 Colin Walters <walters@verbum.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import os
import json
import yaml
import copy

from .utils import fatal
from .task import Task
from .git import GitMirror

def require_key(conf, key):
    try:
        return conf[key]
    except KeyError, e:
        fatal("Missing config key {0}".format(key))

class TaskResolve(Task):
    def _url_to_projname(self, url):
        rcolon = url.rfind(':')
        rslash = url.rfind('/')
        basename = url[max(rcolon, rslash)+1:]
        if basename.endswith('.git'):
            return basename[0:-4]
        return basename

    def _expand_srckey(self, component, key):
        val = component[key]
        aliases = self._overlay.get('aliases', [])
        for alias in aliases:
            name = alias['name']
            namec = name + ':'
            if not val.startswith(namec):
                continue
            return alias['url'] + val[len(namec):]
        return val

    def _expand_component(self, component):
        # 'src' and 'distgit' mappings
        if component.get('src') is None:
            fatal("Component {0} is missing 'src' or 'distgit'")

        component['src'] = self._expand_srckey(component, 'src')

        # TODO support pulling VCS from distgit
        srcname = self._url_to_projname(component['src'])
        distgit = component.get('distgit')
        if distgit is None:
            component['distgit'] = distgit = { 'name': srcname }
        distgit_src = distgit.get('src')
        if distgit_src is None:
            distgit['src'] = self._distgit_prefix + ':' + distgit['name']

        distgit['src'] = self._expand_srckey(distgit, 'src')

        # tag/branch defaults
        if component.get('tag') is None:
            component['branch'] = component.get('branch', 'master')
        if distgit.get('tag') is None:
            distgit['branch'] = distgit.get('branch', 'master')

    def run(self):
        ovlpath = self.workdir + '/overlay.yml'
        with open(ovlpath) as f:
            self._overlay = yaml.load(f)
            
        self._distgit = require_key(self._overlay, 'distgit')
        self._distgit_prefix = require_key(self._distgit, 'prefix')

        mirror = GitMirror(self.workdir + '/src')
        expanded = copy.deepcopy(self._overlay)
        for component in expanded['components']:
            self._expand_component(component)
            mirror.mirror(component['src'], component.get('branch', component.get('tag')),
                          fetch=True)
            distgit = component['distgit']
            mirror.mirror(distgit['src'], distgit.get('branch', distgit.get('tag')),
                          fetch=True)

        snapshot_path = self.workdir + '/snapshot.json'
        snapshot_tmppath = snapshot_path + '.tmp'
        with open(snapshot_tmppath, 'w') as f:
            json.dump(expanded, f, indent=4, sort_keys=True)
        os.rename(snapshot_tmppath, snapshot_path)
        log("Wrote: " + snapshot_path)
