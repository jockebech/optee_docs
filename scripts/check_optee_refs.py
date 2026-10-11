#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
#
# Check that the OP-TEE configuration options, functions and source paths
# named in documentation files still exist in an optee_os source tree.
#
# Usage: check_optee_refs.py --optee-os <path> <file.rst> [<file.rst> ...]

import argparse
import glob
import os
import re
import subprocess
import sys

# Names used as placeholders in examples, not expected in optee_os
ALLOWLIST = {
    'CFG_FOO',
}

CFG_RE = re.compile(r'\bCFG_[A-Z0-9_]+')
FUNC_RE = re.compile(r'``([A-Za-z_][A-Za-z0-9_]*)\(\)``')
PATH_RE = re.compile(r'``([A-Za-z0-9_.<>$()-]+(?:/[A-Za-z0-9_.<>$()-]+)+)``')
INCLUDE_RE = re.compile(r'#include\s+<([A-Za-z0-9_./-]+)>')


def git_grep_word(tree, word):
    return subprocess.run(['git', '-C', tree, 'grep', '-q', '-w', '-F', word],
                          check=False).returncode == 0


def git_grep_prefix(tree, prefix):
    return subprocess.run(['git', '-C', tree, 'grep', '-q', '-F', prefix],
                          check=False).returncode == 0


def git_grep_lines(tree, word):
    res = subprocess.run(['git', '-C', tree, 'grep', '-n', '-w', '-F', word],
                         check=False, capture_output=True, text=True)
    for line in res.stdout.splitlines():
        path, _, rest = line.partition(':')
        _, _, content = rest.partition(':')
        yield path, content


def cfg_is_used(tree, name):
    # An option counts as existing only if something uses it. An option
    # that is only assigned, for example a leftover
    # "$(call force,CFG_X,y)" in a platform conf.mk, has no effect.
    assign = re.compile(r'^\s*(?:export\s+)?' + re.escape(name) +
                        r'\s*[?:+]?=|force,\s*' + re.escape(name) + r'\s*,')
    for path, content in git_grep_lines(tree, name):
        if not (path.endswith('.mk') or os.path.basename(path) == 'Makefile'):
            return True
        content = content.split('#', 1)[0]
        if re.search(r'\b' + re.escape(name) + r'\b',
                     assign.sub('', content)):
            return True
    return False


def cfg_exists(tree, name):
    if cfg_is_used(tree, name):
        return True
    # References such as CFG_TZDRAM or CFG_SECURE_TIME_SOURCE_* name a
    # family of options, accept them if an option with that prefix exists.
    return git_grep_prefix(tree, name.rstrip('_') + '_')


def path_exists(tree, path):
    # Placeholders such as <arch> or $(ARCH) match any directory
    pattern = re.sub(r'<[^>]+>|\$\([^)]+\)', '*', path)
    if glob.glob(os.path.join(tree, pattern)):
        return True
    # Include paths such as mm/generic_ram_layout.h are relative to an
    # include directory
    return bool(glob.glob(os.path.join(tree, '**', 'include', pattern),
                          recursive=True))


def check_file(tree, doc):
    with open(doc, encoding='utf-8') as f:
        text = f.read()

    errors = []
    for name in sorted(set(CFG_RE.findall(text)) - ALLOWLIST):
        if not cfg_exists(tree, name):
            errors.append(f'{doc}: configuration option not found: {name}')
    for name in sorted(set(FUNC_RE.findall(text)) - ALLOWLIST):
        if not git_grep_word(tree, name):
            errors.append(f'{doc}: function not found: {name}()')
    for path in sorted(set(PATH_RE.findall(text))):
        if not path_exists(tree, path):
            errors.append(f'{doc}: path not found: {path}')
    for path in sorted(set(INCLUDE_RE.findall(text))):
        # Some headers, such as platform_config.h, are provided by each
        # platform directory instead of an include directory
        if not glob.glob(os.path.join(tree, '**', path), recursive=True):
            errors.append(f'{doc}: include file not found: {path}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--optee-os', required=True,
                        help='path to an optee_os git checkout')
    parser.add_argument('docs', nargs='+', help='documentation files')
    args = parser.parse_args()

    errors = []
    for doc in args.docs:
        errors += check_file(args.optee_os, doc)

    for e in errors:
        print(e)
    if errors:
        print(f'{len(errors)} reference(s) not found in {args.optee_os}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
